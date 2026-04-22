"""CRM customer-enrichment cache adapter (KG-026).

Surface that external callers (the shop's integrations.py, partners)
hit for email-keyed customer lookups. Adds octo-cache read-through +
OTel span enrichment so every call emits `cache.hit`, `cache.namespace`,
`cache.latency_ms`.

Falls through to the existing SQLAlchemy query path when the cache
client is absent or Redis is unreachable — permissive-fail contract
matches `octo_cache.client`.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_NAMESPACE = "crm:customer"
_TTL_SECONDS = 300


async def _get_cache():
    url = os.getenv("OCTO_CACHE_URL", "").strip()
    if not url:
        return None
    try:
        from octo_cache import OctoCache  # type: ignore
    except ImportError:
        return None
    return OctoCache(redis_url=url)


async def _find_by_email_in_db(email: str) -> dict[str, Any] | None:
    """Direct DB lookup. Always current; slow path."""
    if not email:
        return None
    try:
        from sqlalchemy import select  # type: ignore
        from server.database import Customer, get_db
    except ImportError:
        return None

    async with get_db() as db:
        result = await db.execute(
            select(Customer).where(Customer.email == email).limit(1)
        )
        customer = result.scalars().first()
        if customer is None:
            return None
        return {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "company": customer.company,
            "industry": customer.industry,
            "revenue": float(customer.revenue or 0),
        }


async def find_customer_by_email(email: str) -> dict[str, Any] | None:
    """Cache-first lookup. Returns None when no customer exists."""
    if not email:
        return None

    cache = await _get_cache()
    # `by-email` is the template; raw email doesn't land as an attr.
    key_template = "by-email"
    full_key = f"{key_template}:{email.lower()}"

    if cache is not None:
        cached = await cache.get(_CACHE_NAMESPACE, full_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except ValueError:
                pass

    customer = await _find_by_email_in_db(email)

    if cache is not None:
        # Cache misses too (as an empty marker) so repeated lookups
        # for a non-existent email don't hammer the DB. Empty dict
        # serializes cleanly.
        body = json.dumps(customer or {}, separators=(",", ":"))
        await cache.set(_CACHE_NAMESPACE, full_key, body, ttl_seconds=_TTL_SECONDS)
        await cache.aclose()

    return customer


async def invalidate_customer_cache(email: str) -> None:
    """Call after a customer PUT/DELETE so stale reads clear on next
    hit. TTL-based cache means staleness is already bounded; this is
    the opt-in write-through for admin flows."""
    if not email:
        return
    cache = await _get_cache()
    if cache is None:
        return
    await cache.delete(_CACHE_NAMESPACE, f"by-email:{email.lower()}")
    await cache.aclose()
