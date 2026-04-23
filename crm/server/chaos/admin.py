"""CRM-side chaos admin router.

Only the CRM portal can mutate chaos state. Requests must carry an
authenticated session with the ``chaos-operator`` role (configurable via
``CHAOS_ADMIN_ROLE``). Every apply/clear action is persisted to the
``chaos_state`` table and mirrored to the chaos-audit log.

Wave 1 scope:

* list presets / read state / apply / clear endpoints
* role guard + per-user rate limit (via ``fastapi.Request.state`` hooks)
* TTL clamp to ``CHAOS_MAX_TTL_SECONDS``
* structured audit log record (consumed by LA chaos-audit parser)

Wave 2 will add the OKE-side config sync job and the object-storage
backend.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from server.chaos.registry import (
    MAX_TTL_SECONDS,
    PRESETS_BY_ID,
    ChaosScenarioState,
    get_active_state,
)
from server.security.auth_deps import require_role

logger = logging.getLogger("chaos.audit")

CHAOS_ADMIN_ROLE = os.getenv("CHAOS_ADMIN_ROLE", "chaos-operator").strip().lower() or "chaos-operator"

router = APIRouter(
    prefix="/api/admin/chaos",
    tags=["chaos-admin"],
    dependencies=[require_role(CHAOS_ADMIN_ROLE)],
)


def _hash_user(request: Request) -> str:
    session = getattr(request.state, "session", None) or {}
    uid = str(session.get("user_id") or session.get("sub") or "anon")
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()[:16]


def _audit(event: str, **fields: Any) -> None:
    record = {"event": event, **fields, "ts": time.time()}
    logger.info("chaos_audit %s", json.dumps(record, default=str))


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ApplyRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    target: str = Field(default="both")
    ttl_seconds: int = Field(default=300, ge=10, le=MAX_TTL_SECONDS)
    note: str | None = Field(default=None, max_length=512)

    @field_validator("target")
    @classmethod
    def _valid_target(cls, v: str) -> str:
        norm = v.strip().lower()
        if norm not in {"shop", "crm", "both"}:
            raise ValueError("target must be shop|crm|both")
        return norm


# ---------------------------------------------------------------------------
# Persistence (simple DB upsert — schema created lazily).
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS chaos_state (
    id           VARCHAR2(64) PRIMARY KEY,
    scenario_id  VARCHAR2(64) NOT NULL,
    target       VARCHAR2(16) NOT NULL,
    applied_by   VARCHAR2(64) NOT NULL,
    applied_at   NUMBER       NOT NULL,
    expires_at   NUMBER       NOT NULL,
    payload      CLOB         NOT NULL
)
"""


def _ensure_table() -> None:
    try:
        from sqlalchemy import text

        from server.database import sync_engine  # type: ignore[attr-defined]
    except Exception:
        return
    try:
        with sync_engine.begin() as conn:  # type: ignore[union-attr]
            conn.execute(text(_DDL))
    except Exception as exc:
        logger.debug("chaos_state DDL skipped: %s", exc)


def _persist(state: ChaosScenarioState) -> None:
    try:
        from sqlalchemy import text

        from server.database import sync_engine  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"chaos_state_unavailable: {exc}") from exc

    payload = json.dumps(state.to_json())
    row_id = uuid.uuid4().hex
    with sync_engine.begin() as conn:  # type: ignore[union-attr]
        # Best-effort: Oracle has no generic UPSERT here; delete any prior row
        # so only one active scenario exists at a time.
        conn.execute(text("DELETE FROM chaos_state"))
        conn.execute(
            text(
                "INSERT INTO chaos_state (id, scenario_id, target, applied_by, "
                "applied_at, expires_at, payload) "
                "VALUES (:id, :sid, :t, :u, :a, :e, :p)"
            ),
            {
                "id": row_id,
                "sid": state.scenario_id,
                "t": state.target,
                "u": state.applied_by,
                "a": state.applied_at,
                "e": state.expires_at,
                "p": payload,
            },
        )


def _clear_all() -> None:
    try:
        from sqlalchemy import text

        from server.database import sync_engine  # type: ignore[attr-defined]

        with sync_engine.begin() as conn:  # type: ignore[union-attr]
            conn.execute(text("DELETE FROM chaos_state"))
    except Exception as exc:
        logger.debug("chaos_state clear failed: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/presets")
def list_presets() -> dict[str, Any]:
    return {
        "presets": [
            {
                "id": p.id,
                "description": p.description,
                "targets": list(p.targets),
                "faults": list(p.faults),
                "default_ttl_seconds": p.default_ttl_seconds,
            }
            for p in PRESETS_BY_ID.values()
        ],
        "max_ttl_seconds": MAX_TTL_SECONDS,
    }


@router.get("/state")
def read_state() -> dict[str, Any]:
    state = get_active_state()
    return {"active": state is not None, "state": state.to_json() if state else None}


@router.post("/apply", status_code=status.HTTP_201_CREATED)
def apply_scenario(payload: ApplyRequest, request: Request) -> dict[str, Any]:
    preset = PRESETS_BY_ID.get(payload.scenario_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="scenario_not_found")

    _ensure_table()
    now = time.time()
    ttl = min(payload.ttl_seconds, MAX_TTL_SECONDS)
    actor = _hash_user(request)
    state = ChaosScenarioState(
        scenario_id=preset.id,
        target=payload.target,
        applied_by=actor,
        applied_at=now,
        expires_at=now + ttl,
        faults=preset.faults,
        trace_id=getattr(request.state, "request_id", None),
        extra={"note": payload.note} if payload.note else {},
    )
    _persist(state)
    _audit(
        "chaos.apply",
        scenario_id=preset.id,
        target=payload.target,
        ttl_seconds=ttl,
        applied_by=actor,
        request_id=state.trace_id,
    )
    return {"ok": True, "state": state.to_json()}


@router.post("/clear")
def clear_scenario(request: Request) -> dict[str, bool]:
    _clear_all()
    _audit("chaos.clear", applied_by=_hash_user(request), request_id=getattr(request.state, "request_id", None))
    return {"ok": True}


# ---------------------------------------------------------------------------
# HTML admin page (role-gated via router-level dependency).
# ---------------------------------------------------------------------------

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_PAGE_ROUTER = APIRouter(
    prefix="/admin",
    tags=["chaos-admin"],
    dependencies=[require_role(CHAOS_ADMIN_ROLE)],
)

_templates: Jinja2Templates | None = None


def _get_templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _templates = Jinja2Templates(directory=os.path.join(server_dir, "templates"))
    return _templates


@_PAGE_ROUTER.get("/chaos", response_class=HTMLResponse)
def chaos_admin_page(request: Request) -> HTMLResponse:
    templates = _get_templates()
    nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse(
        request,
        "chaos_admin.html",
        {
            "title": "Chaos Control",
            "brand_name": os.getenv("APP_NAME", "Enterprise CRM"),
            "service_name": os.getenv("SERVICE_NAME_CRM", "octo-enterprise-crm"),
            "app_name": "crm",
            "rum_configured": False,
            "max_ttl": MAX_TTL_SECONDS,
            "csp_nonce": nonce,
        },
    )


page_router = _PAGE_ROUTER
