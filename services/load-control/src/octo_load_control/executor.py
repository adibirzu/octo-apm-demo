"""Run executor dispatch.

Every :class:`ExecutorKind` has a matching function below that turns
a Profile + Run into a live side effect. Dispatch is async so we can
launch a long-running executor and immediately return the run_id to
the caller.

For phases not yet built (K8S_STRESS, VM_STRESS, EDGE_FUZZ, BROWSER_RUNNER
beyond scaffolding), the executor returns a friendly ``NotImplementedYet``
Run state so the control plane + docs are complete today.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .profiles import ExecutorKind, Profile
from .runs import Run, RunState

logger = logging.getLogger(__name__)


class ExecutorBackend:
    """Function table — one async call per ExecutorKind."""

    def __init__(self, *, traffic_generator_client, chaos_admin_client):
        self._traffic = traffic_generator_client
        self._chaos = chaos_admin_client

    async def dispatch(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        """Launch the executor for ``profile`` and return metadata recorded
        on the Run. Caller is responsible for persisting updates."""
        if profile.executor == ExecutorKind.TRAFFIC_GENERATOR:
            return await self._run_traffic_generator(profile=profile, run=run)
        if profile.executor == ExecutorKind.CHAOS_ADMIN:
            return await self._run_chaos_admin(profile=profile, run=run)
        if profile.executor == ExecutorKind.BROWSER_RUNNER:
            return {"status": "not-yet-implemented", "phase": 4}
        if profile.executor in (ExecutorKind.K8S_STRESS, ExecutorKind.VM_STRESS):
            return {"status": "not-yet-implemented", "phase": 8}
        if profile.executor == ExecutorKind.EDGE_FUZZ:
            return {"status": "not-yet-implemented", "phase": 3}
        raise ValueError(f"unknown executor kind: {profile.executor}")

    async def _run_traffic_generator(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        headers = {"X-Run-Id": run.run_id}
        payload = {
            "run_id": run.run_id,
            "profile": profile.name.value,
            "duration_seconds": run.duration_seconds,
            **profile.executor_args,
        }
        try:
            resp = await self._traffic.post("/control/start", json=payload, headers=headers)
            return {"status": "launched", "http_status": resp.status_code, "endpoint": "traffic-generator"}
        except Exception as exc:  # pragma: no cover
            logger.warning("traffic generator dispatch failed: %s", exc)
            return {"status": "dispatch_error", "error": str(exc)}

    async def _run_chaos_admin(self, *, profile: Profile, run: Run) -> dict[str, Any]:
        headers = {"X-Run-Id": run.run_id}
        payload = {
            "profile": profile.executor_args.get("chaos_profile", profile.name.value),
            "duration_seconds": run.duration_seconds,
            "intensity": profile.executor_args.get("intensity", "moderate"),
        }
        try:
            resp = await self._chaos.post("/api/admin/chaos/apply", json=payload, headers=headers)
            return {"status": "launched", "http_status": resp.status_code, "endpoint": "chaos-admin"}
        except Exception as exc:  # pragma: no cover
            logger.warning("chaos admin dispatch failed: %s", exc)
            return {"status": "dispatch_error", "error": str(exc)}


async def wait_then_mark_complete(run: Run, ledger, executor: ExecutorBackend, profile: Profile) -> None:
    """Sleep for ``run.duration_seconds`` then mark the run succeeded
    and persist. Exceptions → FAILED. Executed as a background task."""
    from .runs import _now_iso  # local to avoid cycle

    try:
        await asyncio.sleep(run.duration_seconds)
        run.state = RunState.SUCCEEDED
        run.completed_at = _now_iso()
    except asyncio.CancelledError:
        run.state = RunState.CANCELLED
        run.completed_at = _now_iso()
        raise
    except Exception as exc:  # pragma: no cover — defensive
        run.state = RunState.FAILED
        run.error = str(exc)
        run.completed_at = _now_iso()
    finally:
        ledger.update(run)
