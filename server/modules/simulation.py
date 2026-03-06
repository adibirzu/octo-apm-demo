"""Simulation/chaos engineering module — toggle failures on demand."""

from fastapi import APIRouter
from server.middleware.chaos import chaos

router = APIRouter(prefix="/api/simulate", tags=["simulation"])


@router.get("/status")
async def simulation_status():
    return {
        "db_latency_ms": chaos.db_latency_ms,
        "db_disconnect": chaos.db_disconnect,
        "error_rate": chaos.error_rate,
        "slow_responses": chaos.slow_responses,
    }


@router.post("/configure")
async def configure(payload: dict):
    if "error_rate" in payload:
        chaos.error_rate = float(payload["error_rate"])
    if "slow_responses" in payload:
        chaos.slow_responses = bool(payload["slow_responses"])
    if "db_latency_ms" in payload:
        chaos.db_latency_ms = int(payload["db_latency_ms"])
    if "db_disconnect" in payload:
        chaos.db_disconnect = bool(payload["db_disconnect"])
    return {
        "status": "configured",
        "db_latency_ms": chaos.db_latency_ms,
        "db_disconnect": chaos.db_disconnect,
        "error_rate": chaos.error_rate,
        "slow_responses": chaos.slow_responses,
    }


@router.post("/reset")
async def reset():
    chaos.db_latency_ms = 0
    chaos.db_disconnect = False
    chaos.error_rate = 0.0
    chaos.slow_responses = False
    return {"status": "reset"}


@router.post("/db-latency")
async def db_latency(payload: dict):
    chaos.db_latency_ms = int(payload.get("latency_ms", 0))
    return {"status": "ok", "db_latency_ms": chaos.db_latency_ms}


@router.post("/error-burst")
async def error_burst(payload: dict):
    chaos.error_rate = float(payload.get("rate", 0.3))
    return {"status": "ok", "error_rate": chaos.error_rate}
