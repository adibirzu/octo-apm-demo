"""Simulation/chaos engineering module — toggle failures on demand.

All mutation endpoints require IDCS SSO authentication. The ``/status``
endpoint also requires authentication so unauthenticated callers cannot
probe the chaos state.

Input clamping
--------------
- ``error_rate``: ``0.0 ≤ rate ≤ 1.0`` (fraction of requests that fail).
- ``db_latency_ms``: ``0 ≤ ms ≤ 30_000`` (simulated DB delay in ms).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from server.auth_security import require_sso_user
from server.middleware.chaos import chaos

router = APIRouter(prefix="/api/simulate", tags=["simulation"])

_MAX_ERROR_RATE = 1.0
_MAX_DB_LATENCY_MS = 30_000


def _clamp_error_rate(value: float) -> float:
    if not 0.0 <= value <= _MAX_ERROR_RATE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"error_rate must be between 0.0 and {_MAX_ERROR_RATE}",
        )
    return value


def _clamp_db_latency(value: int) -> int:
    if not 0 <= value <= _MAX_DB_LATENCY_MS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"db_latency_ms must be between 0 and {_MAX_DB_LATENCY_MS}",
        )
    return value


def _chaos_snapshot() -> dict:
    return {
        "db_latency_ms": chaos.db_latency_ms,
        "db_disconnect": chaos.db_disconnect,
        "error_rate": chaos.error_rate,
        "slow_responses": chaos.slow_responses,
    }


@router.get("/status")
async def simulation_status(user: dict = Depends(require_sso_user)):
    return _chaos_snapshot()


@router.post("/configure")
async def configure(payload: dict, user: dict = Depends(require_sso_user)):
    if "error_rate" in payload:
        chaos.error_rate = _clamp_error_rate(float(payload["error_rate"]))
    if "slow_responses" in payload:
        chaos.slow_responses = bool(payload["slow_responses"])
    if "db_latency_ms" in payload:
        chaos.db_latency_ms = _clamp_db_latency(int(payload["db_latency_ms"]))
    if "db_disconnect" in payload:
        chaos.db_disconnect = bool(payload["db_disconnect"])
    return {"status": "configured", "user": user.get("username"), **_chaos_snapshot()}


@router.post("/reset")
async def reset(user: dict = Depends(require_sso_user)):
    chaos.db_latency_ms = 0
    chaos.db_disconnect = False
    chaos.error_rate = 0.0
    chaos.slow_responses = False
    return {"status": "reset", "user": user.get("username")}


@router.post("/db-latency")
async def db_latency(payload: dict, user: dict = Depends(require_sso_user)):
    chaos.db_latency_ms = _clamp_db_latency(int(payload.get("latency_ms", 0)))
    return {"status": "ok", "db_latency_ms": chaos.db_latency_ms}


@router.post("/error-burst")
async def error_burst(payload: dict, user: dict = Depends(require_sso_user)):
    chaos.error_rate = _clamp_error_rate(float(payload.get("rate", 0.3)))
    return {"status": "ok", "error_rate": chaos.error_rate}
