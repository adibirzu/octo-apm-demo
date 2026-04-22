"""Async Redis client wrapper with OTel span enrichment.

Every cache call adds:
    cache.hit             bool
    cache.key             str   (template, not the raw key — cardinality)
    cache.namespace       str   ("shop:catalog", "crm:customer", ...)
    cache.latency_ms      float
    cache.ttl_seconds     int   (on set)
    cache.size_bytes      int   (on set)

Hit/miss rates roll up in OCI APM dashboards without any additional
metric plumbing; the `cache.hit` boolean attribute is the single
dimension the dashboards split on.

Usage:

    cache = OctoCache(redis_url=os.getenv("OCTO_CACHE_URL", "redis://cache:6379"))

    # read-through pattern
    async def get_catalog() -> list[dict]:
        cached = await cache.get("shop:catalog", "all")
        if cached is not None:
            return json.loads(cached)
        data = await fetch_from_db()
        await cache.set("shop:catalog", "all", json.dumps(data), ttl=300)
        return data
"""

from .client import OctoCache

__all__ = ["OctoCache"]
__version__ = "1.0.0"
