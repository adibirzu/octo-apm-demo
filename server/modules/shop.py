"""Shop module — OCTO Drone Shop storefront, checkout, and assistant."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from opentelemetry import trace
from sqlalchemy import text

from server.config import cfg
from server.database import get_db
from server.genai_service import chat_with_documents, genai_configured
from server.modules.integrations import sync_customers_from_crm, sync_order_to_crm
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.store_service import ensure_customer, fetch_cart_items, place_order
from server.storefront import build_grounding_documents, enrich_product, fallback_product_answer

router = APIRouter(prefix="/api/shop", tags=["shop"])


def _trace_id() -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().trace_id:
        return format(span.get_span_context().trace_id, "032x")
    return ""


@router.get("/featured")
async def featured_products():
    """Featured products for the landing page."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.featured") as span:
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
                    "(SELECT COUNT(*) FROM orders) AS order_count"
                    "FROM DUAL"
                )
            )
            stats = dict(stats_result.mappings().first())

        span.set_attribute("shop.catalog_count", len(products))
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
        span.set_attribute("shop.coupon_code", code or "none")
        span.set_attribute("shop.subtotal", subtotal)
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
        session_id = payload.get("session_id") or request.cookies.get("session_id", "") or str(uuid.uuid4())
        crm_customer_sync = await sync_customers_from_crm(force=False, limit=200, source="shop_checkout")
        async with get_db() as db:
            items = await fetch_cart_items(db, session_id)
            if not items:
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
        span.set_attribute("integration.crm_order_synced", bool(crm_order_sync.get("synced")))
        push_log(
            "INFO",
            "Store checkout persisted",
            **{
                "orders.order_id": order_result["order"]["id"],
                "orders.total": order_result["total"],
                "orders.source": "shop_checkout",
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
            "customer_sync": crm_customer_sync,
            "crm_sync": crm_order_sync,
        }


@router.get("/wallet")
async def get_wallet(username: str = ""):
    """Show a simple storefront loyalty balance derived from order history."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.wallet.lookup") as span:
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
    tracer = get_tracer()
    with tracer.start_as_current_span("shop.assistant.query") as span:
        span.set_attribute("assistant.session_id", session_id)
        span.set_attribute("assistant.message_length", len(message))

        async with get_db() as db:
            existing = await db.execute(
                text(
                    "SELECT session_id FROM assistant_sessions WHERE session_id = :session_id "
                    "FETCH FIRST 1 ROWS ONLY"
                ),
                {"session_id": session_id},
            )
            if not existing.first():
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
        if genai_configured():
            try:
                with tracer.start_as_current_span("shop.assistant.genai") as genai_span:
                    response_payload = await chat_with_documents(message, documents)
                    genai_span.set_attribute("assistant.provider", response_payload["provider"])
                    genai_span.set_attribute("assistant.model_id", response_payload["model_id"])
            except Exception as exc:
                push_log("ERROR", f"OCI GenAI assistant failed: {exc}")

        if response_payload is None:
            response_payload = {
                "answer": fallback_product_answer(message, products),
                "provider": "local_grounded_fallback",
                "model_id": "atp-catalog",
                "usage": {},
            }

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

        span.set_attribute("assistant.provider", response_payload["provider"])
        push_log(
            "INFO",
            "Assistant response generated",
            **{
                "assistant.session_id": session_id,
                "assistant.provider": response_payload["provider"],
                "assistant.model_id": response_payload["model_id"],
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
