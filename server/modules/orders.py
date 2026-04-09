"""Orders module — ATP-backed cart, checkout, and order history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request
from opentelemetry import trace
from sqlalchemy import text

from server.database import get_db
from server.modules.integrations import sync_customers_from_crm, sync_order_to_crm
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.store_service import (
    compute_subtotal,
    ensure_customer,
    fetch_cart_items,
    place_order,
    resolve_direct_items,
)
from server.storefront import enrich_product

router = APIRouter(prefix="/api", tags=["orders"])


def _trace_id() -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().trace_id:
        return format(span.get_span_context().trace_id, "032x")
    return ""


@router.get("/cart")
async def get_cart(request: Request, session_id: str = ""):
    """Get cart items for the active storefront session."""
    tracer = get_tracer()
    sid = session_id or request.cookies.get("session_id", "")

    with tracer.start_as_current_span("orders.cart.get") as span:
        span.set_attribute("cart.session_id", sid or "anonymous")
        if not sid:
            return {"items": [], "total": 0, "session_id": ""}

        async with get_db() as db:
            items = await fetch_cart_items(db, sid)

        enriched = [enrich_product(item) for item in items]
        total = compute_subtotal(items)
        span.set_attribute("cart.item_count", len(items))
        span.set_attribute("cart.total", total)
        return {"items": enriched, "total": total, "session_id": sid}


@router.post("/cart/add")
async def add_to_cart(payload: dict, request: Request):
    """Add or increment an item in the current cart."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.cart.add") as span:
        sid = payload.get("session_id") or request.cookies.get("session_id") or str(uuid.uuid4())
        source_ip = request.client.host if request.client else "unknown"
        try:
            product_id = int(payload.get("product_id"))
        except (TypeError, ValueError):
            security_span(
                "mass_assign",
                severity="high",
                payload=str(payload.get("product_id", "")),
                source_ip=source_ip,
                endpoint="/api/cart/add",
                session_id=sid,
            )
            return {"error": "Invalid product id", "session_id": sid}
        try:
            quantity = max(int(payload.get("quantity", 1) or 1), 1)
        except (TypeError, ValueError):
            security_span(
                "mass_assign",
                severity="medium",
                payload=f"invalid_quantity={payload.get('quantity')}",
                source_ip=source_ip,
                endpoint="/api/cart/add",
                product_id=product_id,
                session_id=sid,
            )
            return {"error": "Invalid quantity", "session_id": sid}

        span.set_attribute("cart.session_id", sid)
        span.set_attribute("cart.product_id", product_id)
        span.set_attribute("cart.quantity", quantity)
        if quantity > 20:
            security_span(
                "rate_limit",
                severity="high",
                payload=f"product_id={product_id}; quantity={quantity}",
                source_ip=source_ip,
                endpoint="/api/cart/add",
                product_id=product_id,
                session_id=sid,
            )
            return {"error": "Quantity exceeds allowed threshold", "session_id": sid}

        async with get_db() as db:
            product_lookup = await db.execute(
                text(
                    "SELECT id, stock, is_active FROM products "
                    "WHERE id = :product_id FETCH FIRST 1 ROWS ONLY"
                ),
                {"product_id": product_id},
            )
            product = product_lookup.mappings().first()
            if not product or int(product.get("is_active") or 0) != 1:
                security_span(
                    "idor",
                    severity="medium",
                    payload=f"missing_product={product_id}",
                    source_ip=source_ip,
                    endpoint="/api/cart/add",
                    product_id=product_id,
                    session_id=sid,
                )
                return {"error": "Product not found", "session_id": sid}

            if int(product.get("stock") or 0) <= 0:
                return {"error": "Product is out of stock", "session_id": sid}

            existing = await db.execute(
                text(
                    "SELECT id, quantity FROM cart_items WHERE session_id = :sid "
                    "AND product_id = :product_id FETCH FIRST 1 ROWS ONLY"
                ),
                {"sid": sid, "product_id": product_id},
            )
            row = existing.mappings().first()
            if row:
                await db.execute(
                    text("UPDATE cart_items SET quantity = quantity + :quantity WHERE id = :id"),
                    {"quantity": quantity, "id": row["id"]},
                )
            else:
                await db.execute(
                    text(
                        "INSERT INTO cart_items (session_id, product_id, quantity) "
                        "VALUES (:sid, :product_id, :quantity)"
                    ),
                    {"sid": sid, "product_id": product_id, "quantity": quantity},
                )

        push_log("INFO", "Cart updated", **{"cart.session_id": sid, "cart.product_id": product_id})
        return {"status": "added", "session_id": sid}


@router.delete("/cart/{item_id}")
async def remove_from_cart(item_id: int, request: Request):
    """Remove an item from the current cart."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.cart.remove") as span:
        span.set_attribute("cart.item_id", item_id)
        async with get_db() as db:
            await db.execute(text("DELETE FROM cart_items WHERE id = :id"), {"id": item_id})
        return {"status": "removed", "item_id": item_id}


@router.get("/orders")
async def list_orders(limit: int = Query(default=100, ge=1, le=500)):
    """List recent orders with their item details and pricing breakdown."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.list") as span:
        span.set_attribute("orders.limit", limit)
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT o.id, o.customer_id, c.name AS customer_name, c.email AS customer_email, "
                    "o.total, o.status, o.shipping_address, o.created_at, "
                    "COALESCE((SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi "
                    "WHERE oi.order_id = o.id), 0) AS subtotal, "
                    "COALESCE((SELECT s.shipping_cost FROM shipments s WHERE s.order_id = o.id "
                    "ORDER BY s.created_at DESC FETCH FIRST 1 ROWS ONLY), 0) AS shipping_cost "
                    "FROM orders o LEFT JOIN customers c ON c.id = o.customer_id "
                    "ORDER BY o.created_at DESC "
                    f"FETCH FIRST {limit} ROWS ONLY"
                )
            )
            orders = [dict(row) for row in result.mappings().all()]

            for order in orders:
                shipping_cost = round(float(order.get("shipping_cost") or 0.0), 2)
                subtotal = round(float(order.get("subtotal") or 0.0), 2)
                discount = round(
                    max(subtotal + shipping_cost - float(order.get("total") or 0.0), 0.0),
                    2,
                )
                order["shipping_cost"] = shipping_cost
                order["discount"] = discount
                order["subtotal"] = subtotal
                items = await db.execute(
                    text(
                        "SELECT oi.product_id, oi.quantity, oi.unit_price, p.name, p.sku, p.description, p.stock, p.category, p.image_url "
                        "FROM order_items oi JOIN products p ON p.id = oi.product_id "
                        "WHERE oi.order_id = :order_id"
                    ),
                    {"order_id": order["id"]},
                )
                order["items"] = [enrich_product(dict(item)) for item in items.mappings().all()]

            span.set_attribute("orders.count", len(orders))
        return {"orders": orders}


@router.get("/orders/{order_id}")
async def get_order(order_id: int):
    """Get a single order and its shipment detail."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.get") as span:
        span.set_attribute("orders.order_id", order_id)
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT o.id, o.customer_id, c.name AS customer_name, c.email AS customer_email, "
                    "o.total, o.status, o.shipping_address, o.notes, o.created_at "
                    "FROM orders o LEFT JOIN customers c ON c.id = o.customer_id WHERE o.id = :id"
                ),
                {"id": order_id},
            )
            order = result.mappings().first()
            if not order:
                return {"error": "Order not found", "order_id": order_id}

            items = await db.execute(
                text(
                    "SELECT oi.product_id, oi.quantity, oi.unit_price, p.name, p.sku, p.description, p.stock, p.category, p.image_url "
                    "FROM order_items oi JOIN products p ON p.id = oi.product_id "
                    "WHERE oi.order_id = :order_id"
                ),
                {"order_id": order_id},
            )
            shipment = await db.execute(
                text(
                    "SELECT tracking_number, carrier, status, shipping_cost, created_at "
                    "FROM shipments WHERE order_id = :order_id ORDER BY created_at DESC FETCH FIRST 1 ROWS ONLY"
                ),
                {"order_id": order_id},
            )

        payload = dict(order)
        payload["items"] = [enrich_product(dict(item)) for item in items.mappings().all()]
        payload["shipment"] = shipment.mappings().first()
        return payload


@router.post("/orders")
async def create_order(payload: dict, request: Request):
    """Create an order from either the cart session or a direct item list."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.create") as span:
        session_id = payload.get("session_id") or request.cookies.get("session_id", "")
        coupon_code = payload.get("coupon_code", "")
        shipping_address = payload.get("shipping_address", "")
        notes = payload.get("notes", "")
        customer_sync = await sync_customers_from_crm(force=False, limit=200, source="orders_api")

        async with get_db() as db:
            if session_id:
                items = await fetch_cart_items(db, session_id)
            else:
                items = await resolve_direct_items(db, payload.get("items", []))

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
                shipping_address=shipping_address or "ATP-backed fulfilment queue",
                notes=notes,
                coupon_code=coupon_code,
                session_id=session_id,
                source="orders_api",
                trace_id=_trace_id(),
            )

        crm_sync = await sync_order_to_crm(
            order_id=order_result["order"]["id"],
            customer_email=customer["email"],
            total=order_result["total"],
            source="orders_api",
        )
        span.set_attribute("orders.order_id", order_result["order"]["id"])
        span.set_attribute("orders.total", order_result["total"])
        span.set_attribute("orders.item_count", order_result["item_count"])
        span.set_attribute("integration.crm_order_synced", bool(crm_sync.get("synced")))
        push_log(
            "INFO",
            "Order persisted in backend",
            **{
                "orders.order_id": order_result["order"]["id"],
                "orders.total": order_result["total"],
                "orders.source": "orders_api",
                "integration.crm_order_synced": bool(crm_sync.get("synced")),
            },
        )
        return {
            "status": "created",
            "order_id": order_result["order"]["id"],
            "tracking_number": order_result["tracking_number"],
            "total": order_result["total"],
            "subtotal": order_result["subtotal"],
            "discount": order_result["coupon"]["discount"],
            "shipping_cost": order_result["shipping_cost"],
            "session_id": session_id,
            "customer_sync": customer_sync,
            "crm_sync": crm_sync,
        }
