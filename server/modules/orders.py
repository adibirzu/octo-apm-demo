"""Orders module — cart, checkout, order management.

VULNS: IDOR (view any order), mass assignment (set total), CSRF (no token)
"""

import uuid
from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api", tags=["orders"])


# ── Cart ──────────────────────────────────────────────────────────

@router.get("/cart")
async def get_cart(request: Request, session_id: str = ""):
    """Get cart items for session."""
    tracer = get_tracer()
    sid = session_id or request.cookies.get("session_id", "")

    with tracer.start_as_current_span("orders.get_cart") as span:
        span.set_attribute("cart.session_id", sid)
        if not sid:
            return {"items": [], "total": 0}

        async with get_db() as db:
            result = await db.execute(
                text("SELECT ci.id, ci.quantity, p.name, p.price, p.image_url "
                     "FROM cart_items ci JOIN products p ON ci.product_id = p.id "
                     "WHERE ci.session_id = :sid"),
                {"sid": sid},
            )
            items = [dict(r) for r in result.mappings().all()]

        total = sum(i["price"] * i["quantity"] for i in items)
        return {"items": items, "total": round(total, 2), "session_id": sid}


@router.post("/cart/add")
async def add_to_cart(payload: dict, request: Request):
    """Add item to cart."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.add_to_cart") as span:
        sid = payload.get("session_id") or request.cookies.get("session_id") or str(uuid.uuid4())
        product_id = payload.get("product_id")
        quantity = payload.get("quantity", 1)

        span.set_attribute("cart.product_id", product_id)
        span.set_attribute("cart.quantity", quantity)

        async with get_db() as db:
            await db.execute(
                text("INSERT INTO cart_items (session_id, product_id, quantity) "
                     "VALUES (:sid, :pid, :qty)"),
                {"sid": sid, "pid": product_id, "qty": quantity},
            )

        return {"status": "added", "session_id": sid}


@router.delete("/cart/{item_id}")
async def remove_from_cart(item_id: int):
    """Remove item from cart — no ownership check."""
    async with get_db() as db:
        # VULN: IDOR — can delete any cart item without session validation
        await db.execute(text("DELETE FROM cart_items WHERE id = :id"), {"id": item_id})
    return {"status": "removed"}


# ── Orders ────────────────────────────────────────────────────────

@router.get("/orders")
async def list_orders():
    """List all orders — VULN: No auth, returns all orders."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.list") as span:
        async with get_db() as db:
            # VULN: N+1 query pattern
            result = await db.execute(
                text("SELECT id, customer_id, total, status, created_at FROM orders ORDER BY created_at DESC")
            )
            orders = [dict(r) for r in result.mappings().all()]

            for order in orders:
                items = await db.execute(
                    text("SELECT oi.quantity, p.name, oi.unit_price "
                         "FROM order_items oi JOIN products p ON oi.product_id = p.id "
                         "WHERE oi.order_id = :oid"),
                    {"oid": order["id"]},
                )
                order["items"] = [dict(i) for i in items.mappings().all()]

            span.set_attribute("db.row_count", len(orders))

        return {"orders": orders}


@router.get("/orders/{order_id}")
async def get_order(order_id: int, request: Request):
    """Get order detail — VULN: IDOR (any user can view any order)."""
    tracer = get_tracer()
    with tracer.start_as_current_span("orders.get") as span:
        span.set_attribute("orders.order_id", order_id)

        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM orders WHERE id = :id"), {"id": order_id}
            )
            order = result.mappings().first()

        if not order:
            security_span("idor", severity="medium",
                          payload=str(order_id),
                          source_ip=request.client.host if request.client else "",
                          endpoint=f"/api/orders/{order_id}")
            return {"error": "Order not found"}

        return dict(order)


@router.post("/orders")
async def create_order(payload: dict, request: Request):
    """Create order — VULN: Mass assignment (client can set total)."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("orders.create") as span:
        customer_id = payload.get("customer_id")
        total = payload.get("total", 0)  # VULN: client-controlled total
        notes = payload.get("notes", "")

        if "total" in payload:
            security_span("mass_assign", severity="high",
                          payload=f"total={total}",
                          source_ip=source_ip,
                          endpoint="/api/orders")

        async with get_db() as db:
            result = await db.execute(
                text("INSERT INTO orders (customer_id, total, notes, status) "
                     "VALUES (:cid, :total, :notes, 'pending') RETURNING id"),
                {"cid": customer_id, "total": total, "notes": notes},
            )
            order_id = result.scalar()

        return {"status": "created", "order_id": order_id, "total": total}
