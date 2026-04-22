"""FastAPI surface for the remediator.

Routes:
    POST /events/alarm              OCI Notifications → webhook
    GET  /runs                      list recent proposals + executions
    GET  /runs/{run_id}             one run detail
    POST /runs/{run_id}/approve     operator-approve a HIGH-tier run
    POST /runs/{run_id}/reject      operator-reject
    GET  /playbooks                 list catalog
    GET  /health
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from .playbooks import CATALOG
from .playbooks.base import (
    ExecutionContext,
    RemediationRun,
    RemediationState,
    RemediationTier,
    _now_iso,
)

logger = logging.getLogger(__name__)


class AlarmWebhookBody(BaseModel):
    id: str
    title: str | None = None
    body: str | None = None
    severity: str | None = None
    metric_name: str | None = None
    dimensions: dict[str, str] | None = None
    annotations: dict[str, str] | None = None


class _RunStore:
    """In-memory store — swap for Redis stream in production (KG-036)."""

    def __init__(self) -> None:
        self._runs: dict[str, RemediationRun] = {}

    def add(self, run: RemediationRun) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> RemediationRun | None:
        return self._runs.get(run_id)

    def list_recent(self, limit: int = 50) -> list[RemediationRun]:
        items = sorted(self._runs.values(), key=lambda r: r.proposed_at, reverse=True)
        return items[:limit]


def create_app(*, store: _RunStore | None = None) -> FastAPI:
    store = store or _RunStore()
    app = FastAPI(title="octo-remediator", version="1.0.0")
    auto_medium = os.getenv("OCTO_REMEDIATOR_AUTO_MEDIUM", "false").lower() == "true"

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "auto_medium": auto_medium}

    @app.get("/playbooks")
    async def list_pb() -> list[dict[str, Any]]:
        return [
            {"name": p.name, "description": p.description, "tier": p.tier.value}
            for p in CATALOG
        ]

    @app.post("/events/alarm", status_code=status.HTTP_202_ACCEPTED)
    async def alarm_webhook(body: AlarmWebhookBody) -> dict[str, Any]:
        alarm = body.model_dump()

        # Find first matching playbook. Explicit order (low→med→high)
        # so safe actions fire before high-impact ones.
        matched: list[RemediationRun] = []
        for playbook in sorted(CATALOG, key=lambda p: _tier_priority(p.tier)):
            if not playbook.matches(alarm):
                continue
            params = playbook.extract_params(alarm)
            run = RemediationRun.propose(
                playbook=playbook,
                alarm_id=alarm["id"],
                alarm_summary=alarm.get("title") or alarm.get("body") or "",
                params=params,
            )
            store.add(run)
            matched.append(run)

            # Auto-execute if tier allows
            if playbook.tier == RemediationTier.LOW or (
                playbook.tier == RemediationTier.MEDIUM and auto_medium
            ):
                await _execute(run, playbook, alarm, store)

        return {
            "alarm_id": alarm["id"],
            "proposed_runs": [r.run_id for r in matched],
            "matched_playbooks": [r.playbook_name for r in matched],
        }

    @app.get("/runs")
    async def runs_list(limit: int = 50) -> list[dict[str, Any]]:
        return [_dump(r) for r in store.list_recent(limit=limit)]

    @app.get("/runs/{run_id}")
    async def runs_get(run_id: str) -> dict[str, Any]:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _dump(run)

    @app.post("/runs/{run_id}/approve")
    async def runs_approve(run_id: str, body: dict[str, str] | None = None) -> dict[str, Any]:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if run.state != RemediationState.PROPOSED:
            raise HTTPException(
                status_code=409,
                detail=f"run is {run.state.value}; only PROPOSED runs can be approved",
            )
        run.approver = (body or {}).get("approver", "anonymous")
        run.state = RemediationState.APPROVED

        pb_map = {p.name: p for p in CATALOG}
        playbook = pb_map[run.playbook_name]
        alarm = {"id": run.alarm_id, "body": run.alarm_summary, "annotations": run.params}
        await _execute(run, playbook, alarm, store)
        return _dump(run)

    @app.post("/runs/{run_id}/reject")
    async def runs_reject(run_id: str, body: dict[str, str] | None = None) -> dict[str, Any]:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if run.state != RemediationState.PROPOSED:
            raise HTTPException(
                status_code=409,
                detail=f"run is {run.state.value}; only PROPOSED runs can be rejected",
            )
        run.state = RemediationState.REJECTED
        run.completed_at = _now_iso()
        run.approver = (body or {}).get("approver", "anonymous")
        return _dump(run)

    return app


async def _execute(run, playbook, alarm, store: _RunStore) -> None:
    run.state = RemediationState.RUNNING
    run.started_at = _now_iso()
    store.add(run)
    ctx = ExecutionContext(run=run, alarm=alarm)
    try:
        run.actions = await playbook.execute(ctx)
        run.state = RemediationState.SUCCEEDED
    except Exception as exc:
        run.state = RemediationState.FAILED
        run.error = str(exc)
    finally:
        run.completed_at = _now_iso()
        store.add(run)


def _tier_priority(tier: RemediationTier) -> int:
    return {"low": 0, "medium": 1, "high": 2}[tier.value]


def _dump(run) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "playbook_name": run.playbook_name,
        "tier": run.tier.value,
        "alarm_id": run.alarm_id,
        "alarm_summary": run.alarm_summary,
        "params": run.params,
        "state": run.state.value,
        "proposed_at": run.proposed_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "approver": run.approver,
        "error": run.error,
        "actions": run.actions,
    }


app = create_app()
