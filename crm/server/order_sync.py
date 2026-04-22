"""External order sync and order-risk helpers."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from server.config import cfg
from server.database import Customer, Order, OrderItem, OrderSyncAudit, Product, async_session_factory
from server.observability.correlation import build_correlation_id, current_trace_context, outbound_headers, set_peer_service
from server.observability.logging_sdk import log_security_event, push_log
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

BACKLOG_STATUSES = {"pending", "processing", "backlog", "queued", "awaiting_fulfillment"}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def external_orders_base_url() -> str:
    return cfg.external_orders_url or cfg.octo_drone_shop_url or cfg.mushop_cloudnative_url or cfg.octo_apm_cloudnative_url


async def sync_external_orders(correlation_id: str = "", limit: int = 200) -> dict[str, Any]:
    """Fetch external orders and upsert them into the app database."""
    base_url = external_orders_base_url()
    correlation_id = build_correlation_id(correlation_id)
    trace_ctx = current_trace_context()
    tracer = get_tracer()

    if not base_url:
        return {"status": "skipped", "reason": "external order source not configured", "correlation_id": correlation_id}

    with tracer.start_as_current_span("orders.sync.external") as span:
        span.set_attribute("orders.sync.source", cfg.orders_sync_source_name)
        span.set_attribute("orders.sync.url", base_url)
        set_peer_service(span, cfg.orders_sync_source_name, base_url)
        span.set_attribute("component", "http")
        try:
            orders = await _fetch_external_orders(base_url, correlation_id, limit)
        except Exception as exc:
            push_log(
                "ERROR",
                "External orders sync fetch failed",
                **{
                    "orders.sync.source": cfg.orders_sync_source_name,
                    "error.message": str(exc),
                    "correlation.id": correlation_id,
                },
            )
            return {
                "status": "failed",
                "reason": str(exc),
                "source": cfg.orders_sync_source_name,
                "correlation_id": correlation_id,
            }
        sync_result = {"created": 0, "updated": 0, "failed": 0, "orders": [], "source": cfg.orders_sync_source_name}

        async with async_session_factory() as session:
            product_cache = await _product_lookup(session)
            for raw_order in orders:
                normalized = _normalize_external_order(raw_order)
                if not normalized["source_order_id"]:
                    sync_result["failed"] += 1
                    await _record_audit(
                        session,
                        source_order_id="",
                        action="skip",
                        status="invalid",
                        message="Missing source order id",
                        correlation_id=correlation_id,
                        trace_id=trace_ctx["trace_id"],
                    )
                    continue

                try:
                    async with session.begin_nested():
                        customer = await _resolve_customer(session, normalized)
                        sync_action, order = await _upsert_order(session, customer, normalized, correlation_id)
                        await _replace_order_items(session, order, normalized["items"], product_cache)
                        await _record_audit(
                            session,
                            source_order_id=normalized["source_order_id"],
                            action=sync_action,
                            status="success",
                            message=f"{sync_action} order from {cfg.orders_sync_source_name}",
                            correlation_id=correlation_id,
                            trace_id=trace_ctx["trace_id"],
                        )
                    sync_result[sync_action] += 1
                    sync_result["orders"].append(
                        {
                            "id": order.id,
                            "source_order_id": order.source_order_id,
                            "status": order.status,
                            "backlog_status": order.backlog_status,
                            "total": order.total,
                        }
                    )
                except Exception as exc:
                    sync_result["failed"] += 1
                    await _record_audit(
                        session,
                        source_order_id=normalized["source_order_id"],
                        action="upsert",
                        status="failed",
                        message=str(exc),
                        correlation_id=correlation_id,
                        trace_id=trace_ctx["trace_id"],
                    )

            await session.commit()

        push_log(
            "INFO" if sync_result["failed"] == 0 else "WARNING",
            "External orders sync completed",
            **{
                "orders.sync.source": cfg.orders_sync_source_name,
                "orders.sync.created": sync_result["created"],
                "orders.sync.updated": sync_result["updated"],
                "orders.sync.failed": sync_result["failed"],
                "correlation.id": correlation_id,
            },
        )
        sync_result["correlation_id"] = correlation_id
        return sync_result


async def order_security_summary() -> dict[str, Any]:
    cutoff = _utcnow() - timedelta(minutes=max(cfg.backlog_order_age_minutes, 1))
    async with async_session_factory() as session:
        total_orders = await session.scalar(select(func.count(Order.id))) or 0
        backlog_orders = await session.scalar(
            select(func.count(Order.id)).where(
                Order.backlog_status == "backlog",
            )
        ) or 0
        stale_backlog_orders = await session.scalar(
            select(func.count(Order.id)).where(
                Order.backlog_status == "backlog",
                Order.created_at < cutoff,
            )
        ) or 0
        suspicious_totals = await session.scalar(
            select(func.count(Order.id)).where(Order.total >= cfg.suspicious_order_total_threshold)
        ) or 0
        failed_syncs = await session.scalar(
            select(func.count(OrderSyncAudit.id)).where(OrderSyncAudit.sync_status == "failed")
        ) or 0

    return {
        "total_orders": int(total_orders),
        "backlog_orders": int(backlog_orders),
        "stale_backlog_orders": int(stale_backlog_orders),
        "suspicious_totals": int(suspicious_totals),
        "failed_syncs": int(failed_syncs),
        "thresholds": {
            "suspicious_order_total": cfg.suspicious_order_total_threshold,
            "backlog_age_minutes": cfg.backlog_order_age_minutes,
        },
    }


async def list_backlog_orders(limit: int = 50) -> list[Order]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.customer), selectinload(Order.items))
            .where(Order.backlog_status == "backlog")
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())


async def _fetch_external_orders(base_url: str, correlation_id: str, limit: int) -> list[dict[str, Any]]:
    headers = outbound_headers(correlation_id)
    if cfg.drone_shop_internal_key:
        headers["X-Internal-Service-Key"] = cfg.drone_shop_internal_key

    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        response = await client.get(f"{base_url.rstrip('/')}{cfg.external_orders_path}", params={"limit": limit})
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    for key in ("orders", "items", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_external_order(raw_order: dict[str, Any]) -> dict[str, Any]:
    customer = raw_order.get("customer") or {}
    items = raw_order.get("items") or raw_order.get("lines") or []
    customer_email = (
        raw_order.get("customer_email")
        or customer.get("email")
        or raw_order.get("email")
        or ""
    ).strip().lower()
    customer_name = (
        customer.get("name")
        or raw_order.get("customer_name")
        or raw_order.get("name")
        or customer_email.split("@")[0].replace(".", " ").title()
        or "External Customer"
    )
    status = str(raw_order.get("status") or "pending").lower()
    created_at = _parse_dt(raw_order.get("created_at") or raw_order.get("created") or raw_order.get("submitted_at"))
    normalized_items = []
    computed_total = 0.0
    for item in items:
        quantity = int(item.get("quantity") or item.get("qty") or 1)
        unit_price = _coerce_float(item.get("unit_price") or item.get("price") or 0.0)
        computed_total += quantity * unit_price
        normalized_items.append(
            {
                "product_ref": item.get("product_id") or item.get("sku") or item.get("product_sku") or item.get("name"),
                "product_name": item.get("product_name") or item.get("name") or "Synced Item",
                "quantity": quantity,
                "unit_price": unit_price,
            }
        )

    discount = _coerce_float(
        raw_order.get("discount")
        or raw_order.get("discount_amount")
        or (raw_order.get("coupon") or {}).get("discount")
        or 0.0
    )
    shipping_cost = float(raw_order.get("shipping_cost") or 0.0)
    if shipping_cost <= 0.0:
        shipping_cost = _coerce_float(
            raw_order.get("shipping_amount")
            or (raw_order.get("shipment") or {}).get("shipping_cost")
            or 0.0
        )
    expected_total = round(max(computed_total - discount, 0.0) + shipping_cost, 2)
    declared_total = _coerce_float(raw_order.get("total") or raw_order.get("amount") or expected_total or 0.0)
    if normalized_items and declared_total > expected_total + 0.01:
        with security_span(
            "mass_assignment",
            severity="high",
            payload=json.dumps(
                {
                    "declared_total": declared_total,
                    "computed_total": computed_total,
                    "discount": discount,
                    "shipping_cost": shipping_cost,
                    "expected_total": expected_total,
                }
            )[:512],
        ):
            log_security_event(
                "mass_assignment",
                "high",
                "External order total mismatch detected",
                payload=json.dumps(raw_order)[:512],
                source_system=cfg.orders_sync_source_name,
            )

    backlog_status = "backlog" if status in BACKLOG_STATUSES else "current"
    return {
        "source_order_id": str(raw_order.get("id") or raw_order.get("order_id") or raw_order.get("number") or ""),
        "customer_email": customer_email,
        "customer_name": customer_name,
        "status": status,
        "shipping_address": raw_order.get("shipping_address") or customer.get("address") or "",
        "created_at": created_at,
        "last_synced_at": _utcnow(),
        "total": declared_total,
        "notes": raw_order.get("notes") or raw_order.get("comment") or "",
        "backlog_status": backlog_status,
        "items": normalized_items,
        "payload": raw_order,
    }


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return _utcnow()


async def _resolve_customer(session, normalized: dict[str, Any]) -> Customer:
    customer_email = normalized["customer_email"]
    customer = None
    if customer_email:
        customer = await session.scalar(select(Customer).where(Customer.email == customer_email))
    if customer is None:
        customer = Customer(
            name=normalized["customer_name"],
            email=customer_email or f"{normalized['source_order_id']}@external.local",
            company=cfg.orders_sync_source_name,
            industry="Retail",
            revenue=normalized["total"],
            notes=f"Auto-created from {cfg.orders_sync_source_name} sync",
        )
        session.add(customer)
        await session.flush()
    return customer


async def _upsert_order(session, customer: Customer, normalized: dict[str, Any], correlation_id: str) -> tuple[str, Order]:
    order = await session.scalar(
        select(Order).where(
            Order.source_system == cfg.orders_sync_source_name,
            Order.source_order_id == normalized["source_order_id"],
        )
    )
    action = "updated" if order else "created"
    if order is None:
        order = Order(
            source_system=cfg.orders_sync_source_name,
            source_order_id=normalized["source_order_id"],
            created_at=normalized["created_at"],
            customer_id=customer.id,
            total=normalized["total"],
            status=normalized["status"],
            notes=normalized["notes"],
            shipping_address=normalized["shipping_address"],
            source_customer_email=normalized["customer_email"],
            sync_status="synced",
            backlog_status=normalized["backlog_status"],
            sync_error="",
            source_payload=json.dumps(normalized["payload"], default=str),
            last_synced_at=normalized["last_synced_at"],
            correlation_id=correlation_id,
        )
        session.add(order)
    else:
        order.customer_id = customer.id
        order.total = normalized["total"]
        order.status = normalized["status"]
        order.notes = normalized["notes"]
        order.shipping_address = normalized["shipping_address"]
        order.source_customer_email = normalized["customer_email"]
        order.sync_status = "synced"
        order.backlog_status = normalized["backlog_status"]
        order.sync_error = ""
        order.source_payload = json.dumps(normalized["payload"], default=str)
        order.last_synced_at = normalized["last_synced_at"]
        order.correlation_id = correlation_id
    await session.flush()
    return action, order


async def _replace_order_items(session, order: Order, items: list[dict[str, Any]], product_cache: dict[str, Product]) -> None:
    await session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))

    for item in items:
        product = await _resolve_product(session, item, product_cache)
        quantity = item["quantity"]
        unit_price = item["unit_price"]
        if quantity < 0:
            with security_span("mass_assignment", severity="critical", payload=json.dumps(item)[:512]):
                log_security_event("mass_assignment", "critical", "Negative quantity detected during order sync", payload=json.dumps(item)[:512])
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id if product else None,
                quantity=quantity,
                unit_price=unit_price,
            )
        )
    await session.flush()


async def _product_lookup(session) -> dict[str, Product]:
    result = await session.execute(select(Product))
    products = list(result.scalars())
    cache = {}
    for product in products:
        cache[product.sku.lower()] = product
        cache[product.name.lower()] = product
        cache[str(product.id)] = product
    return cache


async def _resolve_product(session, item: dict[str, Any], product_cache: dict[str, Product]) -> Product:
    ref = str(item.get("product_ref") or item.get("product_name") or "").lower()
    product = product_cache.get(ref)
    if product:
        return product

    base_name = item.get("product_name") or "Synced Item"
    digest = hashlib.md5((ref or base_name).encode("utf-8")).hexdigest()[:8].upper()
    sku = f"SYNC-{digest}"
    product = Product(
        name=base_name,
        sku=sku,
        description=f"Auto-created from {cfg.orders_sync_source_name}",
        price=float(item.get("unit_price") or 0.0),
        stock=999,
        category="External Sync",
        is_active=True,
    )
    session.add(product)
    await session.flush()
    product_cache[sku.lower()] = product
    product_cache[base_name.lower()] = product
    return product


async def _record_audit(
    session,
    source_order_id: str,
    action: str,
    status: str,
    message: str,
    correlation_id: str,
    trace_id: str,
) -> None:
    session.add(
        OrderSyncAudit(
            source_system=cfg.orders_sync_source_name,
            source_order_id=source_order_id,
            sync_action=action,
            sync_status=status,
            message=message,
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
    )
