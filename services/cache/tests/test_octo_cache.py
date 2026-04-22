"""Unit tests for octo_cache.

Uses ``fakeredis`` so no live Redis is required — the wrapper's
contract (span enrichment, hit/miss classification, permissive error
handling) is what we're asserting.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from octo_cache import OctoCache

try:
    import fakeredis.aioredis  # type: ignore
    import redis.asyncio as redis_async  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("fakeredis + redis required: pip install fakeredis redis") from exc


_EXPORTER: InMemorySpanExporter | None = None


def _init_tracing_once() -> InMemorySpanExporter:
    """OTel refuses to swap TracerProvider mid-process — set one up
    lazily on first use and clear its buffer between tests."""
    global _EXPORTER
    if _EXPORTER is None:
        _EXPORTER = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(_EXPORTER))
        trace.set_tracer_provider(provider)
    return _EXPORTER


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    exporter = _init_tracing_once()
    exporter.clear()
    return exporter


@pytest_asyncio.fixture
async def cache():
    """Return an OctoCache whose internal Redis is a fakeredis instance."""
    fake = fakeredis.aioredis.FakeRedis()
    c = OctoCache.__new__(OctoCache)
    c._redis = fake
    yield c
    await c.aclose()


def _latest_span(exporter: InMemorySpanExporter) -> Any:
    provider = trace.get_tracer_provider()
    provider.force_flush()
    spans = exporter.get_finished_spans()
    return spans[-1] if spans else None


async def test_miss_then_set_then_hit(cache: OctoCache, span_exporter: InMemorySpanExporter) -> None:
    tracer = trace.get_tracer("test")

    with tracer.start_as_current_span("first-get"):
        value = await cache.get("shop:catalog", "all")
    assert value is None
    sp = _latest_span(span_exporter)
    attrs = dict(sp.attributes)
    assert attrs["cache.hit"] is False
    assert attrs["cache.namespace"] == "shop:catalog"
    assert attrs["cache.key"] == "all"
    assert attrs["cache.operation"] == "get"
    assert attrs["cache.latency_ms"] >= 0

    with tracer.start_as_current_span("set"):
        ok = await cache.set("shop:catalog", "all", b"[{'id':1}]", ttl_seconds=60)
    assert ok is True
    sp = _latest_span(span_exporter)
    attrs = dict(sp.attributes)
    assert attrs["cache.operation"] == "set"
    assert attrs["cache.size_bytes"] == len(b"[{'id':1}]")
    assert attrs["cache.ttl_seconds"] == 60
    assert attrs["cache.success"] is True

    with tracer.start_as_current_span("second-get"):
        value = await cache.get("shop:catalog", "all")
    assert value == b"[{'id':1}]"
    sp = _latest_span(span_exporter)
    assert dict(sp.attributes)["cache.hit"] is True


async def test_get_unreachable_returns_none(monkeypatch, span_exporter: InMemorySpanExporter) -> None:
    c = OctoCache.__new__(OctoCache)

    class _Boom:
        async def get(self, *_: Any, **__: Any) -> Any:
            raise ConnectionError("redis unreachable")

        async def aclose(self) -> None:
            return None

    c._redis = _Boom()

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("redis-down"):
        value = await c.get("shop:catalog", "all")
    assert value is None

    sp = _latest_span(span_exporter)
    attrs = dict(sp.attributes)
    assert attrs["cache.hit"] is False
    # Exception was recorded on the span — span.events carries it.
    assert any(evt.name == "exception" for evt in sp.events)
    await c.aclose()


async def test_set_unreachable_returns_false(span_exporter: InMemorySpanExporter) -> None:
    c = OctoCache.__new__(OctoCache)

    class _Boom:
        async def set(self, *_: Any, **__: Any) -> Any:
            raise ConnectionError("redis unreachable")

        async def aclose(self) -> None:
            return None

    c._redis = _Boom()

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("redis-down-set"):
        ok = await c.set("shop:catalog", "all", b"x", ttl_seconds=60)
    assert ok is False
    await c.aclose()


async def test_delete_is_best_effort(cache: OctoCache) -> None:
    await cache.set("k", "v", b"data", ttl_seconds=60)
    await cache.delete("k", "v")
    assert await cache.get("k", "v") is None


async def test_key_template_does_not_leak_raw_key(cache: OctoCache, span_exporter: InMemorySpanExporter) -> None:
    """`cache.key` attribute must carry the TEMPLATE, not the actual
    value, so high-cardinality keys (user IDs, order IDs) don't blow
    up APM's attribute cardinality."""
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("customer-lookup"):
        await cache.get("crm:customer", "by-email")
    sp = _latest_span(span_exporter)
    # We passed "by-email" as the template — the actual full key would
    # be something like "crm:customer:alice@example.invalid" but the
    # span only carries the template.
    assert dict(sp.attributes)["cache.key"] == "by-email"


async def test_namespace_separation(cache: OctoCache) -> None:
    await cache.set("shop:catalog", "all", b"A", ttl_seconds=60)
    await cache.set("crm:customer", "all", b"B", ttl_seconds=60)
    # Identical `key` but different namespace → different underlying
    # Redis keys.
    assert await cache.get("shop:catalog", "all") == b"A"
    assert await cache.get("crm:customer", "all") == b"B"
