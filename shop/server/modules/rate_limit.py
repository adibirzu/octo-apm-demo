"""Redis-token-bucket rate limiter (KG-041).

Drop-in replacement for the in-memory limiter in ``public_api.py``.
Uses Redis INCR + EXPIRE per key — O(1), survives pod restarts,
shared across replicas. Falls back to permissive-allow when the
cache client is absent (never take down the API because the rate
limiter is offline).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60


async def _get_redis():
    url = os.getenv("OCTO_CACHE_URL", "").strip()
    if not url:
        return None
    try:
        import redis.asyncio as redis_async  # type: ignore
    except ImportError:
        return None
    return redis_async.from_url(url, decode_responses=False)


async def check_and_consume(*, key: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> dict[str, Any]:
    """Atomically increment + check. Returns:
        {
            "allowed": bool,
            "count": int,
            "limit": int,
            "retry_after_seconds": int  # 0 when allowed
        }
    """
    redis = await _get_redis()
    if redis is None:
        # Permissive — no rate limiter available. Caller falls through.
        return {"allowed": True, "count": 0, "limit": limit, "retry_after_seconds": 0}

    # Redis key: rate:<key>:<minute-bucket>
    bucket = int(time.time() // window_seconds)
    redis_key = f"rate:{key}:{bucket}".encode()

    try:
        pipe = redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds + 5)  # a touch of slack
        results = await pipe.execute()
        count = int(results[0])
    except Exception as exc:
        logger.warning("rate_limit_redis_failed: %s", exc)
        try:
            await redis.aclose()
        except Exception:
            pass
        return {"allowed": True, "count": 0, "limit": limit, "retry_after_seconds": 0}

    await redis.aclose()

    if count > limit:
        retry_after = window_seconds - (int(time.time()) % window_seconds)
        return {
            "allowed": False,
            "count": count,
            "limit": limit,
            "retry_after_seconds": max(1, retry_after),
        }
    return {"allowed": True, "count": count, "limit": limit, "retry_after_seconds": 0}
