"""Async order-sync publisher (KG-034).

Feature-flagged optional path for shop → CRM order handoff. When
`OCTO_ASYNC_ORDER_SYNC_ENABLED=true`, the shop's checkout handler
XADDs the order onto `octo.orders.to-sync` and returns 202 Accepted
immediately; octo-async-worker does the CRM POST out of band.

When the flag is absent, callers fall back to the synchronous
`sync_order_to_crm` path.

The flag is per-request via cfg; operators flip it at deployment
time via env. Both paths stay wired simultaneously during migration.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from opentelemetry import trace

logger = logging.getLogger(__name__)


def _async_enabled() -> bool:
    return os.getenv("OCTO_ASYNC_ORDER_SYNC_ENABLED", "false").lower() == "true"


async def _get_publisher():
    """Lazy import the EventPublisher — keeps shop installable when the
    async-worker package isn't present (dev + CI minimal)."""
    redis_url = os.getenv("OCTO_ORDER_STREAM_REDIS_URL", os.getenv("OCTO_CACHE_URL", "")).strip()
    if not redis_url:
        return None
    try:
        from octo_async_worker import EventPublisher  # type: ignore
    except ImportError:
        return None
    return EventPublisher(redis_url=redis_url)


async def publish_order_for_async_sync(
    *,
    order_id: int,
    customer_id: int,
    customer_email: str,
    items: list[dict[str, Any]],
    source_order_id: str,
    idempotency_token: str,
    run_id: str = "",
) -> dict[str, Any]:
    """Fan-out an order onto the ``octo.orders.to-sync`` stream.

    Returns a small envelope describing the enqueue outcome:
        {"queued": True, "event_id": "<redis id>", "stream": "..."}

    or on failure:
        {"queued": False, "reason": "..."}

    Callers decide whether to fall back to the sync path. Exceptions
    are never raised — we don't want checkout to 500 because the
    async pipe is flakey.
    """
    if not _async_enabled():
        return {"queued": False, "reason": "async path disabled (set OCTO_ASYNC_ORDER_SYNC_ENABLED=true to enable)"}

    publisher = await _get_publisher()
    if publisher is None:
        return {"queued": False, "reason": "publisher not configured"}

    span = trace.get_current_span()
    trace_id_hex = ""
    span_id_hex = ""
    try:
        ctx = span.get_span_context()
        if ctx.trace_id:
            trace_id_hex = format(ctx.trace_id, "032x")
        if ctx.span_id:
            span_id_hex = format(ctx.span_id, "016x")
    except Exception:
        pass

    payload = {
        "order_id": order_id,
        "customer_id": customer_id,
        "customer_email": customer_email,
        "items": items,
        "source_system": "octo-drone-shop",
        "source_order_id": source_order_id,
        "idempotency_token": idempotency_token,
    }

    try:
        event_id = await publisher.publish(
            stream="octo.orders.to-sync",
            payload=payload,
            run_id=run_id,
            workflow_id="shop.order.sync.async",
            trace_id=trace_id_hex,
            span_id=span_id_hex,
        )
        span.set_attribute("order.sync.kind", "async")
        span.set_attribute("order.sync.stream", "octo.orders.to-sync")
        span.set_attribute("order.sync.event_id", str(event_id))
        return {
            "queued": True,
            "event_id": str(event_id),
            "stream": "octo.orders.to-sync",
        }
    except Exception as exc:
        logger.warning("async order publish failed: %s", exc)
        return {"queued": False, "reason": f"publish failed: {exc}"}
    finally:
        try:
            await publisher.aclose()
        except Exception:
            pass
