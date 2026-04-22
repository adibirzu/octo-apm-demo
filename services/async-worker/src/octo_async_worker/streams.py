"""Stream abstractions — producer (EventPublisher) + consumer
(StreamConsumer).

Kept separate from the worker loop so the shop + CRM can import
``EventPublisher`` as a thin dependency without pulling in the full
consumer code.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis_async

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """One event on a stream.

    Every field lands on OTel span attributes so tracing across the
    async boundary works the same way as across the sync one.
    """

    event_id: str                       # Redis-assigned XADD id
    stream: str
    payload: dict[str, Any]
    run_id: str = ""
    workflow_id: str = ""
    trace_id: str = ""
    span_id: str = ""
    delivery_attempt: int = 1
    created_at: str = ""

    @classmethod
    def from_redis(cls, stream: str, entry_id: bytes, fields: dict[bytes, bytes]) -> "Event":
        body = _decode_fields(fields)
        payload_raw = body.pop("payload", "{}")
        try:
            payload = json.loads(payload_raw)
        except (ValueError, TypeError):
            payload = {"_invalid_json": payload_raw}
        return cls(
            event_id=entry_id.decode("utf-8") if isinstance(entry_id, bytes) else entry_id,
            stream=stream,
            payload=payload,
            run_id=body.pop("run_id", ""),
            workflow_id=body.pop("workflow_id", ""),
            trace_id=body.pop("trace_id", ""),
            span_id=body.pop("span_id", ""),
            delivery_attempt=int(body.pop("delivery_attempt", "1")),
            created_at=body.pop("created_at", _now_iso()),
        )


def _decode_fields(fields: dict[bytes, bytes]) -> dict[str, str]:
    return {
        (k.decode("utf-8") if isinstance(k, bytes) else k):
        (v.decode("utf-8") if isinstance(v, bytes) else v)
        for k, v in fields.items()
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EventPublisher:
    """Thin XADD wrapper callers use to put events on a stream.

    Stamps the correlation-contract fields automatically from kwargs.
    """

    def __init__(self, *, redis_url: str):
        self._redis = redis_async.from_url(redis_url, decode_responses=False)

    async def aclose(self) -> None:
        await self._redis.aclose()

    async def publish(
        self,
        *,
        stream: str,
        payload: dict[str, Any],
        run_id: str = "",
        workflow_id: str = "",
        trace_id: str = "",
        span_id: str = "",
        maxlen: int = 10_000,
    ) -> str:
        """XADD the event. Returns the Redis-assigned entry id."""
        body = {
            "payload": json.dumps(payload, separators=(",", ":")),
            "run_id": run_id,
            "workflow_id": workflow_id,
            "trace_id": trace_id,
            "span_id": span_id,
            "delivery_attempt": "1",
            "created_at": _now_iso(),
        }
        # XADD with MAXLEN ~ cap so unbounded producers don't eat memory
        entry_id = await self._redis.xadd(
            stream,
            body,
            maxlen=maxlen,
            approximate=True,  # ~ prefix — O(1) truncation
        )
        return entry_id.decode("utf-8") if isinstance(entry_id, bytes) else str(entry_id)


class StreamConsumer:
    """XREADGROUP-based consumer with DLQ + retry accounting.

    The consumer is **async-safe for multi-replica**: when two pods
    share the same consumer_group, Redis distributes pending entries
    across them. Only the pod that XACKs an entry marks it delivered.
    """

    def __init__(
        self,
        *,
        redis_url: str,
        consumer_group: str,
        consumer_name: str,
        streams: list[str],
        dlq_suffix: str = ".dlq",
        max_delivery_attempts: int = 5,
    ):
        self._redis = redis_async.from_url(redis_url, decode_responses=False)
        self._group = consumer_group
        self._consumer = consumer_name
        self._streams = streams
        self._dlq_suffix = dlq_suffix
        self._max_attempts = max_delivery_attempts

    async def aclose(self) -> None:
        await self._redis.aclose()

    async def ensure_groups(self) -> None:
        """Create the consumer group on each stream if it doesn't exist."""
        for stream in self._streams:
            try:
                await self._redis.xgroup_create(
                    stream,
                    groupname=self._group,
                    id="0",
                    mkstream=True,
                )
            except Exception as exc:
                # BUSYGROUP — group already exists; that's fine.
                if "BUSYGROUP" not in str(exc):
                    raise

    async def poll(self, *, block_ms: int = 5_000, count: int = 16) -> list[Event]:
        """XREADGROUP returning a batch of Events, or [] on timeout.

        Always reads new messages (``>``); pending-list recovery is
        done by :py:meth:`recover_pending`.
        """
        streams_map = {s: ">" for s in self._streams}
        try:
            raw = await self._redis.xreadgroup(
                groupname=self._group,
                consumername=self._consumer,
                streams=streams_map,
                count=count,
                block=block_ms,
            )
        except Exception as exc:
            logger.error("xreadgroup_failed", extra={"error": str(exc)})
            return []

        events: list[Event] = []
        for stream_name_raw, entries in raw or []:
            stream_name = (
                stream_name_raw.decode("utf-8")
                if isinstance(stream_name_raw, bytes)
                else str(stream_name_raw)
            )
            for entry_id, fields in entries:
                events.append(Event.from_redis(stream_name, entry_id, fields))
        return events

    async def ack(self, event: Event) -> None:
        """Mark ``event`` delivered. Call after successful handling."""
        await self._redis.xack(event.stream, self._group, event.event_id)

    async def park_for_retry_or_dlq(self, event: Event) -> str:
        """Escalate a failed delivery.

        Increments delivery_attempt. If under max, XADD back to the
        original stream; otherwise publish to the DLQ and XACK the
        original (so we never re-deliver a poisoned message forever).
        Returns: ``"retry"`` or ``"dlq"``.
        """
        next_attempt = event.delivery_attempt + 1
        if next_attempt > self._max_attempts:
            dlq_stream = f"{event.stream}{self._dlq_suffix}"
            await self._redis.xadd(
                dlq_stream,
                _event_body(event, delivery_attempt=next_attempt, dlq_reason="max-attempts-exceeded"),
                maxlen=100_000,
                approximate=True,
            )
            await self.ack(event)
            return "dlq"
        # Re-queue for retry
        await self._redis.xadd(
            event.stream,
            _event_body(event, delivery_attempt=next_attempt),
            maxlen=10_000,
            approximate=True,
        )
        await self.ack(event)
        return "retry"


def _event_body(event: Event, *, delivery_attempt: int, **extra: str) -> dict[str, str]:
    """Serialize an :class:`Event` back to Redis field form."""
    body = {
        "payload": json.dumps(event.payload, separators=(",", ":")),
        "run_id": event.run_id,
        "workflow_id": event.workflow_id,
        "trace_id": event.trace_id,
        "span_id": event.span_id,
        "delivery_attempt": str(delivery_attempt),
        "created_at": event.created_at,
    }
    body.update(extra)
    return body
