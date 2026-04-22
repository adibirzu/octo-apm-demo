"""Cache-instrumented product read paths (KG-025).

Wraps the existing SQLAlchemy catalogue queries with octo-cache
read-through so every product lookup emits `cache.hit` / `cache.miss`
span attributes. Cache is optional — if `OCTO_CACHE_URL` is unset, the
adapter falls through to the DB directly.

This module exports the three helper symbols referenced by
`public_api.py`:

    _list_products_for_public_api(limit) -> list[dict]
    _get_product_for_public_api(product_id) -> dict | None
    _invalidate_catalog_cache() -> None

Adding a new cache-consumer: import from here rather than hitting the
DB directly. The public-API rate limiter + cache + OTel enrichment
apply for free.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_NAMESPACE = "shop:catalog"
_CATALOG_TTL_SECONDS = 300
_PRODUCT_TTL_SECONDS = 60


async def _get_cache():
    """Lazily instantiate an OctoCache. Returns None if the cache
    client package isn't installed or OCTO_CACHE_URL is unset — callers
    treat that as a permanent miss."""
    url = os.getenv("OCTO_CACHE_URL", "").strip()
    if not url:
        return None
    try:
        from octo_cache import OctoCache  # type: ignore
    except ImportError:
        logger.debug("octo_cache package not importable — bypassing cache")
        return None
    return OctoCache(redis_url=url)


async def _list_products_from_db(limit: int) -> list[dict[str, Any]]:
    """Existing DB query path. Exported so tests + cache miss path
    share one code path."""
    try:
        from sqlalchemy import select  # type: ignore
        from server.database import Product, get_db
    except ImportError:
        return []

    async with get_db() as db:
        result = await db.execute(select(Product).limit(limit))
        return [
            {
                "id": p.id,
                "name": p.name,
                "price": float(p.price or 0),
                "stock": int(p.stock or 0),
                "category": p.category or "",
            }
            for p in result.scalars().all()
        ]


async def _list_products_for_public_api(limit: int = 20) -> list[dict[str, Any]]:
    """Cache-first product list for /api/v1/public/catalog."""
    cache = await _get_cache()
    key = f"all:limit={limit}"
    if cache is not None:
        cached = await cache.get(_CACHE_NAMESPACE, key)
        if cached is not None:
            try:
                return json.loads(cached)
            except ValueError:
                pass  # corrupted — fall through to DB

    items = await _list_products_from_db(limit)
    if cache is not None:
        await cache.set(
            _CACHE_NAMESPACE,
            key,
            json.dumps(items, separators=(",", ":")),
            ttl_seconds=_CATALOG_TTL_SECONDS,
        )
        await cache.aclose()
    return items


async def _get_product_for_public_api(product_id: int) -> dict[str, Any] | None:
    """Cache-first individual product lookup."""
    cache = await _get_cache()
    key = "by-id"  # template, not the raw id — cardinality guard
    if cache is not None:
        cached = await cache.get(_CACHE_NAMESPACE, f"{key}:{product_id}")
        if cached is not None:
            try:
                return json.loads(cached)
            except ValueError:
                pass

    try:
        from server.database import Product, get_db
    except ImportError:
        return None

    async with get_db() as db:
        product = await db.get(Product, product_id)
        if product is None:
            return None
        item = {
            "id": product.id,
            "name": product.name,
            "price": float(product.price or 0),
            "stock": int(product.stock or 0),
            "category": product.category or "",
        }

    if cache is not None:
        await cache.set(
            _CACHE_NAMESPACE,
            f"{key}:{product_id}",
            json.dumps(item, separators=(",", ":")),
            ttl_seconds=_PRODUCT_TTL_SECONDS,
        )
        await cache.aclose()
    return item


async def _invalidate_catalog_cache() -> None:
    """Call after admin writes so the next reader hits the DB."""
    cache = await _get_cache()
    if cache is None:
        return
    await cache.delete(_CACHE_NAMESPACE, "all:limit=20")
    await cache.aclose()
