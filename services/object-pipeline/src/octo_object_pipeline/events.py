"""OCI Events emission — fire-and-forget."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def emit(*, event_type: str, source: str, data: dict[str, Any]) -> None:
    topic = os.getenv("OCI_EVENTS_TOPIC_URL", "")
    if not topic:
        return
    payload = {
        "eventType": event_type,
        "eventTypeVersion": "1.0",
        "source": source,
        "eventTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": data,
    }
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.post(topic, json=payload)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("oci_event_emission_failed: %s", exc)
