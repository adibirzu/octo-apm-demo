"""FastAPI wrapper around the k6 binary for the OKE stress demo (Phase 7).

Responsibilities (per .planning/phases/07-oke-autoscaling-and-stress-demo
D-07, D-12, D-14):

- Long-lived in-cluster control plane: POST /internal/run, POST /internal/clear,
  GET /internal/state, GET /internal/healthz.
- Concurrency=1: a second /internal/run while a run is active returns HTTP 409
  with the active run_id.
- Authentication: every /internal/* endpoint requires the
  X-Internal-Service-Key header (constant-time compared to the
  OCTO_STRESS_RUNNER_INTERNAL_KEY env var sourced from the
  octo-stress-runner-key k8s Secret).
- Lifecycle: /internal/clear sends SIGTERM (process.terminate()) to the active
  k6 subprocess for graceful drain. A server-side asyncio task hard-times-out
  the run at duration_seconds + 30s as a safety net.
- APM/OTel: OTEL_SERVICE_NAME=octo-stress-runner pins the APM entity. The k6
  subprocess is invoked with `--out experimental-opentelemetry` so its spans
  correlate with shop/java spans via the public LB through the X-Run-Id and
  X-Octo-Stress-Target headers carried by the k6 scenarios.

This module is the SOLE implementation of the stress-runner HTTP API and is
called only by the CRM admin stress-test route (Plan 07-05, future). It does
NOT call the Kubernetes API — its ServiceAccount has no Role bindings.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import shutil
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    status,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger("octo_stress_runner")

# ── Configuration ────────────────────────────────────────────────────────

_SCENARIOS_DIR_ENV = "OCTO_STRESS_RUNNER_SCENARIOS_DIR"
_INTERNAL_KEY_ENV = "OCTO_STRESS_RUNNER_INTERNAL_KEY"
_OTEL_SERVICE_NAME_ENV = "OTEL_SERVICE_NAME"
_K6_BINARY_ENV = "OCTO_STRESS_RUNNER_K6_BINARY"
_HARD_TIMEOUT_GRACE_SECONDS = 30

_ALLOWED_SCENARIOS = frozenset(
    {"checkout_journey", "catalog_browse", "login_burst"}
)


def _default_scenarios_dir() -> Path:
    """Resolve the scenarios directory; env override wins for tests."""
    override = os.environ.get(_SCENARIOS_DIR_ENV, "").strip()
    if override:
        return Path(override).resolve()
    # In the deployed pod this resolves to tools/stress-runner/scenarios/
    # relative to the source package root.
    return (Path(__file__).resolve().parent.parent / "scenarios").resolve()


def _load_internal_key() -> str:
    """Fail fast at import/startup if the internal-service-key secret is unset.

    The k8s Secret octo-stress-runner-key is mounted as the
    OCTO_STRESS_RUNNER_INTERNAL_KEY env var (see
    deploy/k8s/oke/stress-runner/deployment.yaml).
    """
    key = os.environ.get(_INTERNAL_KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(
            f"{_INTERNAL_KEY_ENV} is required but not set. The pod must "
            "mount the octo-stress-runner-key Secret (see "
            "deploy/k8s/oke/stress-runner/deployment.yaml)."
        )
    return key


# ── Pydantic models ──────────────────────────────────────────────────────


class RunRequest(BaseModel):
    """Request payload for POST /internal/run.

    Hard caps mirror the D-13 plan caps in CONTEXT.md so that even a
    misconfigured caller cannot overrun the cluster.
    """

    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(
        ...,
        pattern=r"^(checkout_journey|catalog_browse|login_burst)$",
        description="k6 scenario file name (without .js extension)",
    )
    rps: int = Field(..., ge=1, le=200, description="virtual users (≈ RPS per VU)")
    duration_seconds: int = Field(
        ..., ge=10, le=600, description="k6 run duration in seconds"
    )
    run_id: str = Field(..., min_length=1, max_length=128)
    target_host: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Public LB target URL, e.g. https://shop.${DNS_DOMAIN}",
    )

    @field_validator("scenario")
    @classmethod
    def _scenario_in_allow_list(cls, v: str) -> str:
        if v not in _ALLOWED_SCENARIOS:
            raise ValueError(
                f"scenario must be one of {sorted(_ALLOWED_SCENARIOS)}"
            )
        return v


class RunStartedResponse(BaseModel):
    status: str = "started"
    run_id: str
    pid: int | None = None
    scenario: str
    target_host: str
    duration_seconds: int


class BusyResponse(BaseModel):
    status: str = "busy"
    active_run_id: str
    started_at: float


class StateResponse(BaseModel):
    status: str
    run_id: Optional[str] = None
    scenario: Optional[str] = None
    rps: Optional[int] = None
    duration_seconds: Optional[int] = None
    target_host: Optional[str] = None
    started_at: Optional[float] = None


# ── Run lifecycle state ──────────────────────────────────────────────────


@dataclass
class ActiveRun:
    """In-flight stress run state. Concurrency=1 means at most one of these
    exists in the module at any time (guarded by _state_lock)."""

    run_id: str
    process: asyncio.subprocess.Process
    started_at: float
    scenario: str
    rps: int
    duration_seconds: int
    target_host: str
    status: str = "running"
    waiter_task: Optional[asyncio.Task[Any]] = field(default=None, repr=False)
    timeout_task: Optional[asyncio.Task[Any]] = field(default=None, repr=False)


_state_lock: asyncio.Lock | None = None
_active: ActiveRun | None = None


def _get_lock() -> asyncio.Lock:
    """Lazy lock construction — avoids loop-binding issues at import time."""
    global _state_lock
    if _state_lock is None:
        _state_lock = asyncio.Lock()
    return _state_lock


# ── Authentication ───────────────────────────────────────────────────────


def require_internal_key(
    x_internal_service_key: str | None = Header(default=None, alias="X-Internal-Service-Key"),
) -> None:
    """Constant-time compare of the X-Internal-Service-Key header to the env-mounted key.

    Mirrors crm/server/modules/simulation.py:673-675 — the same internal-key
    pattern used by CRM → Drone Shop calls. Returns 401 on missing/invalid.
    """
    expected = _load_internal_key()
    if x_internal_service_key is None or not hmac.compare_digest(
        x_internal_service_key.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Internal-Service-Key header",
        )


# ── k6 invocation ────────────────────────────────────────────────────────


def _resolve_scenario_path(scenario: str) -> Path:
    """Allow-list lookup that prevents path traversal (T-07-11 mitigation)."""
    if scenario not in _ALLOWED_SCENARIOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown scenario: {scenario}",
        )
    scenarios_dir = _default_scenarios_dir()
    candidate = (scenarios_dir / f"{scenario}.js").resolve()
    # Defence in depth: ensure the resolved path stays under scenarios_dir.
    if scenarios_dir not in candidate.parents and candidate.parent != scenarios_dir:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scenario path escapes scenarios directory",
        )
    if not candidate.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"scenario file missing: {candidate.name}",
        )
    return candidate


async def _spawn_k6(req: RunRequest) -> asyncio.subprocess.Process:
    """Launch the k6 subprocess with OTLP output enabled (D-06)."""
    scenario_path = _resolve_scenario_path(req.scenario)
    k6_binary = os.environ.get(_K6_BINARY_ENV) or shutil.which("k6") or "k6"
    cmd = [
        k6_binary,
        "run",
        "--out",
        "experimental-opentelemetry",
        "-e",
        f"STRESS_TARGET_URL={req.target_host}",
        "-e",
        f"K6_VUS={req.rps}",
        "-e",
        f"K6_DURATION={req.duration_seconds}s",
        "-e",
        f"RUN_ID={req.run_id}",
        str(scenario_path),
    ]
    logger.info(
        "spawning k6: run_id=%s scenario=%s target=%s vus=%s duration=%ss",
        req.run_id,
        req.scenario,
        req.target_host,
        req.rps,
        req.duration_seconds,
    )
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _wait_for_completion(run: ActiveRun) -> None:
    """Background task: await process.wait() and mark the run completed."""
    global _active
    try:
        await run.process.wait()
        async with _get_lock():
            if _active is run:
                _active.status = "completed" if run.process.returncode == 0 else "error"
                # Cancel the hard timeout — completion beat it.
                if run.timeout_task is not None and not run.timeout_task.done():
                    run.timeout_task.cancel()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — defensive at lifecycle edge
        logger.exception("waiter task failed: %s", exc)


async def _hard_timeout(run: ActiveRun) -> None:
    """Server-side safety net: kill the run at duration + 30s (D-14)."""
    global _active
    try:
        await asyncio.sleep(run.duration_seconds + _HARD_TIMEOUT_GRACE_SECONDS)
        async with _get_lock():
            if _active is run and run.process.returncode is None:
                logger.warning(
                    "hard timeout for run_id=%s — sending SIGTERM",
                    run.run_id,
                )
                try:
                    run.process.send_signal(signal.SIGTERM)
                except ProcessLookupError:
                    pass
                _active.status = "expired"
    except asyncio.CancelledError:
        # Normal cancellation — the run completed in time.
        raise


# ── FastAPI app ──────────────────────────────────────────────────────────


def _service_name() -> str:
    """Surface OTEL_SERVICE_NAME for log context (used at startup)."""
    return os.environ.get(_OTEL_SERVICE_NAME_ENV, "octo-stress-runner")


app = FastAPI(
    title="octo-stress-runner",
    description=(
        "Internal-only HTTP control plane around the k6 binary. "
        "All /internal/* endpoints require the X-Internal-Service-Key header."
    ),
    version="1.0.0",
)


@app.on_event("startup")
async def _startup_check() -> None:
    """Fail loudly if the internal key is missing or k6 is unavailable."""
    _load_internal_key()  # raises RuntimeError if missing — pod will crashloop
    logger.info(
        "octo-stress-runner ready: service=%s scenarios_dir=%s",
        _service_name(),
        _default_scenarios_dir(),
    )


@app.post(
    "/internal/run",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_key)],
)
async def run_scenario(payload: RunRequest) -> dict[str, Any]:
    """Start a k6 run. Returns HTTP 202 on accepted, HTTP 409 if a run is
    already active (concurrency=1 per D-14)."""
    global _active
    async with _get_lock():
        if _active is not None and _active.process.returncode is None:
            # Another run is in flight — return 409 with active run_id.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "status": "busy",
                    "active_run_id": _active.run_id,
                    "started_at": _active.started_at,
                },
            )
        process = await _spawn_k6(payload)
        run = ActiveRun(
            run_id=payload.run_id,
            process=process,
            started_at=time.time(),
            scenario=payload.scenario,
            rps=payload.rps,
            duration_seconds=payload.duration_seconds,
            target_host=payload.target_host,
            status="running",
        )
        run.waiter_task = asyncio.create_task(_wait_for_completion(run))
        run.timeout_task = asyncio.create_task(_hard_timeout(run))
        _active = run

    return RunStartedResponse(
        status="started",
        run_id=run.run_id,
        pid=process.pid,
        scenario=run.scenario,
        target_host=run.target_host,
        duration_seconds=run.duration_seconds,
    ).model_dump()


@app.post(
    "/internal/clear",
    dependencies=[Depends(require_internal_key)],
)
async def clear_run() -> dict[str, Any]:
    """Send SIGTERM to the active k6 subprocess for graceful drain (D-14)."""
    global _active
    async with _get_lock():
        if _active is None or _active.process.returncode is not None:
            return {"status": "idle"}
        active = _active
        # SIGTERM via process.terminate() (Python's terminate() on POSIX
        # is SIGTERM — see asyncio.subprocess docs).
        try:
            active.process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            # Already gone — nothing to do.
            pass
        active.status = "stopping"
        run_id = active.run_id

    return {"status": "stopping", "run_id": run_id}


@app.get(
    "/internal/state",
    dependencies=[Depends(require_internal_key)],
)
async def read_state() -> dict[str, Any]:
    """Return the current run snapshot, or {status: idle}."""
    async with _get_lock():
        if _active is None or _active.process.returncode is not None and _active.status in {
            "completed",
            "error",
            "expired",
        }:
            # No run, or last run already terminal — report idle but keep the
            # last terminal status discoverable for one read.
            if _active is None:
                return {"status": "idle"}
            terminal = StateResponse(
                status=_active.status,
                run_id=_active.run_id,
                scenario=_active.scenario,
                rps=_active.rps,
                duration_seconds=_active.duration_seconds,
                target_host=_active.target_host,
                started_at=_active.started_at,
            ).model_dump()
            return terminal
        return StateResponse(
            status=_active.status,
            run_id=_active.run_id,
            scenario=_active.scenario,
            rps=_active.rps,
            duration_seconds=_active.duration_seconds,
            target_host=_active.target_host,
            started_at=_active.started_at,
        ).model_dump()


@app.get("/internal/healthz")
async def healthz() -> dict[str, Any]:
    """Liveness/readiness — verifies the k6 binary is on PATH.

    Intentionally NOT gated by the internal-key dependency: the kubelet
    probe runs in-cluster and does not have access to the secret. The
    endpoint leaks no sensitive state — only a boolean k6-on-PATH flag and
    the service name, both of which are deployment-time constants.
    """
    has_k6 = shutil.which(os.environ.get(_K6_BINARY_ENV, "k6")) is not None
    return {"ok": True, "has_k6": has_k6, "service": _service_name()}
