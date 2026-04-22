"""FastAPI app exposing the load-control REST surface.

Routes:
    GET  /profiles            - list the 12 profiles
    GET  /profiles/{name}     - one profile detail
    POST /runs                - launch a run (body: profile, duration_seconds, operator)
    GET  /runs                - list recent runs
    GET  /runs/{run_id}       - run detail
    DELETE /runs/{run_id}     - cancel a run (best effort)
    GET  /health              - liveness + ledger check

The app is **stateless per-instance**: ledger holds the truth. Run two
replicas behind a Service and requests round-robin safely.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from . import events
from .executor import ExecutorBackend, wait_then_mark_complete
from .profiles import ProfileName, get_profile, list_profiles
from .runs import InMemoryLedger, Ledger, LocalJsonLedger, Run, RunState, _now_iso

logger = logging.getLogger(__name__)


class LaunchRequest(BaseModel):
    profile: str = Field(..., description="Profile name from /profiles")
    duration_seconds: int = Field(default=300, ge=10, le=3600)
    operator: str = Field(default="anonymous", max_length=80)

    @field_validator("profile")
    @classmethod
    def _known_profile(cls, v: str) -> str:
        try:
            ProfileName(v)
        except ValueError:
            raise ValueError(
                f"unknown profile '{v}'; valid: "
                + ", ".join(p.value for p in ProfileName)
            )
        return v


def create_app(
    *,
    ledger: Ledger | None = None,
    executor: ExecutorBackend | None = None,
) -> FastAPI:
    """Factory so tests can pass their own ledger + executor."""
    ledger = ledger or LocalJsonLedger()

    if executor is None:
        # Build the default executor with real HTTPX clients pointed at
        # the traffic-generator + chaos admin from env.
        import os

        traffic_base = os.getenv(
            "TRAFFIC_GENERATOR_URL", "http://traffic-generator.octo-traffic.svc.cluster.local:8080"
        )
        chaos_base = os.getenv(
            "CRM_CHAOS_ADMIN_URL", "http://enterprise-crm-portal.octo-backend-prod.svc.cluster.local:8080"
        )
        executor = ExecutorBackend(
            traffic_generator_client=httpx.AsyncClient(base_url=traffic_base, timeout=5.0),
            chaos_admin_client=httpx.AsyncClient(base_url=chaos_base, timeout=5.0),
        )

    app = FastAPI(
        title="octo-load-control",
        version="1.0.0",
        description="Named workload-profile orchestrator for octo-apm-demo.",
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "ledger_type": type(ledger).__name__}

    @app.get("/profiles")
    async def profiles_list() -> list[dict[str, Any]]:
        return [p.as_dict() for p in list_profiles()]

    @app.get("/profiles/{name}")
    async def profiles_get(name: str) -> dict[str, Any]:
        try:
            return get_profile(name).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/runs", status_code=status.HTTP_202_ACCEPTED)
    async def runs_create(body: LaunchRequest) -> dict[str, Any]:
        profile = get_profile(body.profile)
        run = Run.new(
            profile=profile,
            operator=body.operator,
            duration_seconds=body.duration_seconds,
        )
        ledger.append(run)

        run.state = RunState.STARTING
        run.started_at = _now_iso()
        ledger.update(run)
        await events.emit_run_state(run=run, state_suffix="started")

        try:
            run.executor_metadata = await executor.dispatch(profile=profile, run=run)
        except Exception as exc:
            run.state = RunState.FAILED
            run.error = str(exc)
            run.completed_at = _now_iso()
            ledger.update(run)
            await events.emit_run_state(run=run, state_suffix="failed")
            raise HTTPException(status_code=500, detail=f"dispatch failed: {exc}")

        run.state = RunState.RUNNING
        ledger.update(run)

        # Background task — don't await; return run_id so operator can poll.
        asyncio.create_task(_watch_and_finalize(run, ledger, executor, profile))

        return run.__dict__

    async def _watch_and_finalize(run, ledger_, executor_, profile) -> None:
        await wait_then_mark_complete(run, ledger_, executor_, profile)
        suffix = {
            RunState.SUCCEEDED: "succeeded",
            RunState.FAILED: "failed",
            RunState.CANCELLED: "cancelled",
        }.get(run.state, "succeeded")
        await events.emit_run_state(run=run, state_suffix=suffix)

    @app.get("/runs")
    async def runs_list(limit: int = 50) -> list[dict[str, Any]]:
        return [r.__dict__ for r in ledger.list_recent(limit=limit)]

    @app.get("/runs/{run_id}")
    async def runs_get(run_id: str) -> dict[str, Any]:
        r = ledger.get(run_id)
        if r is None:
            raise HTTPException(status_code=404, detail="run not found")
        return r.__dict__

    @app.delete("/runs/{run_id}")
    async def runs_delete(run_id: str) -> dict[str, Any]:
        r = ledger.get(run_id)
        if r is None:
            raise HTTPException(status_code=404, detail="run not found")
        if r.state in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED):
            return {"ok": True, "noop": True, "already_terminal": r.state.value}
        r.state = RunState.CANCELLED
        r.completed_at = _now_iso()
        ledger.update(r)
        await events.emit_run_state(run=r, state_suffix="cancelled")
        return {"ok": True, "cancelled": r.run_id}

    return app


# Module-level default app for `uvicorn octo_load_control.api:app`.
app = create_app(ledger=LocalJsonLedger())
