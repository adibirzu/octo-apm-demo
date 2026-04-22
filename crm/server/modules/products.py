"""Governed product catalog APIs for CRM-managed storefront operations."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from server.database import AuditLog, OrderItem, Product, Shop, get_db
from server.modules._authz import require_management_user
from server.observability.otel_setup import get_tracer
from server.shop_catalog_sync import sync_product_to_shop, sync_products_to_shop

router = APIRouter(prefix="/api/products", tags=["Products"])
tracer_fn = get_tracer


class ProductMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    sku: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    description: str = Field(default="", max_length=4000)
    price: float = Field(..., ge=0, le=1_000_000)
    stock: int = Field(default=0, ge=0, le=1_000_000)
    category: str = Field(default="", max_length=100)
    image_url: Optional[str] = Field(default=None, max_length=500)
    shop_id: Optional[int] = Field(default=None, ge=1)
    is_active: int = Field(default=1, ge=0, le=1)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.startswith("/"):
            return cleaned
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("image_url must be an absolute http(s) URL or an application-relative path")
        return cleaned


def _serialize_product(product: Product) -> dict:
    shop = product.__dict__.get("shop")
    return {
        "id": product.id,
        "shop_id": product.shop_id,
        "shop_name": shop.name if shop is not None else None,
        "name": product.name,
        "sku": product.sku,
        "description": product.description,
        "price": float(product.price or 0),
        "stock": int(product.stock or 0),
        "category": product.category,
        "image_url": product.image_url,
        "is_active": int(product.is_active or 0),
        "status": "active" if product.is_active else "inactive",
        "created_at": product.created_at.isoformat() if product.created_at else None,
    }


def _search_filter(search: str):
    pattern = f"%{search.lower()}%"
    return or_(
        func.lower(Product.name).like(pattern),
        func.lower(Product.sku).like(pattern),
        func.lower(func.coalesce(Product.category, "")).like(pattern),
    )


async def _record_audit(db, request: Request, actor: dict, action: str, resource: str, details: str) -> None:
    db.add(
        AuditLog(
            user_id=actor.get("user_id"),
            action=action,
            resource=resource,
            details=details,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", ""),
            trace_id=getattr(request.state, "correlation_id", ""),
        )
    )
    await db.flush()


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "") or "")


@router.get("")
async def list_products(
    request: Request,
    search: str = Query(default="", description="Case-insensitive name/SKU/category search"),
    category: str = Query(default="", description="Exact category filter"),
    shop_id: int = Query(default=0, ge=0, description="Filter by shop"),
    status: str = Query(default="active", description="active, inactive, or all"),
    include_inactive: bool = Query(default=False, description="Include inactive products"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    tracer = tracer_fn()
    normalized_status = (status or "active").strip().lower()

    with tracer.start_as_current_span("products.list"):
        async with get_db() as db:
            query = (
                select(Product)
                .options(selectinload(Product.shop))
                .order_by(Product.name.asc())
            )
            if search:
                query = query.where(_search_filter(search))
            if category:
                query = query.where(Product.category == category)
            if shop_id:
                query = query.where(Product.shop_id == shop_id)
            if normalized_status == "active":
                query = query.where(Product.is_active == 1)
            elif normalized_status == "inactive":
                query = query.where(Product.is_active == 0)
            elif not include_inactive:
                query = query.where(Product.is_active == 1)

            result = await db.execute(query.offset(offset).limit(limit))
            products = list(result.scalars())

        payload = [_serialize_product(product) for product in products]
        return {
            "products": payload,
            "total": len(payload),
            "limit": limit,
            "offset": offset,
        }


@router.get("/{product_id}")
async def get_product(product_id: int, request: Request):
    tracer = tracer_fn()
    with tracer.start_as_current_span("products.get"):
        async with get_db() as db:
            result = await db.execute(
                select(Product)
                .options(selectinload(Product.shop))
                .where(Product.id == product_id)
            )
            product = result.scalar_one_or_none()

        if product is None:
            return {"error": "Product not found"}
        return {"product": _serialize_product(product)}


@router.post("")
async def create_product(payload: ProductMutation, request: Request):
    tracer = tracer_fn()
    actor = require_management_user(request)

    with tracer.start_as_current_span("products.create"):
        async with get_db() as db:
            existing = await db.scalar(select(Product.id).where(Product.sku == payload.sku))
            if existing is not None:
                return {"error": "SKU already exists"}

            shop = None
            if payload.shop_id is not None:
                shop = await db.get(Shop, payload.shop_id)
                if shop is None:
                    return {"error": "Shop not found"}

            product = Product(**payload.model_dump())
            db.add(product)
            await db.flush()
            if shop is not None:
                product.shop = shop

            await _record_audit(
                db,
                request,
                actor,
                "products.create",
                f"products/{product.id}",
                f"Created product {product.sku}",
            )

        serialized = _serialize_product(product)
        shop_sync = await sync_product_to_shop(
            serialized,
            action="upsert",
            correlation_id=_correlation_id(request),
        )
        return {"status": "created", "product": serialized, "shop_sync": shop_sync}


@router.patch("/{product_id}")
async def update_product(product_id: int, payload: ProductMutation, request: Request):
    tracer = tracer_fn()
    actor = require_management_user(request)

    with tracer.start_as_current_span("products.update"):
        async with get_db() as db:
            product = await db.get(Product, product_id)
            if product is None:
                return {"error": "Product not found"}

            duplicate = await db.scalar(
                select(Product.id)
                .where(Product.sku == payload.sku, Product.id != product_id)
            )
            if duplicate is not None:
                return {"error": "SKU already exists"}

            shop = None
            if payload.shop_id is not None:
                shop = await db.get(Shop, payload.shop_id)
                if shop is None:
                    return {"error": "Shop not found"}

            for field, value in payload.model_dump().items():
                setattr(product, field, value)
            product.shop = shop

            await db.flush()
            await _record_audit(
                db,
                request,
                actor,
                "products.update",
                f"products/{product.id}",
                f"Updated product {product.sku}",
            )

        serialized = _serialize_product(product)
        shop_sync = await sync_product_to_shop(
            serialized,
            action="upsert",
            correlation_id=_correlation_id(request),
        )
        return {"status": "updated", "product": serialized, "shop_sync": shop_sync}


@router.post("/sync/shop")
async def sync_catalog_to_shop(request: Request):
    tracer = tracer_fn()
    actor = require_management_user(request)

    with tracer.start_as_current_span("products.sync.shop"):
        async with get_db() as db:
            result = await db.execute(
                select(Product)
                .options(selectinload(Product.shop))
                .order_by(Product.id.asc())
            )
            products = list(result.scalars())
            await _record_audit(
                db,
                request,
                actor,
                "products.sync.shop",
                "products",
                f"Triggered full catalog sync for {len(products)} products",
            )

        payload = [_serialize_product(product) for product in products]
        shop_sync = await sync_products_to_shop(
            payload,
            action="upsert",
            correlation_id=_correlation_id(request),
        )
        return {
            "status": "completed" if shop_sync.get("synced") else "warning",
            "product_count": len(payload),
            "shop_sync": shop_sync,
        }


@router.delete("/{product_id}")
async def delete_product(product_id: int, request: Request):
    tracer = tracer_fn()
    actor = require_management_user(request)

    with tracer.start_as_current_span("products.delete"):
        sync_snapshot: dict | None = None
        response: dict | None = None
        async with get_db() as db:
            product = await db.get(Product, product_id)
            if product is None:
                return {"error": "Product not found"}

            linked_orders = await db.scalar(
                select(func.count(OrderItem.id)).where(OrderItem.product_id == product_id)
            )
            if linked_orders:
                product.is_active = 0
                await db.flush()
                sync_snapshot = _serialize_product(product)
                await _record_audit(
                    db,
                    request,
                    actor,
                    "products.archive",
                    f"products/{product.id}",
                    f"Archived product {product.sku} because it has order history",
                )
                response = {
                    "status": "archived",
                    "product": sync_snapshot,
                    "reason": "Product has historical orders and was deactivated instead of deleted",
                }
            else:
                sync_snapshot = _serialize_product(product) | {"is_active": 0}
                sku = product.sku
                await db.delete(product)
                await db.flush()
                await _record_audit(
                    db,
                    request,
                    actor,
                    "products.delete",
                    f"products/{product_id}",
                    f"Deleted product {sku}",
                )
                response = {"status": "deleted", "product_id": product_id, "product": sync_snapshot}

        shop_sync = await sync_product_to_shop(
            sync_snapshot or {"name": "", "sku": "", "price": 0, "stock": 0, "is_active": 0},
            action="deactivate",
            correlation_id=_correlation_id(request),
        )
        return {**(response or {"status": "deleted", "product_id": product_id}), "shop_sync": shop_sync}
