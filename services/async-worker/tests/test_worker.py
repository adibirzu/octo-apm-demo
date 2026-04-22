"""Worker loop tests — patch the handler registry so we don't need
real CRM."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from octo_async_worker import Worker, WorkerConfig
from octo_async_worker.handlers.order_sync import NonRetriableError
from octo_async_worker.streams import EventPublisher


@pytest.fixture
def cfg() -> WorkerConfig:
    return WorkerConfig(
        redis_url="redis://unused",  # overridden below
        streams=["test.stream"],
        block_ms=100,
        count_per_poll=5,
        max_delivery_attempts=2,
        run_once=True,
    )


async def test_successful_handle_acks_event(cfg, fake_redis, monkeypatch) -> None:
    # Patch handler to always succeed
    from octo_async_worker import handlers

    called = []

    async def _ok(event):
        called.append(event.payload)

    monkeypatch.setitem(handlers.HANDLERS, "test.stream", _ok)

    # Worker uses its own Redis connections — swap both
    worker = Worker(cfg)
    worker._consumer._redis = fake_redis

    publisher = EventPublisher.__new__(EventPublisher)
    publisher._redis = fake_redis
    await publisher.publish(stream="test.stream", payload={"order_id": 1})

    stats = await worker.run()

    assert called == [{"order_id": 1}]
    assert stats.processed == 1
    assert stats.succeeded == 1
    assert stats.retried == 0
    assert stats.dead_lettered == 0


async def test_retriable_failure_requeues_and_eventually_dlqs(cfg, fake_redis, monkeypatch) -> None:
    """run_once drains until the stream is empty. A perpetually-failing
    handler therefore retries once (attempt 1 → 2, the limit) and then
    DLQs on the next poll. Expected end state: processed=2, retried=1,
    dead_lettered=1."""
    from octo_async_worker import handlers

    async def _boom(event):
        raise RuntimeError("transient")

    monkeypatch.setitem(handlers.HANDLERS, "test.stream", _boom)

    worker = Worker(cfg)
    worker._consumer._redis = fake_redis

    publisher = EventPublisher.__new__(EventPublisher)
    publisher._redis = fake_redis
    await publisher.publish(stream="test.stream", payload={"x": 1})

    stats = await worker.run()

    assert stats.processed == 2
    assert stats.retried == 1
    assert stats.dead_lettered == 1
    assert stats.succeeded == 0


async def test_nonretriable_goes_straight_to_dlq(cfg, fake_redis, monkeypatch) -> None:
    from octo_async_worker import handlers

    async def _bad_payload(event):
        raise NonRetriableError("malformed")

    monkeypatch.setitem(handlers.HANDLERS, "test.stream", _bad_payload)

    worker = Worker(cfg)
    worker._consumer._redis = fake_redis

    publisher = EventPublisher.__new__(EventPublisher)
    publisher._redis = fake_redis
    await publisher.publish(stream="test.stream", payload={"x": 1})

    stats = await worker.run()

    assert stats.processed == 1
    assert stats.dead_lettered == 1
    assert stats.retried == 0

    # DLQ has the entry; original is acked.
    assert await fake_redis.xlen("test.stream.dlq") == 1


async def test_unhandled_stream_retries_then_dlqs(cfg, fake_redis) -> None:
    # No handler registered for "test.stream" — leave HANDLERS alone
    # but use a stream name the worker watches.
    cfg.streams = ["test.no-handler"]
    cfg.max_delivery_attempts = 1  # first failure immediately DLQs

    worker = Worker(cfg)
    worker._consumer._redis = fake_redis

    publisher = EventPublisher.__new__(EventPublisher)
    publisher._redis = fake_redis
    await publisher.publish(stream="test.no-handler", payload={"x": 1})

    stats = await worker.run()

    assert stats.processed == 1
    assert stats.unhandled_stream == 1
    assert stats.dead_lettered == 1
