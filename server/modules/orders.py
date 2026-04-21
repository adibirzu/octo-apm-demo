"""Order management with ATP-safe persistence and sync-aware telemetry."""

from __future__ import annotations

import hmac
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from server.config import cfg
from server.database import Customer, Order, OrderItem, Product, get_db
from server.observability.correlation import build_correlation_id, current_trace_context
from server.observability.logging_sdk import log_security_event, push_log
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability import business_metrics
from server.order_sync import list_backlog_orders, order_security_summary, sync_external_orders

router = APIRouter(prefix="/api/orders", tags=["Orders"])
tracer_fn = get_tracer


def _serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "customer_name": order.customer.name if order.customer else "Unknown",
        "customer_email": order.source_customer_email or (order.customer.email if order.customer else ""),
        "total": float(order.total or 0),
        "status": order.status,
        "source_system": order.source_system or "enterprise-crm",
        "source_order_id": order.source_order_id,
        "sync_status": order.sync_status or "local",
        "backlog_status": order.backlog_status or "current",
        "correlation_id": order.correlation_id,
        "last_synced_at": order.last_synced_at.isoformat() if order.last_synced_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


@router.get("")
async def list_orders(
    request: Request,
    status: str = Query(default="", description="Filter by status"),
    customer_id: int = Query(default=0, description="Filter by customer"),
    backlog_only: bool = Query(default=False, description="Show backlog orders only"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List orders with external sync metadata."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("orders.list") as span:
        span.set_attribute("orders.filter.status", status or "all")
        span.set_attribute("orders.filter.customer_id", customer_id)
        span.set_attribute("orders.filter.backlog_only", backlog_only)

        async with get_db() as db:
            query = (
                select(Order)
                .options(selectinload(Order.customer))
                .order_by(Order.created_at.desc())
            )
            if status:
                query = query.where(Order.status == status)
            if customer_id:
                query = query.where(Order.customer_id == customer_id)
            if backlog_only:
                query = query.where(Order.backlog_status == "backlog")

            query = query.offset(offset).limit(limit)

            with tracer.start_as_current_span("db.query.orders_list"):
                result = await db.execute(query)
                orders = list(result.scalars())

        payload = [_serialize_order(order) for order in orders]
        return {
            "orders": payload,
            "total": len(payload),
            "limit": limit,
            "offset": offset,
            "database_target": cfg.database_target_label,
            "source": cfg.orders_sync_source_name,
        }


@router.get("/backlog")
async def backlog_orders(request: Request):
    tracer = tracer_fn()
    with tracer.start_as_current_span("orders.backlog") as span:
        orders = await list_backlog_orders()
        span.set_attribute("orders.backlog.count", len(orders))
        return {
            "orders": [_serialize_order(order) for order in orders],
            "total": len(orders),
        }


@router.get("/security/summary")
async def security_summary(request: Request):
    tracer = tracer_fn()
    with tracer.start_as_current_span("orders.security.summary"):
        return await order_security_summary()


@router.post("/sync")
async def sync_orders(request: Request):
    tracer = tracer_fn()
    correlation_id = build_correlation_id(getattr(request.state, "correlation_id", ""))
    with tracer.start_as_current_span("orders.sync.trigger") as span:
        span.set_attribute("orders.sync.source", cfg.orders_sync_source_name)
        result = await sync_external_orders(correlation_id=correlation_id)
        span.set_attribute("orders.sync.created", result.get("created", 0))
        span.set_attribute("orders.sync.updated", result.get("updated", 0))
        span.set_attribute("orders.sync.failed", result.get("failed", 0))
        business_metrics.record_order_sync(
            result.get("created", 0), result.get("updated", 0), result.get("failed", 0)
        )
        return result


@router.get("/{order_id}")
async def get_order(order_id: int, request: Request):
    """Get order detail with DB drilldown context."""
    tracer = tracer_fn()
    trace_ctx = current_trace_context()

    with tracer.start_as_current_span("orders.get") as span:
        span.set_attribute("orders.id", order_id)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.order_detail"):
                result = await db.execute(
                    select(Order)
                    .options(selectinload(Order.customer), selectinload(Order.items).selectinload(OrderItem.product))
                    .where(Order.id == order_id)
                )
                order = result.scalar_one_or_none()

        if not order:
            return {"error": "Order not found"}

        detail = _serialize_order(order)
        detail.update(
            {
                "notes": order.notes,
                "shipping_address": order.shipping_address,
                "sync_error": order.sync_error,
                "items": [
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "product_name": item.product.name if item.product else "Unknown",
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price or 0),
                        "line_total": float((item.quantity or 0) * (item.unit_price or 0)),
                    }
                    for item in order.items
                ],
                "db_drilldown": {
                    "database_target": cfg.database_target_label,
                    "atp_ocid": cfg.atp_ocid or None,
                    "atp_connection_name": cfg.atp_connection_name or None,
                    "db_query_preview": "SELECT * FROM orders WHERE id = :id; SELECT * FROM order_items WHERE order_id = :id",
                    "db_management_console_url": cfg.db_management_console_url,
                    "opsi_console_url": cfg.opsi_console_url,
                },
                "telemetry": {
                    "correlation_id": order.correlation_id or build_correlation_id(getattr(request.state, "correlation_id", "")),
                    "trace_id": trace_ctx["trace_id"],
                    "span_id": trace_ctx["span_id"],
                    "traceparent": trace_ctx["traceparent"],
                    "apm_console_url": cfg.apm_console_url,
                    "log_analytics_console_url": cfg.log_analytics_console_url,
                },
            }
        )
        return {"order": detail}


def _require_internal_key_if_configured(request: Request) -> None:
    """Enforce X-Internal-Service-Key on cross-service POST /api/orders
    when the shared key is configured. If the key is empty, allow
    anonymous traffic (back-compat with deployments that have not yet
    populated the Kubernetes secret).
    """
    required = getattr(cfg, "drone_shop_internal_key", "") or ""
    if not required:
        return
    supplied = (request.headers.get("X-Internal-Service-Key") or "").strip()
    if not supplied or not hmac.compare_digest(supplied, required):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Service-Key")


@router.post("")
async def create_order(request: Request):
    """Create order and persist it with server-side total calculation.

    When the calling service supplies idempotency metadata
    (``source_system``, ``source_order_id``, ``idempotency_token``) the
    values are stored verbatim so a retried sync from the shop does
    not create a duplicate invoice.
    """
    _require_internal_key_if_configured(request)
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()
    correlation_id = build_correlation_id(getattr(request.state, "correlation_id", ""))

    with tracer.start_as_current_span("orders.create") as span:
        customer_id = int(body.get("customer_id") or 0)
        items = body.get("items") or []
        if not items and body.get("product_id"):
            items = [
                {
                    "product_id": body.get("product_id"),
                    "quantity": int(body.get("quantity") or 1),
                    "unit_price": float(body.get("unit_price") or 0),
                }
            ]

        async with get_db() as db:
            customer = await db.get(Customer, customer_id) if customer_id else None
            if customer is None:
                return {"error": "Customer not found"}

            product_ids = [int(item.get("product_id") or 0) for item in items if item.get("product_id")]
            products = {}
            if product_ids:
                result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
                products = {product.id: product for product in result.scalars()}

            computed_total = 0.0
            order_items = []
            for item in items:
                quantity = int(item.get("quantity") or 0)
                if quantity <= 0:
                    with security_span("mass_assignment", severity="high", payload=str(item), source_ip=client_ip):
                        log_security_event(
                            "mass_assignment",
                            "high",
                            "Invalid quantity detected on order create",
                            source_ip=client_ip,
                            payload=str(item),
                        )
                    return {"error": "Quantity must be positive"}

                product = products.get(int(item.get("product_id") or 0))
                price = float(product.price if product else item.get("unit_price") or 0.0)
                computed_total += quantity * price
                order_items.append({"product": product, "quantity": quantity, "unit_price": price})

            client_total = float(body.get("total") or 0.0)
            if client_total and abs(client_total - computed_total) > 0.01:
                with security_span(
                    "mass_assignment",
                    severity="critical",
                    payload=f"client_total={client_total}, computed_total={computed_total}",
                    source_ip=client_ip,
                ):
                    log_security_event(
                        "mass_assignment",
                        "critical",
                        "Order total tampering detected",
                        source_ip=client_ip,
                        payload=f"client_total={client_total}, computed_total={computed_total}",
                        correlation_id=correlation_id,
                    )

            # Honor idempotency metadata if supplied by the calling
            # service; otherwise fall back to server-side generation so
            # direct CRM-UI order creation still works.
            payload_source_system = (body.get("source_system") or "").strip()
            payload_source_order_id = (body.get("source_order_id") or "").strip()
            source_system = payload_source_system or "enterprise-crm"
            source_order_id = (
                payload_source_order_id
                or f"manual-{customer.id}-{uuid4().hex[:12]}"
            )
            order = Order(
                customer_id=customer.id,
                total=computed_total,
                status="pending",
                notes=body.get("notes", ""),
                shipping_address=body.get("shipping_address", ""),
                source_system=source_system,
                source_order_id=source_order_id,
                source_customer_email=customer.email,
                sync_status="local",
                backlog_status="backlog",
                correlation_id=correlation_id,
            )
            db.add(order)
            await db.flush()

            for item in order_items:
                db.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=item["product"].id if item["product"] else None,
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                    )
                )
            await db.flush()

        business_metrics.record_order_created(computed_total, source="enterprise-crm")
        push_log(
            "INFO",
            f"Order #{order.id} created",
            **{
                "orders.id": order.id,
                "orders.total": computed_total,
                "orders.items_count": len(order_items),
                "orders.source_system": "enterprise-crm",
                "correlation.id": correlation_id,
            },
        )
        return {"status": "created", "order_id": order.id, "total": computed_total}


@router.patch("/{order_id}/status")
async def update_order_status(order_id: int, request: Request):
    tracer = tracer_fn()
    body = await request.json()
    new_status = str(body.get("status") or "").strip().lower()

    with tracer.start_as_current_span("orders.update_status") as span:
        span.set_attribute("orders.id", order_id)
        span.set_attribute("orders.new_status", new_status)

        async with get_db() as db:
            order = await db.get(Order, order_id)
            if order is None:
                return {"error": "Order not found"}
            order.status = new_status
            order.backlog_status = "backlog" if new_status in {"pending", "processing", "queued"} else "current"
            await db.flush()

        return {"status": "updated", "order_id": order_id, "new_status": new_status}
