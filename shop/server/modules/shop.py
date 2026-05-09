"""Shop module — OCTO Drone Shop storefront, checkout, and assistant."""

from __future__ import annotations

import uuid
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from opentelemetry import trace
from sqlalchemy import text

from server.assistant_service import (
    assistant_history_payload,
    assistant_scope_decision as _assistant_scope_decision,
    run_assistant_query,
)
from server.auth_security import SESSION_COOKIE_NAME, require_admin_or_internal_service, require_authenticated_user
from server.config import cfg
from server.database import get_db
from server.modules.attack_simulation import build_attack_story, run_attack_simulation
from server.modules.integrations import sync_customers_from_crm, sync_order_to_crm
from server.modules.java_app_server import JavaAppServerClient
from server.modules.payment_gateway_simulation import authorize_simulated_payment
from server.observability import business_metrics
from server.observability.correlation import apply_span_attributes
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.store_service import (
    ensure_customer,
    fetch_cart_items,
    normalize_checkout_idempotency_key,
    place_order,
    resolve_direct_items,
    update_order_payment_state,
)
from server.storefront import enrich_product

router = APIRouter(prefix="/api/shop", tags=["shop"])


def _trace_id() -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().trace_id:
        return format(span.get_span_context().trace_id, "032x")
    return ""


def _request_has_auth_token(request: Request) -> bool:
    auth_header = request.headers.get("Authorization", "").strip()
    return auth_header.startswith("Bearer ") or bool(request.cookies.get(SESSION_COOKIE_NAME, "").strip())


def _payment_required_flag(value: Any) -> bool:
    return str(value if value is not None else 1).strip().lower() not in {"0", "false", "no"}


async def _optional_checkout_user(db, request: Request) -> dict[str, Any] | None:
    if not _request_has_auth_token(request):
        return None
    token_payload = require_authenticated_user(request)
    result = await db.execute(
        text("SELECT id, username, email, role FROM users WHERE id = :id AND is_active = 1"),
        {"id": int(token_payload["sub"])},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=401, detail="Authenticated checkout user was not found")
    return dict(row)


def _safe_card_summary(card: dict | None) -> dict[str, str]:
    card = card or {}
    number = "".join(ch for ch in str(card.get("number") or "") if ch.isdigit())
    brand = "".join(ch for ch in str(card.get("brand") or "visa").lower() if ch.isalnum() or ch in "-_")[:24]
    return {
        "brand": brand or "visa",
        "last4": number[-4:] if len(number) >= 4 else "4242",
        "token": f"tok_demo_{uuid.uuid4().hex[:12]}",
    }


def _bounded_string(value: object, *, fallback: str, limit: int) -> str:
    text_value = str(value or fallback).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    normalized = " ".join(text_value.split())
    return (normalized or fallback)[:limit]


def assistant_scope_decision(message: str, products: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
    return _assistant_scope_decision(message, products)


def _attack_story(source_ip: str = "203.0.113.77") -> list[dict[str, str]]:
    return build_attack_story(source_ip)


@router.get("/featured")
async def featured_products():
    """Featured products for the landing page."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.featured") as span:
        apply_span_attributes(span, {
            "app.page.name": "shop",
            "app.module": "shop",
            "app.logical_endpoint": "shop.featured",
            "db.target": cfg.database_target_label,
            "db.connection_name": cfg.oracle_dsn,
        })
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, name, sku, description, price, image_url, stock, category "
                    "FROM products WHERE is_active = 1 ORDER BY price DESC FETCH FIRST 8 ROWS ONLY"
                )
            )
            products = [enrich_product(dict(row)) for row in result.mappings().all()]
        span.set_attribute("shop.featured_count", len(products))
        return {"products": products}


@router.get("/storefront")
async def storefront():
    """Full storefront payload sourced from ATP."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.storefront") as span:
        apply_span_attributes(span, {
            "app.page.name": "shop",
            "app.module": "shop",
            "app.logical_endpoint": "shop.storefront",
            "db.target": cfg.database_target_label,
            "db.connection_name": cfg.oracle_dsn,
        })
        crm_sync = await sync_customers_from_crm(force=False, limit=200, source="shop_storefront")
        async with get_db() as db:
            products_result = await db.execute(
                text(
                    "SELECT id, name, sku, description, price, stock, category, image_url "
                    "FROM products WHERE is_active = 1 ORDER BY category, name"
                )
            )
            products = [enrich_product(dict(row)) for row in products_result.mappings().all()]

            categories_result = await db.execute(
                text("SELECT DISTINCT category FROM products WHERE is_active = 1 ORDER BY category")
            )
            categories = [row[0] for row in categories_result.all()]

            stats_result = await db.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM products WHERE is_active = 1) AS product_count, "
                    "(SELECT COALESCE(SUM(stock), 0) FROM products WHERE is_active = 1) AS inventory_units, "
                    "(SELECT COALESCE(SUM(total), 0) FROM orders) AS revenue, "
                    "(SELECT COUNT(*) FROM orders) AS order_count "
                    "FROM DUAL"
                )
            )
            stats = dict(stats_result.mappings().first())

        span.set_attribute("shop.catalog_count", len(products))
        span.set_attribute("shop.category_count", len(categories))
        span.set_attribute("shop.inventory_units", int(stats.get("inventory_units") or 0))
        span.set_attribute("shop.total_revenue", float(stats.get("revenue") or 0))
        span.set_attribute("shop.order_count", int(stats.get("order_count") or 0))
        span.set_attribute("integration.crm_sync_configured", bool(crm_sync.get("configured")))
        return {
            "products": products,
            "categories": categories,
            "stats": {
                "product_count": int(stats["product_count"] or 0),
                "inventory_units": int(stats["inventory_units"] or 0),
                "revenue": float(stats["revenue"] or 0),
                "order_count": int(stats["order_count"] or 0),
            },
            "backend": {
                "database": "oracle_atp",
                "apm_configured": cfg.apm_configured,
                "rum_configured": cfg.rum_configured,
            },
            "crm_sync": crm_sync,
        }


@router.post("/coupon/apply")
async def apply_coupon(payload: dict):
    """Apply a coupon to a candidate subtotal."""
    code = payload.get("code", "")
    subtotal = float(payload.get("subtotal", 0) or 0)
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.coupon.apply") as span:
        apply_span_attributes(span, {
            "shop.coupon_code": code or "none",
            "shop.subtotal": subtotal,
            "app.page.name": "shop",
            "app.module": "shop",
            "app.logical_endpoint": "shop.coupon.apply",
        })
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT code, discount_percent, discount_amount FROM coupons "
                    "WHERE code = :code AND is_active = 1 FETCH FIRST 1 ROWS ONLY"
                ),
                {"code": code},
            )
            coupon = result.mappings().first()

        if not coupon:
            return {"valid": False, "code": code, "discount": 0.0}

        discount = min(
            subtotal,
            subtotal * float(coupon["discount_percent"] or 0) / 100 + float(coupon["discount_amount"] or 0),
        )
        return {"valid": True, "code": code, "discount": round(discount, 2)}


@router.post("/checkout")
async def checkout(payload: dict, request: Request):
    """Persist the order, create shipment records, and emit traces/logs."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.checkout") as span:
        apply_span_attributes(span, {
            "app.page.name": "shop",
            "app.module": "shop",
            "app.logical_endpoint": "shop.checkout",
            "db.target": cfg.database_target_label,
            "db.connection_name": cfg.oracle_dsn,
        })
        session_id = payload.get("session_id") or request.cookies.get("session_id", "") or str(uuid.uuid4())
        try:
            checkout_idempotency_key = normalize_checkout_idempotency_key(
                payload.get("checkout_idempotency_key")
                or payload.get("idempotency_key")
                or request.headers.get("Idempotency-Key", "")
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if checkout_idempotency_key:
            span.set_attribute(
                "orders.checkout_idempotency_key_hash",
                sha256(checkout_idempotency_key.encode("utf-8")).hexdigest()[:16],
            )
        crm_customer_sync = await sync_customers_from_crm(force=False, limit=200, source="shop_checkout")
        async with get_db() as db:
            items = await fetch_cart_items(db, session_id)
            if not items and payload.get("items"):
                items = await resolve_direct_items(db, payload["items"])
            if not items:
                business_metrics.record_checkout(success=False)
                return {"error": "Cart is empty", "session_id": session_id}

            checkout_user = await _optional_checkout_user(db, request)
            if checkout_user:
                span.set_attribute("auth.user_id", int(checkout_user["id"]))
                span.set_attribute("auth.username", str(checkout_user["username"]))
                span.set_attribute("auth.role", str(checkout_user["role"]))
            default_email = str(checkout_user["email"]) if checkout_user else "buyer@octo.local"
            default_name = str(checkout_user["username"]) if checkout_user else "OCTO Buyer"
            customer_email = str(payload.get("customer_email") or default_email)
            customer_name = str(payload.get("customer_name") or default_name)
            customer = await ensure_customer(
                db,
                name=customer_name,
                email=customer_email,
                phone=payload.get("customer_phone", ""),
                company=payload.get("company", ""),
                industry=payload.get("industry", "Drone Operations"),
            )
            order_result = await place_order(
                db,
                customer=customer,
                items=items,
                shipping_address=payload.get("shipping_address", "ATP-backed fulfilment queue"),
                payment_method=payload.get("payment_method", "credit_card"),
                notes=payload.get("notes", ""),
                coupon_code=payload.get("coupon_code", ""),
                session_id=session_id,
                source="shop_checkout",
                trace_id=_trace_id(),
                checkout_idempotency_key=checkout_idempotency_key,
                user_id=int(checkout_user["id"]) if checkout_user else None,
            )
            payment_result = {"status": "skipped", "reason": "idempotent replay"}
            order_payment_state = {
                "payment_status": order_result["order"].get("payment_status", "pending"),
                "order_status": order_result["order"].get("status", "payment_pending"),
                "payment_required": str(order_result["order"].get("payment_required", 1)),
                "payment_gateway_request_id": str(order_result["order"].get("payment_gateway_request_id") or ""),
            }
            if not order_result.get("idempotent_replay"):
                payment_result = await authorize_simulated_payment(
                    order_id=order_result["order"]["id"],
                    total=order_result["total"],
                    currency=cfg.payment_simulation_currency,
                    customer_email=customer["email"],
                    checkout_idempotency_key=checkout_idempotency_key,
                    payment_method=payload.get("payment_method", "credit_card"),
                    payment_details=payload.get("payment_details") if isinstance(payload.get("payment_details"), dict) else {},
                    db=db,
                )
                if payment_result.get("status") not in {"skipped", "unreachable"}:
                    payment_gateway_request_id = str((payment_result.get("payment_gateway") or {}).get("request_id") or "")
                    order_payment_state = await update_order_payment_state(
                        db,
                        order_id=order_result["order"]["id"],
                        payment_provider=str(payment_result.get("provider") or "simulated"),
                        payment_provider_reference=str(payment_result.get("provider_reference") or ""),
                        payment_status=str(payment_result.get("status") or "pending"),
                        payment_gateway_request_id=payment_gateway_request_id,
                    )

        payment_gateway_request_id = str(
            (payment_result.get("payment_gateway") or {}).get("request_id")
            or order_payment_state.get("payment_gateway_request_id")
            or order_result["order"].get("payment_gateway_request_id")
            or ""
        )
        crm_order_sync = await sync_order_to_crm(
            order_id=order_result["order"]["id"],
            customer_email=customer["email"],
            total=order_result["total"],
            source="shop_checkout",
            payment_status=str(order_payment_state.get("payment_status") or payment_result.get("status") or "pending"),
            payment_required=_payment_required_flag(order_payment_state.get("payment_required")),
            payment_method=str(payment_result.get("method") or payload.get("payment_method", "unknown")),
            payment_provider=str(payment_result.get("provider") or ""),
            payment_provider_reference=str(payment_result.get("provider_reference") or ""),
            payment_gateway_request_id=payment_gateway_request_id,
        )
        span.set_attribute("orders.order_id", order_result["order"]["id"])
        span.set_attribute("orders.total", order_result["total"])
        span.set_attribute("orders.item_count", order_result["item_count"])
        span.set_attribute("orders.subtotal", order_result.get("subtotal", order_result["total"]))
        span.set_attribute("orders.discount", float(order_result.get("coupon", {}).get("discount") or 0))
        span.set_attribute("orders.shipping_cost", float(order_result.get("shipping_cost") or 0))
        span.set_attribute("orders.idempotent_replay", bool(order_result.get("idempotent_replay")))
        span.set_attribute("orders.payment_required", _payment_required_flag(order_payment_state.get("payment_required")))
        span.set_attribute("orders.payment_status", str(order_payment_state.get("payment_status") or "pending"))
        span.set_attribute("orders.status", str(order_payment_state.get("order_status") or order_result["order"].get("status", "unknown")))
        span.set_attribute("shop.payment_method", payload.get("payment_method", "unknown"))
        span.set_attribute("browser.trace_id", str(payload.get("browser_trace_id") or ""))
        span.set_attribute("payment.simulation.status", payment_result.get("status", "unknown"))
        span.set_attribute("payment.provider", payment_result.get("provider", "unknown"))
        span.set_attribute("payment.gateway.request_id", payment_gateway_request_id)
        span.set_attribute("payment.card_brand", payment_result.get("card_brand", ""))
        span.set_attribute("payment.card_last4", payment_result.get("card_last4", ""))
        span.set_attribute("payment.wallet_type", payment_result.get("wallet_type", ""))
        span.set_attribute("payment.simulation.risk_score", int(payment_result.get("risk_score") or 0))
        span.set_attribute("payment.simulation.decision_source", payment_result.get("decision_source", "none"))
        span.set_attribute("shop.coupon_code", payload.get("coupon_code", "") or "none")
        span.set_attribute("shop.session_id", session_id)
        span.set_attribute("customer.company", payload.get("company", "") or "")
        span.set_attribute("customer.email_domain", customer_email.split("@")[-1] if "@" in customer_email else "unknown")
        span.set_attribute("integration.crm_order_synced", bool(crm_order_sync.get("synced")))
        business_metrics.record_checkout(success=True)
        if not order_result.get("idempotent_replay"):
            business_metrics.record_order_created(order_result["total"], source="shop_checkout")
        push_log(
            "INFO",
            "Store checkout persisted",
            **{
                "orders.order_id": order_result["order"]["id"],
                "orders.total": order_result["total"],
                "orders.source": "shop_checkout",
                "orders.idempotent_replay": bool(order_result.get("idempotent_replay")),
                "orders.payment_required": _payment_required_flag(order_payment_state.get("payment_required")),
                "orders.payment_status": str(order_payment_state.get("payment_status") or "pending"),
                "orders.status": str(order_payment_state.get("order_status") or order_result["order"].get("status", "unknown")),
                "auth.user_id": int(checkout_user["id"]) if checkout_user else 0,
                "payment.simulation.status": payment_result.get("status", "unknown"),
                "payment.provider": payment_result.get("provider", "unknown"),
                "payment.gateway.request_id": payment_gateway_request_id,
                "payment.method": payment_result.get("method", payload.get("payment_method", "unknown")),
                "payment.card_brand": payment_result.get("card_brand", ""),
                "payment.card_last4": payment_result.get("card_last4", ""),
                "payment.wallet_type": payment_result.get("wallet_type", ""),
                "payment.simulation.risk_score": int(payment_result.get("risk_score") or 0),
                "payment.decision_source": payment_result.get("decision_source", "none"),
                "payment.antifraud_reasons": ",".join(payment_result.get("risk_reasons") or []),
                "shop.session_id": session_id,
                "browser.trace_id": str(payload.get("browser_trace_id") or ""),
                "integration.crm_order_synced": bool(crm_order_sync.get("synced")),
            },
        )
        return {
            "status": "order_placed",
            "order_id": order_result["order"]["id"],
            "tracking_number": order_result["tracking_number"],
            "subtotal": order_result["subtotal"],
            "discount": order_result["coupon"]["discount"],
            "shipping_cost": order_result["shipping_cost"],
            "total": order_result["total"],
            "session_id": session_id,
            "idempotent_replay": bool(order_result.get("idempotent_replay")),
            "trace_id": _trace_id(),
            "order_status": str(order_payment_state.get("order_status") or order_result["order"].get("status", "")),
            "payment_status": str(order_payment_state.get("payment_status") or "pending"),
            "payment_required": _payment_required_flag(order_payment_state.get("payment_required")),
            "authenticated_user": {
                "id": checkout_user["id"],
                "username": checkout_user["username"],
                "email": checkout_user["email"],
            } if checkout_user else None,
            "payment": {
                "status": payment_result.get("status", "skipped"),
                "provider": payment_result.get("provider", ""),
                "method": payment_result.get("method", payload.get("payment_method", "")),
                "card_brand": payment_result.get("card_brand", ""),
                "card_last4": payment_result.get("card_last4", ""),
                "wallet_type": payment_result.get("wallet_type", ""),
                "risk_score": payment_result.get("risk_score", 0),
                "risk_reasons": payment_result.get("risk_reasons", []),
                "decision_source": payment_result.get("decision_source", ""),
                "error_code": payment_result.get("error_code", ""),
                "gateway": payment_result.get("payment_gateway", {}),
            },
            "customer_sync": crm_customer_sync,
            "crm_sync": crm_order_sync,
        }


@router.get("/app-server/health")
async def app_server_health():
    """Health snapshot for the Java APM app-server sidecar."""
    result = await JavaAppServerClient().health()
    return {"java_app_server": result}


@router.post("/app-server/simulate/{scenario}")
async def app_server_simulate(scenario: str, request: Request, payload: dict | None = None):
    """Proxy admin simulations to the Java app-server sidecar."""
    require_admin_or_internal_service(request)
    result = await JavaAppServerClient().simulate(scenario, payload or {})
    return {"java_app_server": result}


@router.post("/payment/simulate/{scenario}")
async def payment_simulate(scenario: str, request: Request, payload: dict | None = None):
    """Generate payment-gateway demo traffic through the Java sidecar."""
    require_admin_or_internal_service(request)
    normalized = scenario.strip().lower()
    if normalized not in {"approve", "decline", "timeout"}:
        raise HTTPException(status_code=400, detail="scenario must be approve, decline, or timeout")
    body = payload or {}
    result = await JavaAppServerClient().authorize_payment(
        order_id=int(body.get("order_id") or 900000),
        amount_minor_units=int(body.get("amount_minor_units") or 1299900),
        currency=str(body.get("currency") or cfg.payment_simulation_currency),
        customer_email=str(body.get("customer_email") or "demo@example.test"),
        idempotency_key_hash=str(body.get("idempotency_key_hash") or f"sim-{normalized}"),
        simulation_mode=normalized,
    )
    business_metrics.record_payment_authorization(
        status=str((result.get("data") or {}).get("decision") or result.get("status") or "unknown"),
        provider="simulated-java-gateway",
        source="admin_payment_simulate",
        risk_score=(result.get("data") or {}).get("risk_score"),
    )
    push_log(
        "WARNING" if normalized != "approve" else "INFO",
        "Payment simulation invoked from admin",
        **{
            "payment.simulation.scenario": normalized,
            "payment.java_app_server.status": result.get("status", "unknown"),
        },
    )
    return {"payment_simulation": {"scenario": normalized, "java_app_server": result}}


@router.post("/demo/storyboard")
async def demo_storyboard(request: Request, payload: dict | None = None):
    """Generate a guided shop journey with order, payment, support, and Java spans."""
    require_admin_or_internal_service(request)
    body = payload or {}
    tracer = get_tracer()
    journey_id = f"story-{uuid.uuid4().hex[:12]}"
    card = _safe_card_summary(body.get("card") if isinstance(body.get("card"), dict) else {})
    source_ip = str(body.get("source_ip") or "198.51.100.42")
    quantity = max(1, min(int(body.get("quantity") or 2), 5))

    with tracer.start_as_current_span("demo.storyboard.shop_journey") as span:
        apply_span_attributes(span, {
            "demo.storyboard.id": journey_id,
            "demo.storyboard.persona": str(body.get("persona") or "Field operations buyer"),
            "client.address": source_ip,
            "payment.card_brand": card["brand"],
            "payment.card_last4": card["last4"],
            "app.module": "shop",
            "app.logical_endpoint": "demo.storyboard.shop_journey",
        })
        async with get_db() as db:
            with tracer.start_as_current_span("demo.storyboard.open_shop"):
                product_rows = await db.execute(
                    text(
                        "SELECT id, name, price FROM products WHERE is_active = 1 "
                        "ORDER BY price DESC FETCH FIRST 2 ROWS ONLY"
                    )
                )
                products = [dict(row) for row in product_rows.mappings().all()]
                if not products:
                    raise HTTPException(status_code=409, detail="no active products available")

            with tracer.start_as_current_span("demo.storyboard.add_drones"):
                items = [
                    {"product_id": int(product["id"]), "quantity": quantity, "price": float(product["price"])}
                    for product in products
                ]

            customer = await ensure_customer(
                db,
                name=str(body.get("customer_name") or "Demo Buyer"),
                email=str(body.get("customer_email") or "demo.buyer@example.test"),
                phone="+1-555-0100",
                company="Octo Field Ops",
                industry="Drone Operations",
            )
            order_result = await place_order(
                db,
                customer=customer,
                items=items,
                shipping_address=str(body.get("shipping_address") or "100 Demo Way, Phoenix, AZ"),
                payment_method="credit_card",
                notes=f"Demo storyboard {journey_id}; card={card['brand']} ending {card['last4']}",
                session_id=f"storyboard-{journey_id}",
                source="demo-storyboard",
                trace_id=_trace_id(),
                checkout_idempotency_key=journey_id,
            )
            order_id = int(order_result["order"]["id"])
            java_quote = await JavaAppServerClient().quote(
                product_id=items[0]["product_id"],
                quantity=items[0]["quantity"],
                base_price_minor_units=int(round(float(items[0]["price"]) * 100)),
            )
            payment = await JavaAppServerClient().authorize_payment(
                order_id=order_id,
                amount_minor_units=int(round(float(order_result["total"]) * 100)),
                currency=str(body.get("currency") or cfg.payment_simulation_currency),
                customer_email=customer["email"],
                idempotency_key_hash=sha256(journey_id.encode("utf-8")).hexdigest()[:16],
                simulation_mode=str(body.get("payment_mode") or "approve"),
            )
            await update_order_payment_state(
                db,
                order_id=order_id,
                payment_provider="simulated-java-gateway",
                payment_provider_reference=card["token"],
                payment_status="authorized" if payment.get("status") == "ok" else "pending",
            )
            await db.execute(
                text(
                    "INSERT INTO tickets (customer_id, title, status, priority, product_id, service_id) "
                    "VALUES (:customer_id, :title, 'open', 'medium', :product_id, null)"
                ),
                {
                    "customer_id": customer["id"],
                    "title": f"Post-purchase support for {products[0]['name']}",
                    "product_id": products[0]["id"],
                },
            )
            ticket_row = await db.execute(
                text("SELECT MAX(id) FROM tickets WHERE customer_id = :customer_id"),
                {"customer_id": customer["id"]},
            )
            ticket_id = int(ticket_row.scalar() or 0)
            if ticket_id:
                await db.execute(
                    text(
                        "INSERT INTO ticket_messages (ticket_id, sender_type, content) "
                        "VALUES (:ticket_id, 'customer', :content)"
                    ),
                    {
                        "ticket_id": ticket_id,
                        "content": "Need battery health and fleet onboarding guidance after demo purchase.",
                    },
                )

        push_log(
            "INFO",
            "Demo storyboard completed",
            **{
                "demo.storyboard.id": journey_id,
                "orders.order_id": order_id,
                "ticket.id": ticket_id,
                "payment.card_brand": card["brand"],
                "payment.card_last4": card["last4"],
                "client.address": source_ip,
            },
        )
        business_metrics.record_order_created(order_result["total"], source="demo-storyboard")
        business_metrics.record_payment_authorization(
            status=str((payment.get("data") or {}).get("decision") or payment.get("status") or "unknown"),
            provider="simulated-java-gateway",
            source="demo-storyboard",
            risk_score=(payment.get("data") or {}).get("risk_score"),
        )
        return {
            "status": "completed",
            "storyboard_id": journey_id,
            "order_id": order_id,
            "ticket_id": ticket_id,
            "products": products,
            "java_quote": java_quote,
            "payment": payment,
            "trace_id": _trace_id(),
        }


@router.post("/attack/simulate")
async def attack_simulate(request: Request, payload: dict | None = None):
    """Generate a full security-lab path with MITRE, OSQuery, log, and Java spans."""
    require_admin_or_internal_service(request)
    return await run_attack_simulation(payload)


@router.get("/wallet")
async def get_wallet(username: str = ""):
    """Show a simple storefront loyalty balance derived from order history."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.wallet.lookup") as span:
        apply_span_attributes(span, {
            "app.page.name": "shop",
            "app.module": "shop",
            "app.logical_endpoint": "shop.wallet.lookup",
            "db.target": cfg.database_target_label,
            "db.connection_name": cfg.oracle_dsn,
        })
        async with get_db() as db:
            if username:
                result = await db.execute(
                    text(
                        "SELECT COALESCE(SUM(total), 0) AS total_spend, COUNT(*) AS order_count "
                        "FROM orders o JOIN customers c ON c.id = o.customer_id "
                        "WHERE lower(c.email) LIKE lower(:username) OR lower(c.name) LIKE lower(:username)"
                    ),
                    {"username": f"%{username}%"},
                )
            else:
                result = await db.execute(
                    text("SELECT COALESCE(SUM(total), 0) AS total_spend, COUNT(*) AS order_count FROM orders")
                )
            wallet = dict(result.mappings().first())

        spend = float(wallet["total_spend"] or 0)
        balance = round(spend * 0.02, 2)
        span.set_attribute("shop.wallet.balance", balance)
        return {
            "username": username or "all-customers",
            "balance": balance,
            "currency": "USD",
            "order_count": int(wallet["order_count"] or 0),
        }


@router.get("/locations")
async def dealer_shops():
    """Fetch authorized dealer locations."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.locations") as span:
        apply_span_attributes(span, {
            "app.page.name": "services",
            "app.module": "shop",
            "app.logical_endpoint": "shop.locations",
            "db.target": cfg.database_target_label,
            "db.connection_name": cfg.oracle_dsn,
        })
        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, name, address, coordinates, contact_email, contact_phone FROM shops WHERE is_active = 1")
            )
            shops = [dict(row) for row in result.mappings().all()]
            span.set_attribute("shop.locations_count", len(shops))
            return {"shops": shops}


@router.get("/assistant/history/{session_id}")
async def assistant_history(session_id: str, request: Request):
    """Return stored assistant conversation messages."""
    require_admin_or_internal_service(request)
    return await assistant_history_payload(session_id)


@router.post("/assistant/query")
async def assistant_query(payload: dict, request: Request):
    """Grounded drone advisor backed by OCI GenAI with ATP conversation history."""
    actor = require_admin_or_internal_service(request)
    surface = "internal-service" if actor.get("role") == "service" else "admin"
    return await run_assistant_query(payload, surface=surface, actor=actor)


@router.get("/captcha")
async def get_captcha():
    """Simple deterministic challenge for the demo storefront."""
    return {"challenge": "What is 12 + 8?", "captcha_id": "shop-demo-12-8"}


@router.post("/captcha/verify")
async def verify_captcha(payload: dict):
    """Verify the demo challenge."""
    return {"valid": str(payload.get("answer", "")) == "20"}
