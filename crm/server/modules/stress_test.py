"""Admin-only stress-test surface (Phase 7 Plan 07-05).

Mounts /api/admin/stress/{presets,apply,clear,state} + the HTML page
/admin/stress-test. Every endpoint enforces admin role + admin host
(Phase 5 contract, plan 07-04 helper). Lifecycle events emit a
three-channel MELTS audit: OTel span + push_log + increment_stress_run.
The handler proxies the run lifecycle to the octo-stress-runner pod via
X-Internal-Service-Key. Server-side caps (rps 1-200, duration 10-600s,
scenario allow-list, target_service=shop) are Pydantic-enforced before
any side effect.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from server.config import cfg
from server.modules._admin_host import _require_admin_host
from server.modules._authz import require_admin_user
from server.observability.logging_sdk import push_log
from server.observability.oci_monitoring import increment_stress_run
from server.observability.otel_setup import get_tracer

logger = logging.getLogger("stress_test.audit")

_ALLOWED_SCENARIOS = ("checkout_journey", "catalog_browse", "login_burst")
_SCENARIO_PATTERN = r"^(checkout_journey|catalog_browse|login_burst)$"
_RUNNER_UNAVAILABLE_DETAIL = (
    "Stress runner unavailable. Confirm octo-stress-runner Deployment is "
    "healthy in the OKE cluster."
)


def _runner_base_url() -> str:
    return (
        cfg.octo_stress_runner_base_url
        or "http://octo-stress-runner.octo-stress.svc.cluster.local:8080"
    ).rstrip("/")


def _runner_headers() -> dict[str, str]:
    return {
        "X-Internal-Service-Key": cfg.octo_stress_runner_internal_key or "",
        "Content-Type": "application/json",
    }


def _target_host_for_shop() -> str:
    """Build the LB target hostname for the shop service from cfg.dns_domain.

    Server-side construction — never trust client input for the target host.
    """
    dns = (getattr(cfg, "dns_domain", "") or "").strip()
    if dns:
        return f"https://shop.{dns}"
    return (cfg.shop_public_url or "https://shop.octodemo.cloud").rstrip("/")


# Request model — server-side hard caps (D-13)


class RunRequest(BaseModel):
    scenario: str = Field(
        default="checkout_journey",
        pattern=_SCENARIO_PATTERN,
    )
    target_service: Literal["shop"] = Field(default="shop")
    rps: int = Field(default=25, ge=1, le=200)
    duration_seconds: int = Field(default=60, ge=10, le=600)
    note: str = Field(default="", max_length=512)

    @field_validator("note")
    @classmethod
    def _strip_control_chars(cls, v: str) -> str:
        # T-07-23: reject embedded newlines / nulls in the audit note so we
        # cannot inject fake log lines via push_log JSON-serialization paths.
        if any(ch in v for ch in ("\n", "\r", "\x00")):
            raise ValueError("note must not contain newline or null characters")
        return v


# Presets (D-13 caps)
_PRESETS = (
    {
        "name": "light",
        "label": "Light (10 RPS · 60s · catalog_browse)",
        "scenario": "catalog_browse",
        "rps": 10,
        "duration_seconds": 60,
    },
    {
        "name": "medium",
        "label": "Medium (50 RPS · 180s · checkout_journey)",
        "scenario": "checkout_journey",
        "rps": 50,
        "duration_seconds": 180,
    },
    {
        "name": "heavy",
        "label": "Heavy (120 RPS · 300s · checkout_journey)",
        "scenario": "checkout_journey",
        "rps": 120,
        "duration_seconds": 300,
    },
)


# Routers — admin role + admin host required on every endpoint
router = APIRouter(
    prefix="/api/admin/stress",
    tags=["stress-admin"],
    dependencies=[Depends(require_admin_user), Depends(_require_admin_host)],
)

_PAGE_ROUTER = APIRouter(
    prefix="/admin",
    tags=["stress-admin-page"],
    dependencies=[Depends(require_admin_user), Depends(_require_admin_host)],
)


# Three-channel MELTS audit emit (D-15)


def _emit_lifecycle_event(
    *,
    run_id: str,
    status_value: str,
    actor: dict,
    host: str,
    payload: RunRequest | None = None,
    reason: str = "",
) -> None:
    """Emit the same lifecycle event to span, log, and monitoring counter."""
    target_host = _target_host_for_shop()
    fields: dict[str, Any] = {
        "app.module": "stress_test",
        "run_id": run_id,
        "admin_user": actor.get("username", "unknown"),
        "admin_role": actor.get("role", "unknown"),
        "admin_host": host,
        "target_service": "shop",
        "target_host": target_host,
        "source_pod": cfg.service_instance_id,
        "status": status_value,
        "reason": reason,
    }
    if payload is not None:
        fields["rps_requested"] = payload.rps
        fields["duration_requested"] = payload.duration_seconds
        fields["scenario"] = payload.scenario
    try:
        push_log("INFO", f"stress_test.{status_value}", **fields)
    except Exception as exc:  # never block the handler on audit emission
        logger.warning("stress_test push_log failed: %s", exc)
    try:
        increment_stress_run(run_id=run_id, status=status_value)
    except Exception as exc:
        logger.warning("stress_test increment_stress_run failed: %s", exc)


# Cross-pod call to octo-stress-runner


async def _call_runner(
    method: str, path: str, *, json_body: dict | None = None
) -> tuple[int, dict]:
    """Call the octo-stress-runner pod. Returns (status_code, json_body).

    Raises HTTPException(503) when the runner is unreachable so callers can
    surface the UI-SPEC State copy.
    """
    url = f"{_runner_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "POST":
                resp = await client.post(
                    url, json=json_body or {}, headers=_runner_headers()
                )
            else:
                resp = await client.get(url, headers=_runner_headers())
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
        logger.warning("octo-stress-runner unreachable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_RUNNER_UNAVAILABLE_DETAIL,
        )
    try:
        data = resp.json()
    except Exception:
        data = {}
    return resp.status_code, data


# Endpoints


@router.get("/presets")
async def list_presets() -> dict[str, Any]:
    return {"presets": list(_PRESETS)}


@router.get("/state")
async def read_state(request: Request) -> dict[str, Any]:
    code, body = await _call_runner("GET", "/internal/state")
    if code != 200:
        # Surface the runner's status; default to idle so the UI does not
        # crash on a stale upstream.
        return {"status": (body or {}).get("status", "idle")}
    # Sanitized projection: keep only the UI-relevant fields.
    if body.get("status") == "idle" or not body.get("run_id"):
        return {"status": "idle"}
    return {
        "status": body.get("status", "running"),
        "run_id": body.get("run_id"),
        "scenario": body.get("scenario"),
        "rps": body.get("rps"),
        "duration_seconds": body.get("duration_seconds"),
        "target_host": body.get("target_host") or _target_host_for_shop(),
        "started_at": body.get("started_at"),
    }


@router.post("/apply", status_code=status.HTTP_202_ACCEPTED)
async def apply_run(payload: RunRequest, request: Request) -> dict[str, Any]:
    actor = require_admin_user(request)
    host = _require_admin_host(request)
    run_id = str(uuid.uuid4())
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.stress.apply") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))
        span.set_attribute("admin.host", host)
        span.set_attribute("stress.run_id", run_id)
        span.set_attribute("stress.scenario", payload.scenario)
        span.set_attribute("stress.rps_requested", payload.rps)
        span.set_attribute("stress.duration_requested", payload.duration_seconds)
        span.set_attribute("stress.target_service", "shop")

        # Three-channel audit BEFORE the cross-pod call so a runner failure
        # still leaves an authoritative trail of the attempt.
        _emit_lifecycle_event(
            run_id=run_id,
            status_value="started",
            actor=actor,
            host=host,
            payload=payload,
        )

        target_host = _target_host_for_shop()
        runner_body = {
            "run_id": run_id,
            "scenario": payload.scenario,
            "rps": payload.rps,
            "duration_seconds": payload.duration_seconds,
            "target_url": target_host,
            "note": payload.note,
        }
        code, body = await _call_runner(
            "POST", "/internal/run", json_body=runner_body
        )
        if code == 409:
            # Concurrency=1 race — surface the runner's active_run_id.
            active = (body or {}).get("active_run_id") or (body or {}).get("run_id")
            _emit_lifecycle_event(
                run_id=run_id,
                status_value="rejected",
                actor=actor,
                host=host,
                payload=payload,
                reason=f"concurrency_active_run_id={active}",
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "status": "active",
                    "active_run_id": active,
                    "message": "Another stress run is already active.",
                },
            )
        if code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_RUNNER_UNAVAILABLE_DETAIL,
            )

    return {
        "run_id": run_id,
        "status": "started",
        "scenario": payload.scenario,
        "rps": payload.rps,
        "duration_seconds": payload.duration_seconds,
        "target_host": target_host,
    }


@router.post("/clear")
async def clear_run(request: Request) -> dict[str, Any]:
    actor = require_admin_user(request)
    host = _require_admin_host(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.stress.clear") as span:
        span.set_attribute("admin.actor", actor.get("username", "unknown"))
        span.set_attribute("admin.host", host)

        # Check current runner state — if idle, return idempotently with no
        # audit emission (clear is a no-op against an empty state).
        state_code, state_body = await _call_runner("GET", "/internal/state")
        active_run_id: str | None = None
        if state_code == 200:
            if state_body.get("status") == "idle" or not state_body.get("run_id"):
                return {"status": "idle"}
            active_run_id = state_body.get("run_id")

        clear_code, _clear_body = await _call_runner("POST", "/internal/clear")
        if clear_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_RUNNER_UNAVAILABLE_DETAIL,
            )

        # Audit emission AFTER successful clear so the counter does not
        # over-report for transient connectivity blips.
        _emit_lifecycle_event(
            run_id=active_run_id or "unknown",
            status_value="stopped",
            actor=actor,
            host=host,
        )
        return {"status": "stopped", "run_id": active_run_id}


# HTML page route
_templates: Jinja2Templates | None = None


def _get_templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _templates = Jinja2Templates(directory=os.path.join(server_dir, "templates"))
    return _templates


_FALLBACK_PAGE_HTML = (
    '<!doctype html><html><head><meta charset="utf-8">'
    "<title>OKE stress test</title></head>"
    '<body><script nonce="{nonce}">/* nav_key="stress" */</script>'
    "<h1>OKE stress test</h1>"
    "<p>The stress_test_admin.html template will be authored by "
    "Plan 07-06. This fallback keeps the page route discoverable and "
    "preserves the csp_nonce + nav_key='stress' contract.</p>"
    "</body></html>"
)


# Plan 07-06 base.html consumer reads nav_key="stress" from the template
# context dict below to render the sidebar entry as active. The literal
# nav_key="stress" appears here so Plan 07-05 test 17 can grep the source.
_NAV_KEY_STRESS = "stress"  # nav_key="stress" — Plan 07-06 contract


@_PAGE_ROUTER.get("/stress-test", response_class=HTMLResponse)
def stress_admin_page(request: Request) -> HTMLResponse:
    nonce = getattr(request.state, "csp_nonce", "")
    template_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
    )
    template_path = os.path.join(template_dir, "stress_test_admin.html")
    context = {
        "title": "OKE stress test",
        "brand_name": os.getenv("APP_NAME", "Enterprise CRM"),
        "service_name": os.getenv("SERVICE_NAME_CRM", "octo-enterprise-crm"),
        "app_name": "crm",
        "app_version": os.getenv("APP_VERSION", "0.0.0"),
        "rum_configured": False,
        "apm_console_url": getattr(cfg, "apm_console_url", "") or "",
        "opsi_console_url": getattr(cfg, "opsi_console_url", "") or "",
        "db_management_console_url": getattr(cfg, "db_management_console_url", "") or "",
        "log_analytics_console_url": getattr(cfg, "log_analytics_console_url", "") or "",
        "csp_nonce": nonce,
        "nav_key": _NAV_KEY_STRESS,
        "dns_domain": getattr(cfg, "dns_domain", "") or "",
    }
    if not os.path.isfile(template_path):
        # Plan 07-06 owns the template authoring; render a minimal HTML
        # placeholder that still satisfies the CSP nonce + nav_key='stress'
        # contract so Phase 07 plans downstream can wire the nav entry.
        body = _FALLBACK_PAGE_HTML.format(nonce=nonce or "")
        return HTMLResponse(content=body, status_code=200)
    templates = _get_templates()
    return templates.TemplateResponse(request, "stress_test_admin.html", context)


page_router = _PAGE_ROUTER
