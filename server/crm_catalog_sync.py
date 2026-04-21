"""Helpers for applying CRM-managed catalog changes inside the shop service."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import text

from server.database import AuditLog

_SKU_PATTERN = re.compile(r"^[A-Z0-9._-]{2,50}$")
_ALLOWED_ACTIONS = {"upsert", "deactivate"}


def normalize_sync_action(action: str | None) -> str:
    normalized = str(action or "upsert").strip().lower()
    if normalized not in _ALLOWED_ACTIONS:
        raise ValueError(f"action must be one of: {', '.join(sorted(_ALLOWED_ACTIONS))}")
    return normalized


def normalize_synced_product(raw: dict) -> dict:
    name = str(raw.get("name", "") or "").strip()
    if not name:
        raise ValueError("name is required")
    if len(name) > 200:
        raise ValueError("name exceeds 200 characters")

    sku = str(raw.get("sku", "") or "").strip().upper()
    if not _SKU_PATTERN.fullmatch(sku):
        raise ValueError("sku must match ^[A-Z0-9._-]{2,50}$")

    description = str(raw.get("description", "") or "").strip()
    if len(description) > 4000:
        raise ValueError("description exceeds 4000 characters")

    category = str(raw.get("category", "") or "").strip()
    if len(category) > 100:
        raise ValueError("category exceeds 100 characters")

    image_url = str(raw.get("image_url", "") or "").strip()
    if len(image_url) > 500:
        raise ValueError("image_url exceeds 500 characters")

    try:
        price = float(raw.get("price") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("price must be numeric") from exc
    if price < 0 or price > 1_000_000:
        raise ValueError("price must be between 0 and 1000000")

    try:
        stock = int(raw.get("stock") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("stock must be an integer") from exc
    if stock < 0 or stock > 1_000_000:
        raise ValueError("stock must be between 0 and 1000000")

    try:
        is_active = 1 if int(raw.get("is_active", 1) or 0) else 0
    except (TypeError, ValueError) as exc:
        raise ValueError("is_active must be 0 or 1") from exc

    return {
        "name": name,
        "sku": sku,
        "description": description,
        "price": price,
        "stock": stock,
        "category": category,
        "image_url": image_url,
        "is_active": is_active,
    }


async def apply_catalog_sync(
    db,
    *,
    products: Iterable[dict],
    action: str = "upsert",
    source: str = "enterprise-crm-portal",
) -> dict:
    normalized_action = normalize_sync_action(action)
    prepared_products = [normalize_synced_product(product) for product in products]

    created = 0
    updated = 0
    deactivated = 0
    processed: list[dict] = []

    for product in prepared_products:
        target_is_active = 0 if normalized_action == "deactivate" else product["is_active"]
        existing = await db.execute(
            text("SELECT id FROM products WHERE upper(sku) = upper(:sku) FETCH FIRST 1 ROWS ONLY"),
            {"sku": product["sku"]},
        )
        row = existing.mappings().first()

        payload = {**product, "is_active": target_is_active}
        if row:
            await db.execute(
                text(
                    "UPDATE products SET "
                    "name = :name, sku = :sku, description = :description, price = :price, "
                    "stock = :stock, category = :category, image_url = :image_url, is_active = :is_active "
                    "WHERE id = :id"
                ),
                {**payload, "id": row["id"]},
            )
            product_id = int(row["id"])
            if normalized_action == "deactivate":
                deactivated += 1
                operation = "deactivated"
            else:
                updated += 1
                operation = "updated"
        else:
            await db.execute(
                text(
                    "INSERT INTO products (name, sku, description, price, stock, category, image_url, is_active) "
                    "VALUES (:name, :sku, :description, :price, :stock, :category, :image_url, :is_active)"
                ),
                payload,
            )
            created_row = await db.execute(
                text("SELECT id FROM products WHERE upper(sku) = upper(:sku) FETCH FIRST 1 ROWS ONLY"),
                {"sku": product["sku"]},
            )
            product_id = int(created_row.mappings().first()["id"])
            if normalized_action == "deactivate":
                deactivated += 1
                operation = "created_inactive"
            else:
                created += 1
                operation = "created"

        db.add(
            AuditLog(
                user_id=0,
                action=f"crm_catalog_{normalized_action}",
                resource=f"products/{product_id}",
                details=f"{source} {operation} {product['sku']}",
                ip_address="internal-service",
            )
        )
        processed.append({"sku": product["sku"], "product_id": product_id, "status": operation})

    return {
        "status": "ok",
        "action": normalized_action,
        "source": source,
        "processed_count": len(processed),
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
        "products": processed,
    }
