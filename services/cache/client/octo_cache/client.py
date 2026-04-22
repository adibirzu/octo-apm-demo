"""Async Redis wrapper instrumented for OCI APM."""

from __future__ import annotations

import time
from typing import Any

import redis.asyncio as redis_async
from opentelemetry import trace

_tracer = trace.get_tracer("octo_cache")


class OctoCache:
    """Thin wrapper around ``redis.asyncio.Redis`` that enriches OTel
    spans on every operation so APM can show hit/miss dashboards
    without a separate metric pipeline.

    The wrapper is **permissive**: if Redis is unreachable, it logs the
    error on the current span and returns ``None`` (for ``get``) or
    silently fails (for ``set``). The caller's fallback is the DB
    round-trip. This is deliberate — caches are *optional*; they must
    not take down the app when they fail.
    """

    def __init__(self, *, redis_url: str, connect_timeout: float = 1.0, socket_timeout: float = 0.5):
        self._redis = redis_async.from_url(
            redis_url,
            decode_responses=False,          # bytes-in / bytes-out
            socket_connect_timeout=connect_timeout,
            socket_timeout=socket_timeout,
            health_check_interval=30,
        )

    async def aclose(self) -> None:
        await self._redis.aclose()

    async def get(self, namespace: str, key: str) -> bytes | None:
        full_key = self._full_key(namespace, key)
        span = trace.get_current_span()
        start = time.perf_counter()
        hit = False
        try:
            value = await self._redis.get(full_key)
            hit = value is not None
            return value
        except Exception as exc:  # noqa: BLE001
            span.record_exception(exc)
            return None
        finally:
            latency_ms = (time.perf_counter() - start) * 1_000.0
            self._set_span_attrs(span, namespace=namespace, key_template=key,
                                 hit=hit, latency_ms=latency_ms)

    async def set(
        self,
        namespace: str,
        key: str,
        value: bytes | str,
        *,
        ttl_seconds: int,
    ) -> bool:
        full_key = self._full_key(namespace, key)
        body = value.encode("utf-8") if isinstance(value, str) else value
        span = trace.get_current_span()
        start = time.perf_counter()
        ok = False
        try:
            ok = bool(await self._redis.set(full_key, body, ex=ttl_seconds))
            return ok
        except Exception as exc:  # noqa: BLE001
            span.record_exception(exc)
            return False
        finally:
            latency_ms = (time.perf_counter() - start) * 1_000.0
            self._set_span_attrs(
                span,
                namespace=namespace,
                key_template=key,
                operation="set",
                latency_ms=latency_ms,
                size_bytes=len(body),
                ttl_seconds=ttl_seconds,
                success=ok,
            )

    async def delete(self, namespace: str, key: str) -> None:
        full_key = self._full_key(namespace, key)
        try:
            await self._redis.delete(full_key)
        except Exception:
            # Best-effort — stale cache resolves on TTL.
            pass

    @staticmethod
    def _full_key(namespace: str, key: str) -> str:
        # Stable separator: `:` is the idiomatic Redis convention and
        # matches the Redis Enterprise `keyspace` layout we use in prod.
        return f"{namespace}:{key}"

    @staticmethod
    def _set_span_attrs(
        span,
        *,
        namespace: str,
        key_template: str,
        hit: bool | None = None,
        operation: str = "get",
        latency_ms: float = 0.0,
        size_bytes: int | None = None,
        ttl_seconds: int | None = None,
        success: bool | None = None,
    ) -> None:
        span.set_attribute("cache.system", "redis")
        span.set_attribute("cache.namespace", namespace)
        # key template — never the raw key (cardinality bomb)
        span.set_attribute("cache.key", key_template)
        span.set_attribute("cache.operation", operation)
        span.set_attribute("cache.latency_ms", round(latency_ms, 3))
        if hit is not None:
            span.set_attribute("cache.hit", hit)
        if size_bytes is not None:
            span.set_attribute("cache.size_bytes", size_bytes)
        if ttl_seconds is not None:
            span.set_attribute("cache.ttl_seconds", ttl_seconds)
        if success is not None:
            span.set_attribute("cache.success", success)
