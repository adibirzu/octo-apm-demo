"""Tier-low playbook: flush a specific cache namespace in octo-cache.

Matches any alarm whose body contains 'cache' + 'stale' or whose
dimension `metric_name` is `cache.hit_ratio` below threshold. Safe
because cache flush degrades to DB fallback per the
permissive-fail contract.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import redis.asyncio as redis_async

from .base import ExecutionContext, Playbook, RemediationTier, _now_iso

logger = logging.getLogger(__name__)


class CacheFlushPlaybook(Playbook):
    name = "cache-flush"
    description = "Flush a single cache namespace; safe — DB fallback catches misses."
    tier = RemediationTier.LOW

    def matches(self, alarm: dict[str, Any]) -> bool:
        body = (alarm.get("body") or "").lower()
        metric_name = (alarm.get("metric_name") or "").lower()
        return (
            "cache" in body and "stale" in body
        ) or metric_name == "cache.hit_ratio"

    def extract_params(self, alarm: dict[str, Any]) -> dict[str, Any]:
        # Prefer explicit annotation, fall back to a conservative default.
        return {
            "namespace": (alarm.get("annotations") or {}).get("cache_namespace", "shop:catalog"),
        }

    async def execute(self, ctx: ExecutionContext) -> list[dict[str, Any]]:
        namespace = ctx.run.params.get("namespace", "shop:catalog")
        redis_url = os.getenv("OCTO_REMEDIATOR_REDIS_URL", "redis://cache.octo-cache.svc.cluster.local:6379")

        action_started = _now_iso()
        if ctx.dry_run:
            return [{
                "kind": "cache_flush_dryrun",
                "target": namespace,
                "result": "would DEL octo-cache keys in namespace",
                "completed_at": _now_iso(),
            }]

        client = redis_async.from_url(redis_url, decode_responses=False)
        try:
            # SCAN + DEL (avoid KEYS * in prod-shaped environments)
            cursor = 0
            pattern = f"{namespace}:*".encode()
            deleted = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=pattern, count=500)
                if keys:
                    deleted += await client.delete(*keys)
                if cursor == 0:
                    break
        finally:
            await client.aclose()

        return [{
            "kind": "cache_flush",
            "target": namespace,
            "result": f"deleted {deleted} keys",
            "started_at": action_started,
            "completed_at": _now_iso(),
        }]
