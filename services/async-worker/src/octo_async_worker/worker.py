"""Main consumer loop."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass, field

from opentelemetry import trace

from .config import WorkerConfig
from .handlers import get_handler
from .handlers.order_sync import NonRetriableError
from .streams import Event, StreamConsumer

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer("octo_async_worker")


@dataclass
class WorkerStats:
    processed: int = 0
    succeeded: int = 0
    retried: int = 0
    dead_lettered: int = 0
    unhandled_stream: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "succeeded": self.succeeded,
            "retried": self.retried,
            "dead_lettered": self.dead_lettered,
            "unhandled_stream": self.unhandled_stream,
        }


class Worker:
    def __init__(self, cfg: WorkerConfig):
        self.cfg = cfg
        consumer_name = cfg.consumer_name or f"{cfg.service_name}-{socket.gethostname()}"
        self._consumer = StreamConsumer(
            redis_url=cfg.redis_url,
            consumer_group=cfg.consumer_group,
            consumer_name=consumer_name,
            streams=cfg.streams,
            dlq_suffix=cfg.dlq_stream_suffix,
            max_delivery_attempts=cfg.max_delivery_attempts,
        )
        self.stats = WorkerStats()
        self._stop = asyncio.Event()

    async def setup(self) -> None:
        await self._consumer.ensure_groups()

    async def run(self) -> WorkerStats:
        await self.setup()
        logger.info("worker.started", extra={"streams": self.cfg.streams})

        iterations_since_recovery = 0
        recovery_every = 20  # one recovery pass per ~20 polls

        while not self._stop.is_set():
            # KG-033 — periodically reclaim pending messages from
            # dead consumers. Cheap if there are none.
            if iterations_since_recovery >= recovery_every:
                iterations_since_recovery = 0
                recovered = await self._consumer.recover_pending(min_idle_ms=60_000)
                for event in recovered:
                    await self._handle_one(event)

            events = await self._consumer.poll(
                block_ms=self.cfg.block_ms,
                count=self.cfg.count_per_poll,
            )
            iterations_since_recovery += 1

            if not events:
                if self.cfg.run_once:
                    break
                continue

            for event in events:
                await self._handle_one(event)

        await self._consumer.aclose()
        logger.info("worker.stopped", extra=self.stats.as_dict())
        return self.stats

    def request_stop(self) -> None:
        self._stop.set()

    async def _handle_one(self, event: Event) -> None:
        self.stats.processed += 1
        handler = get_handler(event.stream)

        with _tracer.start_as_current_span(f"handle {event.stream}") as span:
            span.set_attribute("stream", event.stream)
            span.set_attribute("stream.event_id", event.event_id)
            span.set_attribute("stream.delivery_attempt", event.delivery_attempt)
            if event.run_id:
                span.set_attribute("run_id", event.run_id)
            if event.workflow_id:
                span.set_attribute("workflow.id", event.workflow_id)

            if handler is None:
                logger.warning("unhandled_stream", extra={"stream": event.stream})
                self.stats.unhandled_stream += 1
                outcome = await self._consumer.park_for_retry_or_dlq(event)
                if outcome == "dlq":
                    self.stats.dead_lettered += 1
                else:
                    self.stats.retried += 1
                return

            try:
                await handler(event)
            except NonRetriableError as exc:
                span.record_exception(exc)
                span.set_attribute("handler.outcome", "dlq-nonretriable")
                await self._force_dlq(event, reason=f"non-retriable: {exc}")
                self.stats.dead_lettered += 1
                return
            except Exception as exc:
                span.record_exception(exc)
                span.set_attribute("handler.outcome", "retry-or-dlq")
                outcome = await self._consumer.park_for_retry_or_dlq(event)
                if outcome == "dlq":
                    self.stats.dead_lettered += 1
                else:
                    self.stats.retried += 1
                return

            await self._consumer.ack(event)
            span.set_attribute("handler.outcome", "ok")
            self.stats.succeeded += 1

    async def _force_dlq(self, event: Event, *, reason: str) -> None:
        """Bypass retries for non-retriable errors — straight to DLQ."""
        await self._consumer._redis.xadd(  # noqa: SLF001 — trusted internal caller
            f"{event.stream}{self.cfg.dlq_stream_suffix}",
            {
                "payload": str(event.payload),
                "run_id": event.run_id,
                "workflow_id": event.workflow_id,
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "delivery_attempt": str(event.delivery_attempt),
                "dlq_reason": reason,
                "original_event_id": event.event_id,
            },
            maxlen=100_000,
            approximate=True,
        )
        await self._consumer.ack(event)
