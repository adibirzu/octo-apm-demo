"""KG-033 — XCLAIM / XAUTOCLAIM recovery tests.

Verifies StreamConsumer.recover_pending() reclaims messages left
pending by a dead consumer and returns them as Events the worker
can process.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from octo_async_worker.streams import EventPublisher, StreamConsumer


@pytest_asyncio.fixture
async def pub_and_two_consumers(fake_redis):
    pub = EventPublisher.__new__(EventPublisher)
    pub._redis = fake_redis

    # "Dead" consumer that publishes + reads but never ACKs
    dead = StreamConsumer.__new__(StreamConsumer)
    dead._redis = fake_redis
    dead._group = "recovery-group"
    dead._consumer = "dead-consumer"
    dead._streams = ["recovery.stream"]
    dead._dlq_suffix = ".dlq"
    dead._max_attempts = 5

    # "Alive" consumer that will XAUTOCLAIM
    alive = StreamConsumer.__new__(StreamConsumer)
    alive._redis = fake_redis
    alive._group = "recovery-group"
    alive._consumer = "alive-consumer"
    alive._streams = ["recovery.stream"]
    alive._dlq_suffix = ".dlq"
    alive._max_attempts = 5

    await dead.ensure_groups()
    yield pub, dead, alive


async def test_recovery_reclaims_pending_messages(pub_and_two_consumers) -> None:
    pub, dead, alive = pub_and_two_consumers
    await pub.publish(stream="recovery.stream", payload={"order_id": 1})

    # Dead consumer reads but never acks — message is now pending
    read = await dead.poll(block_ms=50, count=10)
    assert len(read) == 1
    # Do NOT call dead.ack()

    # recover_pending with min_idle_ms=0 grabs everything pending
    recovered = await alive.recover_pending(min_idle_ms=0, batch=10)
    assert len(recovered) == 1
    assert recovered[0].payload["order_id"] == 1
    # The message is now associated with `alive` — subsequent XPENDING
    # for the group shows alive as the consumer holding it. (fakeredis
    # represents this transparently.)


async def test_recovery_ignores_fresh_pending(pub_and_two_consumers) -> None:
    """Messages newer than min_idle_ms should NOT be reclaimed —
    otherwise two live consumers would steal each other's work."""
    pub, dead, alive = pub_and_two_consumers
    await pub.publish(stream="recovery.stream", payload={"order_id": 2})
    await dead.poll(block_ms=50, count=10)  # dead now pending

    # min_idle_ms much higher than elapsed time
    recovered = await alive.recover_pending(min_idle_ms=60_000, batch=10)
    assert recovered == []


async def test_recovery_handles_missing_xautoclaim_gracefully(pub_and_two_consumers, monkeypatch) -> None:
    """If the Redis version doesn't support XAUTOCLAIM, recover_pending
    must log + return [] instead of blowing up the worker loop."""
    pub, dead, alive = pub_and_two_consumers

    async def _boom(**_: object):
        raise RuntimeError("ERR unknown command `xautoclaim`")

    monkeypatch.setattr(alive._redis, "xautoclaim", _boom)

    recovered = await alive.recover_pending(min_idle_ms=0, batch=10)
    assert recovered == []
