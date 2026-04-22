"""Store backend helpers for ATP-backed cart and order processing."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def fetch_cart_items(db, session_id: str) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            "SELECT ci.id, ci.product_id, ci.quantity, p.name, p.sku, p.description, p.price, "
            "p.stock, p.category, p.image_url "
            "FROM cart_items ci JOIN products p ON ci.product_id = p.id "
            "WHERE ci.session_id = :sid ORDER BY ci.created_at DESC"
        ),
        {"sid": session_id},
    )
    return [dict(row) for row in result.mappings().all()]


def compute_subtotal(items: list[dict[str, Any]]) -> float:
    return round(sum(float(item["price"]) * int(item["quantity"]) for item in items), 2)


async def ensure_customer(
    db,
    *,
    name: str,
    email: str,
    phone: str = "",
    company: str = "",
    industry: str = "Drone Operations",
) -> dict[str, Any]:
    existing = await db.execute(
        text("SELECT id, name, email FROM customers WHERE lower(email) = lower(:email)"),
        {"email": email},
    )
    customer = existing.mappings().first()
    if customer:
        await db.execute(
            text(
                "UPDATE customers SET name = :name, phone = :phone, company = :company, "
                "industry = :industry, updated_at = CURRENT_TIMESTAMP WHERE id = :id"
            ),
            {
                "id": customer["id"],
                "name": name,
                "phone": phone,
                "company": company,
                "industry": industry,
            },
        )
        return {"id": customer["id"], "name": name, "email": email}

    await db.execute(
        text(
            "INSERT INTO customers (name, email, phone, company, industry) "
            "VALUES (:name, :email, :phone, :company, :industry)"
        ),
        {"name": name, "email": email, "phone": phone, "company": company, "industry": industry},
    )
    lookup = await db.execute(
        text(
            "SELECT id, name, email FROM customers WHERE lower(email) = lower(:email) "
            "ORDER BY created_at DESC FETCH FIRST 1 ROWS ONLY"
        ),
        {"email": email},
    )
    created = lookup.mappings().first()
    return {"id": created["id"], "name": created["name"], "email": created["email"]}


async def resolve_direct_items(db, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []

    resolved: list[dict[str, Any]] = []
    for item in items:
        product_id = item.get("product_id")
        quantity = max(int(item.get("quantity", 1) or 1), 1)
        product_row = await db.execute(
            text(
                "SELECT id, name, sku, description, price, stock, category, image_url "
                "FROM products WHERE id = :id AND is_active = 1"
            ),
            {"id": product_id},
        )
        product = product_row.mappings().first()
        if not product:
            continue
        resolved.append({**dict(product), "product_id": product["id"], "quantity": quantity})
    return resolved


async def apply_coupon(db, code: str, subtotal: float) -> dict[str, Any]:
    if not code:
        return {"code": "", "discount": 0.0, "valid": False}

    result = await db.execute(
        text(
            "SELECT code, discount_percent, discount_amount, used_count, max_uses "
            "FROM coupons WHERE code = :code AND is_active = 1"
        ),
        {"code": code},
    )
    coupon = result.mappings().first()
    if not coupon:
        return {"code": code, "discount": 0.0, "valid": False}

    if int(coupon["max_uses"] or 0) and int(coupon["used_count"] or 0) >= int(coupon["max_uses"]):
        return {"code": code, "discount": 0.0, "valid": False}

    percent_discount = subtotal * float(coupon["discount_percent"] or 0) / 100
    amount_discount = float(coupon["discount_amount"] or 0)
    discount = round(min(subtotal, percent_discount + amount_discount), 2)
    await db.execute(
        text("UPDATE coupons SET used_count = COALESCE(used_count, 0) + 1 WHERE code = :code"),
        {"code": code},
    )
    return {"code": code, "discount": discount, "valid": True}


async def place_order(
    db,
    *,
    customer: dict[str, Any],
    items: list[dict[str, Any]],
    shipping_address: str,
    payment_method: str = "credit_card",
    notes: str = "",
    coupon_code: str = "",
    session_id: str = "",
    source: str = "shop",
    trace_id: str = "",
) -> dict[str, Any]:
    subtotal = compute_subtotal(items)
    coupon = await apply_coupon(db, coupon_code, subtotal)
    shipping_cost = 0.0 if subtotal >= 5000 else 149.0 if subtotal else 0.0
    total = round(max(subtotal - float(coupon["discount"]), 0) + shipping_cost, 2)

    await db.execute(
        text(
            "INSERT INTO orders (customer_id, total, status, payment_method, payment_status, notes, shipping_address) "
            "VALUES (:customer_id, :total, :status, :payment_method, :payment_status, :notes, :shipping_address)"
        ),
        {
            "customer_id": customer["id"],
            "total": total,
            "status": "processing",
            "payment_method": payment_method,
            "payment_status": "completed" if payment_method in ["credit_card", "crypto"] else "pending",
            "notes": notes or f"Source={source}; Coupon={coupon_code or 'none'}",
            "shipping_address": shipping_address,
        },
    )
    order_lookup = await db.execute(
        text(
            "SELECT id, total, status, created_at FROM orders WHERE customer_id = :customer_id "
            "ORDER BY created_at DESC FETCH FIRST 1 ROWS ONLY"
        ),
        {"customer_id": customer["id"]},
    )
    order = dict(order_lookup.mappings().first())

    for item in items:
        await db.execute(
            text(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                "VALUES (:order_id, :product_id, :quantity, :unit_price)"
            ),
            {
                "order_id": order["id"],
                "product_id": item["product_id"],
                "quantity": int(item["quantity"]),
                "unit_price": float(item["price"]),
            },
        )
        await db.execute(
            text(
                "UPDATE products SET stock = CASE WHEN stock >= :quantity THEN stock - :quantity ELSE stock END "
                "WHERE id = :product_id"
            ),
            {"product_id": item["product_id"], "quantity": int(item["quantity"])},
        )

    tracking_number = f"OCTO-{order['id']:06d}"
    await db.execute(
        text(
            "INSERT INTO shipments (order_id, tracking_number, carrier, status, origin_region, "
            "destination_region, weight_kg, shipping_cost) "
            "VALUES (:order_id, :tracking_number, 'dhl', 'processing', 'eu-central-1', "
            "'global', :weight_kg, :shipping_cost)"
        ),
        {
            "order_id": order["id"],
            "tracking_number": tracking_number,
            "weight_kg": round(sum(int(item["quantity"]) * 1.4 for item in items), 2),
            "shipping_cost": shipping_cost,
        },
    )
    await db.execute(
        text(
            "INSERT INTO audit_logs (user_id, action, details, trace_id) "
            "VALUES (:user_id, 'order.created', :details, :trace_id)"
        ),
        {
                "user_id": customer["id"],
                "details": f"resource=orders/{order['id']}; source={source}; session_id={session_id or 'n/a'}; coupon={coupon_code or 'none'}",
                "trace_id": trace_id,
            },
        )

    if session_id:
        await db.execute(text("DELETE FROM cart_items WHERE session_id = :sid"), {"sid": session_id})

    return {
        "order": order,
        "subtotal": subtotal,
        "shipping_cost": shipping_cost,
        "coupon": coupon,
        "total": total,
        "tracking_number": tracking_number,
        "item_count": sum(int(item["quantity"]) for item in items),
    }
