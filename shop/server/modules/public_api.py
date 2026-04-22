"""Public + partner API surface — versioned under /api/v1.

Public routes (no auth):
    GET  /api/v1/public/catalog
    GET  /api/v1/public/products/{id}

Partner routes (X-API-Key header):
    GET  /api/v1/partner/orders/{id}
    POST /api/v1/partner/orders             (create — idempotent via key)

All routes emit OTel spans, respect the correlation contract
(X-Run-Id, X-Workflow-Id, traceparent), and return a consistent error
envelope.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Minimal in-memory rate limiter ────────────────────────────────────
# Fine for the demo / single-pod. Replace with a Redis-token-bucket
# once we're past the concept-proof; wiring into octo-cache is
# straightforward (SETNX + EXPIRE).
_WINDOW_SECONDS = 60
_PUBLIC_LIMIT = 100
_PARTNER_LIMIT = 1000
_buckets: dict[str, list[float]] = defaultdict(list)


def _rate_limit(key: str, limit: int) -> None:
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS
    bucket = _buckets[key]
    # Drop entries older than the window
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= limit:
        retry_after = max(1, int(_WINDOW_SECONDS - (now - bucket[0])))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"rate limit exceeded; retry after {retry_after}s",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


# ── Public routes ─────────────────────────────────────────────────────
public_router = APIRouter(prefix="/api/v1/public", tags=["public-api"])


class ProductOut(BaseModel):
    id: int
    name: str
    price: float
    stock: int
    category: str = ""


class CatalogResponse(BaseModel):
    items: list[ProductOut]
    total: int


@public_router.get("/catalog", response_model=CatalogResponse)
async def public_catalog(request: Request, limit: int = 20) -> CatalogResponse:
    _rate_limit(f"ip:{request.client.host if request.client else 'unknown'}", _PUBLIC_LIMIT)
    # Delegate to existing product module to avoid duplicating DB code.
    from server.modules.products import _list_products_for_public_api  # lazy — circulates otherwise

    items = await _list_products_for_public_api(limit=limit)
    return CatalogResponse(items=items, total=len(items))


@public_router.get("/products/{product_id}", response_model=ProductOut)
async def public_product(product_id: int, request: Request) -> ProductOut:
    _rate_limit(f"ip:{request.client.host if request.client else 'unknown'}", _PUBLIC_LIMIT)
    from server.modules.products import _get_product_for_public_api

    product = await _get_product_for_public_api(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return product


# ── Partner routes ────────────────────────────────────────────────────
partner_router = APIRouter(prefix="/api/v1/partner", tags=["partner-api"])

# In prod, API keys live in OCI Vault; for demo we accept a single
# env-configured key. KG-028 replaces with the vault-backed authorizer.
_PARTNER_API_KEY_ENV = "PARTNER_API_KEY"


def _require_partner_key(x_api_key: str | None) -> str:
    expected = os.getenv(_PARTNER_API_KEY_ENV, "")
    if not expected:
        raise HTTPException(status_code=501, detail="partner API not configured on this tenancy")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
    return x_api_key


class PartnerOrderCreate(BaseModel):
    customer_email: str = Field(..., min_length=1)
    items: list[dict[str, Any]]
    idempotency_token: str | None = None


@partner_router.get("/orders/{order_id}")
async def partner_order_get(
    order_id: int,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    key = _require_partner_key(x_api_key)
    _rate_limit(f"partner:{key}", _PARTNER_LIMIT)

    from server.modules.orders import _get_order_for_partner_api

    order = await _get_order_for_partner_api(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


@partner_router.post("/orders", status_code=status.HTTP_201_CREATED)
async def partner_order_create(
    body: PartnerOrderCreate,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    key = _require_partner_key(x_api_key)
    _rate_limit(f"partner:{key}", _PARTNER_LIMIT)

    from server.modules.orders import _create_order_for_partner_api

    order = await _create_order_for_partner_api(
        customer_email=body.customer_email,
        items=body.items,
        idempotency_token=body.idempotency_token,
    )
    return order
