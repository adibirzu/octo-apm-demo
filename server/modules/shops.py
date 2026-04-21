"""CRM storefront management APIs for shops and channel settings."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from server.database import AuditLog, Product, Shop, get_db
from server.modules._authz import require_management_user
from server.observability.otel_setup import get_tracer

router = APIRouter(prefix="/api/shops", tags=["Shops"])
tracer_fn = get_tracer

_ALLOWED_SHOP_STATUSES = {"active", "maintenance", "inactive"}


class ShopMutation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    storefront_url: str = Field(..., max_length=500)
    crm_base_url: str = Field(..., max_length=500)
    region: str = Field(..., min_length=2, max_length=80)
    currency: str = Field(default="USD", min_length=3, max_length=10)
    status: str = Field(default="active", min_length=3, max_length=50)
    notes: str = Field(default="", max_length=4000)

    @field_validator("storefront_url", "crm_base_url")
    @classmethod
    def validate_urls(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute http(s) URL")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_SHOP_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_ALLOWED_SHOP_STATUSES))}")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


def _serialize_shop(shop: Shop, product_count: int = 0) -> dict:
    return {
        "id": shop.id,
        "name": shop.name,
        "slug": shop.slug,
        "storefront_url": shop.storefront_url,
        "crm_base_url": shop.crm_base_url,
        "region": shop.region,
        "currency": shop.currency,
        "status": shop.status,
        "notes": shop.notes,
        "product_count": int(product_count or 0),
        "created_at": shop.created_at.isoformat() if shop.created_at else None,
        "updated_at": shop.updated_at.isoformat() if shop.updated_at else None,
    }


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


@router.get("")
async def list_shops(
    request: Request,
    search: str = Query(default="", description="Case-insensitive name/slug/region search"),
    status_filter: str = Query(default="", alias="status", description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    tracer = tracer_fn()
    normalized_search = (search or "").strip().lower()
    product_count = (
        select(func.count(Product.id))
        .where(Product.shop_id == Shop.id)
        .correlate(Shop)
        .scalar_subquery()
    )

    with tracer.start_as_current_span("shops.list"):
        async with get_db() as db:
            query = (
                select(Shop, product_count.label("product_count"))
                .order_by(Shop.name.asc())
            )
            if normalized_search:
                pattern = f"%{normalized_search}%"
                query = query.where(
                    or_(
                        func.lower(Shop.name).like(pattern),
                        func.lower(Shop.slug).like(pattern),
                        func.lower(Shop.region).like(pattern),
                    )
                )
            if status_filter:
                query = query.where(Shop.status == status_filter.strip().lower())

            result = await db.execute(query.offset(offset).limit(limit))
            rows = result.all()

        shops = [_serialize_shop(shop, product_count) for shop, product_count in rows]
        return {"shops": shops, "total": len(shops), "limit": limit, "offset": offset}


@router.get("/{shop_id}")
async def get_shop(shop_id: int, request: Request):
    tracer = tracer_fn()
    product_count = (
        select(func.count(Product.id))
        .where(Product.shop_id == Shop.id)
        .correlate(Shop)
        .scalar_subquery()
    )

    with tracer.start_as_current_span("shops.get"):
        async with get_db() as db:
            result = await db.execute(
                select(Shop, product_count.label("product_count"))
                .where(Shop.id == shop_id)
            )
            row = result.first()

        if row is None:
            return {"error": "Shop not found"}
        shop, product_count = row
        return {"shop": _serialize_shop(shop, product_count)}


@router.post("")
async def create_shop(payload: ShopMutation, request: Request):
    tracer = tracer_fn()
    actor = require_management_user(request)

    with tracer.start_as_current_span("shops.create"):
        async with get_db() as db:
            duplicate = await db.scalar(select(Shop.id).where(Shop.slug == payload.slug))
            if duplicate is not None:
                return {"error": "Shop slug already exists"}

            shop = Shop(**payload.model_dump())
            db.add(shop)
            await db.flush()
            await _record_audit(
                db,
                request,
                actor,
                "shops.create",
                f"shops/{shop.id}",
                f"Created shop {shop.slug}",
            )

        return {"status": "created", "shop": _serialize_shop(shop)}


@router.patch("/{shop_id}")
async def update_shop(shop_id: int, payload: ShopMutation, request: Request):
    tracer = tracer_fn()
    actor = require_management_user(request)

    with tracer.start_as_current_span("shops.update"):
        async with get_db() as db:
            shop = await db.get(Shop, shop_id)
            if shop is None:
                return {"error": "Shop not found"}

            duplicate = await db.scalar(
                select(Shop.id).where(Shop.slug == payload.slug, Shop.id != shop_id)
            )
            if duplicate is not None:
                return {"error": "Shop slug already exists"}

            for field, value in payload.model_dump().items():
                setattr(shop, field, value)
            await db.flush()
            product_count = await db.scalar(select(func.count(Product.id)).where(Product.shop_id == shop.id))
            await _record_audit(
                db,
                request,
                actor,
                "shops.update",
                f"shops/{shop.id}",
                f"Updated shop {shop.slug}",
            )

        return {"status": "updated", "shop": _serialize_shop(shop, product_count or 0)}


@router.delete("/{shop_id}")
async def delete_shop(shop_id: int, request: Request):
    tracer = tracer_fn()
    actor = require_management_user(request)

    with tracer.start_as_current_span("shops.delete"):
        async with get_db() as db:
            shop = await db.get(Shop, shop_id)
            if shop is None:
                return {"error": "Shop not found"}

            product_count = await db.scalar(select(func.count(Product.id)).where(Product.shop_id == shop.id))
            if product_count:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Shop still has assigned products",
                )

            slug = shop.slug
            await db.delete(shop)
            await db.flush()
            await _record_audit(
                db,
                request,
                actor,
                "shops.delete",
                f"shops/{shop_id}",
                f"Deleted shop {slug}",
            )

        return {"status": "deleted", "shop_id": shop_id}
