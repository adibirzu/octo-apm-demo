"""OCI Events emission.

Every successful state-machine transition that touches money emits an
event to the OCI Events service. The Coordinator (or any downstream
consumer) subscribes and reacts — e.g. open an incident when the
payment-failure rate spikes.

Events are fire-and-forget — failures are logged at WARN level but do
not fail the HTTP request, since the webhook has already been verified
and must return 2xx to stop provider retries.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .state_machine import OrderState

logger = logging.getLogger(__name__)


_EVENT_TOPIC = os.getenv(
    "OCI_EVENTS_TOPIC_URL",
    "",  # empty → emission disabled
)


def emit_order_state_change(
    *,
    order_id: int,
    previous_state: OrderState,
    new_state: OrderState,
    amount_minor_units: int,
    currency: str,
    provider: str,
    provider_reference: str,
    trace_id: str | None = None,
) -> None:
    """Fire-and-forget POST to the OCI Events ingestion URL."""
    if not _EVENT_TOPIC:
        logger.debug("OCI_EVENTS_TOPIC_URL not set — skipping event emission")
        return

    payload: dict[str, Any] = {
        "eventType": f"com.octodemo.drone-shop.order.{new_state.value}",
        "eventTypeVersion": "1.0",
        "source": "octo-drone-shop",
        "eventTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": {
            "order_id": order_id,
            "previous_state": previous_state.value,
            "new_state": new_state.value,
            "amount_minor_units": amount_minor_units,
            "currency": currency,
            "payment_provider": provider,
            "payment_provider_reference": provider_reference,
            "oracleApmTraceId": trace_id or "",
        },
    }

    try:
        # 1-second timeout — must not block webhook ACK.
        with httpx.Client(timeout=1.0) as client:
            resp = client.post(_EVENT_TOPIC, json=payload)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(
            "oci_event_emission_failed",
            extra={
                "order_id": order_id,
                "new_state": new_state.value,
                "error": str(exc),
            },
        )
