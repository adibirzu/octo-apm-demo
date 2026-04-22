"""EventPublisher + StreamConsumer tests — fakeredis only, no network."""

from __future__ import annotations

import pytest
import pytest_asyncio

from octo_async_worker.streams import Event, EventPublisher, StreamConsumer


@pytest_asyncio.fixture
async def publisher(fake_redis):
    p = EventPublisher.__new__(EventPublisher)
    p._redis = fake_redis
    yield p
    # aclose is called by fixture teardown via fake_redis


@pytest_asyncio.fixture
async def consumer(fake_redis):
    c = StreamConsumer.__new__(StreamConsumer)
    c._redis = fake_redis
    c._group = "test-group"
    c._consumer = "test-consumer"
    c._streams = ["test.stream"]
    c._dlq_suffix = ".dlq"
    c._max_attempts = 3
    yield c


async def test_publish_then_poll(publisher, consumer) -> None:
    await consumer.ensure_groups()
    await publisher.publish(
        stream="test.stream",
        payload={"order_id": 42},
        run_id="run-abc",
        workflow_id="test-wf",
    )
    events = await consumer.poll(block_ms=50, count=10)
    assert len(events) == 1
    e = events[0]
    assert e.stream == "test.stream"
    assert e.payload["order_id"] == 42
    assert e.run_id == "run-abc"
    assert e.workflow_id == "test-wf"
    assert e.delivery_attempt == 1


async def test_ack_marks_delivered(publisher, consumer) -> None:
    await consumer.ensure_groups()
    await publisher.publish(stream="test.stream", payload={"x": 1})
    events = await consumer.poll(block_ms=50, count=10)
    assert len(events) == 1
    await consumer.ack(events[0])

    # A second poll returns no new events; the one we acked is gone.
    events2 = await consumer.poll(block_ms=50, count=10)
    assert events2 == []


async def test_retry_requeues_with_incremented_attempt(publisher, consumer) -> None:
    await consumer.ensure_groups()
    await publisher.publish(stream="test.stream", payload={"x": 1})

    first = (await consumer.poll(block_ms=50, count=10))[0]
    outcome = await consumer.park_for_retry_or_dlq(first)
    assert outcome == "retry"

    # Fresh poll returns the same payload with attempt = 2
    second_batch = await consumer.poll(block_ms=50, count=10)
    assert len(second_batch) == 1
    assert second_batch[0].payload == first.payload
    assert second_batch[0].delivery_attempt == 2


async def test_dlq_after_max_attempts(publisher, consumer, fake_redis) -> None:
    consumer._max_attempts = 2
    await consumer.ensure_groups()

    await publisher.publish(stream="test.stream", payload={"x": 1})
    e = (await consumer.poll(block_ms=50, count=10))[0]
    assert await consumer.park_for_retry_or_dlq(e) == "retry"  # attempt 2

    e2 = (await consumer.poll(block_ms=50, count=10))[0]
    outcome = await consumer.park_for_retry_or_dlq(e2)
    assert outcome == "dlq"

    # Original stream is drained
    assert await consumer.poll(block_ms=50, count=10) == []

    # DLQ has one entry
    dlq_len = await fake_redis.xlen("test.stream.dlq")
    assert dlq_len == 1


async def test_ensure_groups_is_idempotent(publisher, consumer) -> None:
    await consumer.ensure_groups()
    # Calling again must not raise (BUSYGROUP swallowed)
    await consumer.ensure_groups()
