"""OCI Events emission on run lifecycle.

Matches the correlation-contract event envelope. Every state transition
emits one event:

- ``com.octodemo.load-control.run.started``
- ``com.octodemo.load-control.run.succeeded`` | ``.failed`` | ``.cancelled``

Fire-and-forget (short timeout). Emission failures are logged and
swallowed so a Events outage does not block the REST API response.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from .runs import Run

logger = logging.getLogger(__name__)

_EVENT_TOPIC = os.getenv("OCI_EVENTS_TOPIC_URL", "")


def _isoformat_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def emit_run_state(*, run: Run, state_suffix: str) -> None:
    if not _EVENT_TOPIC:
        logger.debug("OCI_EVENTS_TOPIC_URL not set — skipping event emission")
        return

    payload = {
        "eventType": f"com.octodemo.load-control.run.{state_suffix}",
        "eventTypeVersion": "1.0",
        "source": "octo-load-control",
        "eventTime": _isoformat_utc(),
        "data": {
            "run_id": run.run_id,
            "profile_name": run.profile_name,
            "operator": run.operator,
            "duration_seconds": run.duration_seconds,
            "state": run.state.value,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.post(_EVENT_TOPIC, json=payload)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("load-control event emission failed: %s", exc)
