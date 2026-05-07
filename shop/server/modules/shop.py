"""Shop module — OCTO Drone Shop storefront, checkout, and assistant."""

from __future__ import annotations

import uuid
import time
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from opentelemetry import trace
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from server.config import cfg
from server.database import get_db
from server.genai_service import chat_with_documents, genai_configured
from server.modules.attack_simulation import build_attack_story, run_attack_simulation
from server.modules.integrations import sync_customers_from_crm, sync_order_to_crm
from server.modules.java_app_server import JavaAppServerClient
from server.modules.payment_gateway_simulation import authorize_simulated_payment
from server.observability import business_metrics, llmetry
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
from server.storefront import build_grounding_documents, enrich_product, fallback_product_answer

router = APIRouter(prefix="/api/shop", tags=["shop"])

_ASSISTANT_SCOPE = "drone_specs"
_ASSISTANT_REFUSAL = (
    "I can only answer questions about OCTO drone specs, payloads, sensors, stock, "
    "pricing, checkout options, and mission fit."
)
_ASSISTANT_ALLOWED_TERMS = {
    "drone", "drones", "uav", "uas", "quadcopter", "octocopter", "vtol", "fpv",
    "platform", "airframe", "payload", "payloads", "sensor", "sensors", "camera",
    "thermal", "lidar", "rtk", "ppk", "gnss", "gimbal", "radio", "mesh", "range",
    "endurance", "flight", "battery", "batteries", "propeller", "props", "motor",
    "esc", "controller", "pixhawk", "mapping", "survey", "inspection", "cinema",
    "agriculture", "public safety", "search", "rescue", "ndaa", "stock", "price",
    "pricing", "cost", "sku", "catalog", "compare", "recommend", "mission",
    "spec", "specs", "shipping", "lead time", "checkout", "payment", "warranty",
    "skydio", "parrot", "anafi", "autel", "wingtra", "trinity", "flyability",
    "elios", "freefly", "astro", "teledyne", "flir", "siras", "gremsy",
    "holybro", "iflight", "foxtech", "tattu", "sony", "doodle",
}
_ASSISTANT_BLOCKED_TERMS = {
    "ignore previous", "ignore the previous", "system prompt", "developer message",
    "secret", "password", "api key", "token", "jailbreak", "malware", "exploit",
    "drop table", "delete from", "credit card number", "ssn",
}


def _trace_id() -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().trace_id:
        return format(span.get_span_context().trace_id, "032x")
    return ""


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


def _product_terms(products: list[dict[str, Any]]) -> set[str]:
    terms: set[str] = set()
    for product in products:
        sku = str(product.get("sku") or "").strip().lower()
        name = str(product.get("name") or "").strip().lower()
        category = str(product.get("category") or "").strip().lower()
        if sku:
            terms.add(sku)
        if name:
            terms.add(name)
            name_parts = [part for part in name.replace("-", " ").split() if len(part) >= 5]
            if len(name_parts) >= 2:
                terms.update(name_parts[:3])
        if category:
            terms.add(category)
    return terms


def assistant_scope_decision(message: str, products: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
    """Return whether the advisor can answer without leaving drone catalog scope."""
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return False, "empty_message"
    if any(term in normalized for term in _ASSISTANT_BLOCKED_TERMS):
        return False, "blocked_term"
    product_terms = _product_terms(products or [])
    if any(term and term in normalized for term in product_terms):
        return True, "catalog_product"
    if any(term in normalized for term in _ASSISTANT_ALLOWED_TERMS):
        return True, "drone_domain_keyword"
    return False, "out_of_scope"


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
                "genai_configured": genai_configured(),
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

            customer = await ensure_customer(
                db,
                name=payload.get("customer_name", "OCTO Buyer"),
                email=payload.get("customer_email", "buyer@octo.local"),
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
            )
            payment_result = {"status": "skipped", "reason": "idempotent replay"}
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
                    await update_order_payment_state(
                        db,
                        order_id=order_result["order"]["id"],
                        payment_provider=str(payment_result.get("provider") or "simulated"),
                        payment_provider_reference=str(payment_result.get("provider_reference") or ""),
                        payment_status=str(payment_result.get("status") or "pending"),
                    )

        crm_order_sync = await sync_order_to_crm(
            order_id=order_result["order"]["id"],
            customer_email=customer["email"],
            total=order_result["total"],
            source="shop_checkout",
        )
        span.set_attribute("orders.order_id", order_result["order"]["id"])
        span.set_attribute("orders.total", order_result["total"])
        span.set_attribute("orders.item_count", order_result["item_count"])
        span.set_attribute("orders.subtotal", order_result.get("subtotal", order_result["total"]))
        span.set_attribute("orders.discount", float(order_result.get("coupon", {}).get("discount") or 0))
        span.set_attribute("orders.shipping_cost", float(order_result.get("shipping_cost") or 0))
        span.set_attribute("orders.idempotent_replay", bool(order_result.get("idempotent_replay")))
        span.set_attribute("shop.payment_method", payload.get("payment_method", "unknown"))
        span.set_attribute("payment.simulation.status", payment_result.get("status", "unknown"))
        span.set_attribute("payment.provider", payment_result.get("provider", "unknown"))
        span.set_attribute("payment.card_brand", payment_result.get("card_brand", ""))
        span.set_attribute("payment.card_last4", payment_result.get("card_last4", ""))
        span.set_attribute("payment.wallet_type", payment_result.get("wallet_type", ""))
        span.set_attribute("payment.simulation.risk_score", int(payment_result.get("risk_score") or 0))
        span.set_attribute("payment.simulation.decision_source", payment_result.get("decision_source", "none"))
        span.set_attribute("shop.coupon_code", payload.get("coupon_code", "") or "none")
        span.set_attribute("shop.session_id", session_id)
        span.set_attribute("customer.company", payload.get("company", "") or "")
        span.set_attribute("customer.email_domain", (payload.get("customer_email") or "").split("@")[-1] or "unknown")
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
                "payment.simulation.status": payment_result.get("status", "unknown"),
                "payment.provider": payment_result.get("provider", "unknown"),
                "payment.method": payment_result.get("method", payload.get("payment_method", "unknown")),
                "payment.card_brand": payment_result.get("card_brand", ""),
                "payment.card_last4": payment_result.get("card_last4", ""),
                "payment.wallet_type": payment_result.get("wallet_type", ""),
                "payment.simulation.risk_score": int(payment_result.get("risk_score") or 0),
                "payment.decision_source": payment_result.get("decision_source", "none"),
                "payment.antifraud_reasons": ",".join(payment_result.get("risk_reasons") or []),
                "shop.session_id": session_id,
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
async def app_server_simulate(scenario: str, payload: dict | None = None):
    """Proxy admin simulations to the Java app-server sidecar."""
    result = await JavaAppServerClient().simulate(scenario, payload or {})
    return {"java_app_server": result}


@router.post("/payment/simulate/{scenario}")
async def payment_simulate(scenario: str, payload: dict | None = None):
    """Generate payment-gateway demo traffic through the Java sidecar."""
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
async def demo_storyboard(payload: dict | None = None):
    """Generate a guided shop journey with order, payment, support, and Java spans."""
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
async def attack_simulate(payload: dict | None = None):
    """Generate a full security-lab path with MITRE, OSQuery, log, and Java spans."""
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
async def assistant_history(session_id: str):
    """Return stored assistant conversation messages."""
    async with get_db() as db:
        messages = await db.execute(
            text(
                "SELECT role, content, provider, model_id, created_at "
                "FROM assistant_messages WHERE session_id = :session_id ORDER BY created_at ASC"
            ),
            {"session_id": session_id},
        )
        return {"session_id": session_id, "messages": [dict(row) for row in messages.mappings().all()]}


@router.post("/assistant/query")
async def assistant_query(payload: dict, request: Request):
    """Grounded drone advisor backed by OCI GenAI with ATP conversation history."""
    message = payload.get("message", "").strip()
    if not message:
        return {"error": "Message is required"}

    session_id = payload.get("session_id") or str(uuid.uuid4())
    assistant_started = time.monotonic()
    assistant_outcome = "success"
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.assistant.query") as span:
        apply_span_attributes(span, {
            "assistant.session_id": session_id,
            "assistant.message_length": len(message),
            "assistant.product_focus": payload.get("product_focus", "") or "all",
            "assistant.customer_email_provided": bool(payload.get("customer_email")),
            "app.page.name": "shop",
            "app.module": "shop",
            "app.logical_endpoint": "shop.assistant.query",
            "db.target": cfg.database_target_label,
            "db.connection_name": cfg.oracle_dsn,
        })

        async with get_db() as db:
            existing = await db.execute(
                text(
                    "SELECT session_id FROM assistant_sessions WHERE session_id = :session_id "
                    "FETCH FIRST 1 ROWS ONLY"
                ),
                {"session_id": session_id},
            )
            if not existing.first():
                try:
                    await db.execute(
                        text(
                            "INSERT INTO assistant_sessions (session_id, customer_email, product_focus, source) "
                            "VALUES (:session_id, :customer_email, :product_focus, 'shop')"
                        ),
                        {
                            "session_id": session_id,
                            "customer_email": payload.get("customer_email", ""),
                            "product_focus": payload.get("product_focus", ""),
                        },
                    )
                except IntegrityError:
                    await db.rollback()

            query = (
                "SELECT id, name, sku, description, price, stock, category, image_url "
                "FROM products WHERE is_active = 1"
            )
            params = {}
            if payload.get("product_focus"):
                query += " AND (lower(name) LIKE lower(:focus) OR lower(category) LIKE lower(:focus))"
                params["focus"] = f"%{payload['product_focus']}%"
            query += " ORDER BY price DESC FETCH FIRST 8 ROWS ONLY"
            products_result = await db.execute(text(query), params)
            products = [enrich_product(dict(row)) for row in products_result.mappings().all()]
            documents = build_grounding_documents(products)
            guardrail_allowed, guardrail_reason = assistant_scope_decision(message, products)
            apply_span_attributes(span, {
                "assistant.guardrail.scope": _ASSISTANT_SCOPE,
                "assistant.guardrail.allowed": guardrail_allowed,
                "assistant.guardrail.reason": guardrail_reason,
                "assistant.documents_grounded": len(documents),
            })

            await db.execute(
                text(
                    "INSERT INTO assistant_messages (session_id, role, content, provider, model_id, trace_id) "
                    "VALUES (:session_id, 'user', :content, 'client', '', :trace_id)"
                ),
                {
                    "session_id": session_id,
                    "content": message,
                    "trace_id": _trace_id(),
                },
            )

        response_payload = None
        if not guardrail_allowed:
            assistant_outcome = "guardrail_blocked"
            response_payload = {
                "answer": _ASSISTANT_REFUSAL,
                "provider": "guardrail_scope_filter",
                "model_id": "drone-spec-scope",
                "usage": {},
            }
        elif genai_configured():
            with tracer.start_as_current_span("shop.assistant.genai") as genai_span:
                genai_started = time.monotonic()
                try:
                    apply_span_attributes(genai_span, {
                        "assistant.guardrail.scope": _ASSISTANT_SCOPE,
                        "assistant.guardrail.allowed": True,
                        "assistant.documents_grounded": len(documents),
                        "gen_ai.system": "oci_genai",
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model": cfg.oci_genai_model_id,
                        "llm.system": "oci_genai",
                        "llm.model": cfg.oci_genai_model_id,
                    })
                    response_payload = await chat_with_documents(message, documents)
                    llmetry.record_assistant_observation(
                        span=genai_span,
                        emit_log=False,
                        record_metric=False,
                        session_id=session_id,
                        message=message,
                        answer=response_payload.get("answer", ""),
                        provider=response_payload.get("provider", "oci_genai"),
                        model_id=response_payload.get("model_id", cfg.oci_genai_model_id),
                        usage=response_payload.get("usage") or {},
                        documents_grounded=len(documents),
                        guardrail_allowed=True,
                        guardrail_reason=guardrail_reason,
                        latency_ms=(time.monotonic() - genai_started) * 1000,
                        outcome="success",
                        customer_email=payload.get("customer_email", ""),
                    )
                except Exception as exc:
                    assistant_outcome = "fallback"
                    genai_span.record_exception(exc)
                    genai_span.set_attribute("assistant.outcome", "error")
                    genai_span.set_attribute("otel.status_code", "ERROR")
                    llmetry.record_assistant_observation(
                        span=genai_span,
                        emit_log=False,
                        record_metric=False,
                        session_id=session_id,
                        message=message,
                        answer="",
                        provider="oci_genai",
                        model_id=cfg.oci_genai_model_id,
                        usage={},
                        documents_grounded=len(documents),
                        guardrail_allowed=True,
                        guardrail_reason=guardrail_reason,
                        latency_ms=(time.monotonic() - genai_started) * 1000,
                        outcome="error",
                        error_type=exc.__class__.__name__,
                        customer_email=payload.get("customer_email", ""),
                    )
                    push_log(
                        "ERROR",
                        f"OCI GenAI assistant failed: {exc}",
                        **{
                            "assistant.session_id": session_id,
                            "assistant.provider": "oci_genai",
                            "assistant.outcome": "error",
                            "llmetry.error_type": exc.__class__.__name__,
                        },
                    )

        if response_payload is None:
            if assistant_outcome == "success":
                assistant_outcome = "fallback"
            response_payload = {
                "answer": fallback_product_answer(message, products),
                "provider": "local_grounded_fallback",
                "model_id": "atp-catalog",
                "usage": {},
            }

        llmetry_event = llmetry.record_assistant_observation(
            span=span,
            emit_log=True,
            record_metric=True,
            session_id=session_id,
            message=message,
            answer=response_payload["answer"],
            provider=response_payload["provider"],
            model_id=response_payload["model_id"],
            usage=response_payload.get("usage") or {},
            documents_grounded=len(documents),
            guardrail_allowed=guardrail_allowed,
            guardrail_reason=guardrail_reason,
            latency_ms=(time.monotonic() - assistant_started) * 1000,
            outcome=assistant_outcome,
            customer_email=payload.get("customer_email", ""),
        )

        async with get_db() as db:
            await db.execute(
                text(
                    "INSERT INTO assistant_messages (session_id, role, content, provider, model_id, trace_id) "
                    "VALUES (:session_id, 'assistant', :content, :provider, :model_id, :trace_id)"
                ),
                {
                    "session_id": session_id,
                    "content": response_payload["answer"],
                    "provider": response_payload["provider"],
                    "model_id": response_payload["model_id"],
                    "trace_id": _trace_id(),
                },
            )
            await llmetry.persist_assistant_observation(db, llmetry_event)

        span.set_attribute("assistant.provider", response_payload["provider"])
        span.set_attribute("assistant.genai_used", response_payload["provider"] == "oci_genai")
        span.set_attribute("assistant.documents_grounded", len(documents))
        span.set_attribute("assistant.guardrail.allowed", guardrail_allowed)
        span.set_attribute("assistant.guardrail.reason", guardrail_reason)
        span.set_attribute("assistant.guardrail.scope", _ASSISTANT_SCOPE)
        usage = response_payload.get("usage") or {}
        if usage.get("input_tokens") is not None:
            span.set_attribute("llm.token.prompt", int(usage["input_tokens"]))
        if usage.get("output_tokens") is not None:
            span.set_attribute("llm.token.completion", int(usage["output_tokens"]))
        if usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
            span.set_attribute("llm.token.total", int(usage["input_tokens"]) + int(usage["output_tokens"]))
        push_log(
            "INFO",
            "Assistant response generated",
            **{
                "assistant.session_id": session_id,
                "assistant.provider": response_payload["provider"],
                "assistant.model_id": response_payload["model_id"],
                "assistant.guardrail.scope": _ASSISTANT_SCOPE,
                "assistant.guardrail.allowed": guardrail_allowed,
                "assistant.guardrail.reason": guardrail_reason,
                "assistant.outcome": assistant_outcome,
            },
        )
        return {
            "session_id": session_id,
            "answer": response_payload["answer"],
            "provider": response_payload["provider"],
            "model_id": response_payload["model_id"],
            "usage": response_payload.get("usage", {}),
            "documents_used": len(documents),
        }


@router.get("/captcha")
async def get_captcha():
    """Simple deterministic challenge for the demo storefront."""
    return {"challenge": "What is 12 + 8?", "captcha_id": "shop-demo-12-8"}


@router.post("/captcha/verify")
async def verify_captcha(payload: dict):
    """Verify the demo challenge."""
    return {"valid": str(payload.get("answer", "")) == "20"}
