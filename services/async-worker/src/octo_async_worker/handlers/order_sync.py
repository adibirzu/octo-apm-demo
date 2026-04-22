"""Handler for ``octo.orders.to-sync`` events.

Wire format (payload):
    {
        "order_id": 100,
        "customer_id": 42,
        "items": [...],
        "source_system": "octo-drone-shop",
        "source_order_id": "100",
        "idempotency_token": "<uuid>"
    }

Calls CRM ``POST /api/orders`` with the ``X-Internal-Service-Key``
header. On non-2xx, raises so the consumer escalates to retry/DLQ.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from opentelemetry import trace

from ..streams import Event

logger = logging.getLogger(__name__)


async def handle(event: Event) -> None:
    payload: dict[str, Any] = event.payload
    crm_url = os.getenv("OCTO_WORKER_CRM_BASE_URL", "https://backend.octodemo.cloud")
    key = os.getenv("OCTO_WORKER_INTERNAL_SERVICE_KEY", "")

    headers: dict[str, str] = {
        "X-Run-Id": event.run_id,
        "X-Workflow-Id": event.workflow_id or "async.order-sync",
    }
    if key:
        headers["X-Internal-Service-Key"] = key
    if event.trace_id:
        # W3C traceparent so CRM-side spans chain to the producer's trace.
        headers["traceparent"] = f"00-{event.trace_id}-{event.span_id or '0000000000000000'}-01"

    span = trace.get_current_span()
    span.set_attribute("stream", event.stream)
    span.set_attribute("stream.event_id", event.event_id)
    span.set_attribute("stream.delivery_attempt", event.delivery_attempt)
    span.set_attribute("workflow.id", event.workflow_id or "async.order-sync")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{crm_url}/api/orders", json=payload, headers=headers)

    span.set_attribute("http.status_code", resp.status_code)

    if resp.status_code >= 500 or resp.status_code == 429:
        # Retriable — raise so consumer escalates
        raise RuntimeError(
            f"CRM returned {resp.status_code}; retriable (attempt {event.delivery_attempt})"
        )
    if resp.status_code >= 400:
        # Non-retriable: the payload is broken. Escalate straight to DLQ
        # via a special flag on the raised exception so the worker knows
        # not to bother retrying.
        raise NonRetriableError(
            f"CRM returned {resp.status_code} on attempt {event.delivery_attempt}"
        )

    logger.info(
        "order_sync.success",
        extra={
            "order_id": payload.get("order_id"),
            "run_id": event.run_id,
            "status": resp.status_code,
        },
    )


class NonRetriableError(Exception):
    """Raised for payload-broken failures (4xx non-429). Worker will
    route straight to DLQ without spending retries."""
