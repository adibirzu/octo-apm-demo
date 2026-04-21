"""Frontend observability endpoint — ingests browser telemetry events.

Receives Web Vitals, JS errors, user journey steps, and API timing from
the frontend observability.js script. Events are recorded as metrics and
forwarded to the structured log pipeline.
"""

import json
import logging

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ValidationError

from server.observability.metrics import get_meter
from server.observability.logging_sdk import push_log

router = APIRouter(prefix="/api/observability", tags=["Observability"])
logger = logging.getLogger(__name__)

# Lazy-init metrics
_web_vital_histogram = None
_frontend_error_counter = None
_journey_step_counter = None
_frontend_api_duration = None


def _ensure_metrics():
    global _web_vital_histogram, _frontend_error_counter, _journey_step_counter, _frontend_api_duration
    if _web_vital_histogram is not None:
        return
    m = get_meter()
    _web_vital_histogram = m.create_histogram(
        "crm.frontend.web_vital",
        description="Web Vital metric values (LCP/CLS/INP/TTFB)",
        unit="ms",
    )
    _frontend_error_counter = m.create_counter(
        "crm.frontend.errors",
        description="Frontend JS errors and unhandled promise rejections",
        unit="1",
    )
    _journey_step_counter = m.create_counter(
        "crm.frontend.journey_steps",
        description="User journey step completions",
        unit="1",
    )
    _frontend_api_duration = m.create_histogram(
        "crm.frontend.api.duration",
        description="Frontend-observed API call latency",
        unit="ms",
    )


class FrontendEvent(BaseModel):
    type: str
    page: str
    session_id: str = ""
    view_id: str = ""
    ts: int = 0
    payload: dict = {}


async def _parse_frontend_event(request: Request) -> FrontendEvent | None:
    """Parse telemetry sent via fetch(JSON) or sendBeacon(text/plain/application-json).

    The browser `sendBeacon()` API commonly sends string bodies as
    `text/plain;charset=UTF-8`. FastAPI's normal body-model binding rejects
    those before the route runs, which turns harmless telemetry into visible
    `422` errors in the browser console. This parser accepts both formats and
    silently drops malformed telemetry with a warning.
    """
    raw_body = await request.body()
    if not raw_body:
        return None

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Dropping malformed frontend telemetry payload")
        return None

    try:
        return FrontendEvent.model_validate(data)
    except ValidationError:
        logger.warning("Dropping invalid frontend telemetry event", exc_info=True)
        return None


@router.post("/frontend", status_code=204)
async def ingest_frontend_event(request: Request):
    """Ingest a single frontend telemetry event."""
    event = await _parse_frontend_event(request)
    if event is None:
        return Response(status_code=204)

    _ensure_metrics()
    page = event.page.split("?")[0]  # strip query params

    if event.type == "web_vital":
        metric_name = event.payload.get("name", "unknown")
        value = float(event.payload.get("value", 0))
        _web_vital_histogram.record(value, {"metric": metric_name, "page": page})

    elif event.type in ("js_error", "promise_rejection"):
        _frontend_error_counter.add(1, {"type": event.type, "page": page})
        push_log("WARNING", f"Frontend {event.type}: {event.payload.get('message', '')[:200]}", **{
            "frontend.error.type": event.type,
            "frontend.error.page": page,
            "frontend.error.message": str(event.payload.get("message", ""))[:200],
            "frontend.error.source": str(event.payload.get("source", ""))[:200],
        })

    elif event.type == "journey_step":
        step = event.payload.get("step", "unknown")
        _journey_step_counter.add(1, {"step": step, "page": page})

    elif event.type == "frontend_api":
        duration = float(event.payload.get("duration_ms", 0))
        api_url = event.payload.get("url", "unknown")
        status = event.payload.get("status", 0)
        _frontend_api_duration.record(duration, {"url": api_url, "status": str(status)})

    elif event.type == "navigation":
        pass  # just log, no metric needed

    return Response(status_code=204)
