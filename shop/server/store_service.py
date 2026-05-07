"""Store backend helpers for ATP-backed cart and order processing."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


_CHECKOUT_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def normalize_checkout_idempotency_key(value: object) -> str:
    """Validate a caller-supplied checkout idempotency key."""
    key = str(value or "").strip()
    if not key:
        return ""
    if not _CHECKOUT_IDEMPOTENCY_KEY_RE.fullmatch(key):
        raise ValueError("checkout idempotency key must be 8-128 URL-safe characters")
    return key


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


async def _existing_order_for_checkout_key(db, checkout_idempotency_key: str) -> dict[str, Any] | None:
    if not checkout_idempotency_key:
        return None

    order_lookup = await db.execute(
        text(
            "SELECT id, customer_id, user_id, total, status, payment_method, payment_status, "
            "payment_required, payment_provider, payment_provider_reference, payment_gateway_request_id, "
            "payment_paid_at, created_at "
            "FROM orders WHERE checkout_idempotency_key = :key FETCH FIRST 1 ROWS ONLY"
        ),
        {"key": checkout_idempotency_key},
    )
    order_row = order_lookup.mappings().first()
    if not order_row:
        return None

    order = dict(order_row)
    order_id = order["id"]
    item_summary = await db.execute(
        text(
            "SELECT COALESCE(SUM(quantity * unit_price), 0) AS subtotal, "
            "COALESCE(SUM(quantity), 0) AS item_count "
            "FROM order_items WHERE order_id = :order_id"
        ),
        {"order_id": order_id},
    )
    item_row = item_summary.mappings().first() or {}
    shipment_lookup = await db.execute(
        text(
            "SELECT tracking_number, shipping_cost FROM shipments "
            "WHERE order_id = :order_id ORDER BY id DESC FETCH FIRST 1 ROWS ONLY"
        ),
        {"order_id": order_id},
    )
    shipment = shipment_lookup.mappings().first() or {}
    subtotal = round(float(item_row.get("subtotal") or 0), 2)
    shipping_cost = round(float(shipment.get("shipping_cost") or 0), 2)
    total = round(float(order.get("total") or 0), 2)
    discount = round(max(subtotal + shipping_cost - total, 0), 2)

    return {
        "order": order,
        "subtotal": subtotal,
        "shipping_cost": shipping_cost,
        "coupon": {"code": "", "discount": discount, "valid": False},
        "total": total,
        "tracking_number": shipment.get("tracking_number") or f"OCTO-{order_id:06d}",
        "item_count": int(item_row.get("item_count") or 0),
        "idempotent_replay": True,
    }


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
    checkout_idempotency_key: str = "",
    user_id: int | None = None,
) -> dict[str, Any]:
    normalized_checkout_key = normalize_checkout_idempotency_key(checkout_idempotency_key)
    if normalized_checkout_key:
        existing = await _existing_order_for_checkout_key(db, normalized_checkout_key)
        if existing:
            return existing

    order_lookup_key = normalized_checkout_key or f"auto:{uuid.uuid4()}"
    subtotal = compute_subtotal(items)
    coupon = await apply_coupon(db, coupon_code, subtotal)
    shipping_cost = 0.0 if subtotal >= 5000 else 149.0 if subtotal else 0.0
    total = round(max(subtotal - float(coupon["discount"]), 0) + shipping_cost, 2)

    try:
        await db.execute(
            text(
                "INSERT INTO orders (customer_id, user_id, total, status, payment_method, payment_status, "
                "payment_required, notes, shipping_address, checkout_idempotency_key) "
                "VALUES (:customer_id, :user_id, :total, :status, :payment_method, :payment_status, "
                ":payment_required, :notes, :shipping_address, :checkout_idempotency_key)"
            ),
            {
                "customer_id": customer["id"],
                "user_id": user_id,
                "total": total,
                "status": "payment_pending",
                "payment_method": payment_method,
                "payment_status": "pending",
                "payment_required": 1,
                "notes": notes or f"Source={source}; Coupon={coupon_code or 'none'}",
                "shipping_address": shipping_address,
                "checkout_idempotency_key": order_lookup_key,
            },
        )
    except IntegrityError:
        if not normalized_checkout_key:
            raise
        await db.rollback()
        existing = await _existing_order_for_checkout_key(db, normalized_checkout_key)
        if existing:
            return existing
        raise
    order_lookup = await db.execute(
        text(
            "SELECT id, customer_id, user_id, total, status, payment_method, payment_status, "
            "payment_required, payment_provider, payment_provider_reference, payment_gateway_request_id, "
            "payment_paid_at, created_at "
            "FROM orders "
            "WHERE checkout_idempotency_key = :checkout_idempotency_key FETCH FIRST 1 ROWS ONLY"
        ),
        {"checkout_idempotency_key": order_lookup_key},
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
                "details": (
                    f"resource=orders/{order['id']}; source={source}; session_id={session_id or 'n/a'}; "
                    f"coupon={coupon_code or 'none'}; checkout_idempotency={'present' if normalized_checkout_key else 'generated'}"
                ),
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
        "idempotent_replay": False,
    }


async def update_order_payment_state(
    db,
    *,
    order_id: int,
    payment_provider: str,
    payment_provider_reference: str,
    payment_status: str,
    payment_gateway_request_id: str = "",
) -> dict[str, str]:
    """Persist payment simulation/provider details on an order."""
    normalized_payment_status = (payment_status or "pending").lower()
    if normalized_payment_status == "authorized":
        order_status = "paid"
        stored_payment_status = "paid"
        payment_required = 0
        payment_paid_at_expr = "CURRENT_TIMESTAMP"
    elif normalized_payment_status in {"declined", "failed", "timeout"}:
        order_status = "payment_pending"
        stored_payment_status = "failed"
        payment_required = 1
        payment_paid_at_expr = "NULL"
    else:
        order_status = "payment_pending"
        stored_payment_status = "pending"
        payment_required = 1
        payment_paid_at_expr = "NULL"

    await db.execute(
        text(
            "UPDATE orders SET payment_provider = :payment_provider, "
            "payment_provider_reference = :payment_provider_reference, "
            "payment_gateway_request_id = COALESCE(NULLIF(:payment_gateway_request_id, ''), payment_gateway_request_id), "
            "payment_status = :payment_status, payment_required = :payment_required, "
            f"payment_paid_at = {payment_paid_at_expr}, status = :status "
            "WHERE id = :order_id"
        ),
        {
            "order_id": order_id,
            "payment_provider": payment_provider,
            "payment_provider_reference": payment_provider_reference,
            "payment_gateway_request_id": payment_gateway_request_id,
            "payment_status": stored_payment_status,
            "payment_required": payment_required,
            "status": order_status,
        },
    )
    return {
        "payment_status": stored_payment_status,
        "order_status": order_status,
        "payment_required": str(payment_required),
        "payment_gateway_request_id": payment_gateway_request_id,
    }
