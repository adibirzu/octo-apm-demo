"""Chaos scenario registry.

Presets describe *what* can go wrong. The runtime state (what is active
right now) is stored out of process so that multiple app replicas agree
on the same scenario. This file is identical between Shop and CRM; the
*surface* differs: Shop only reads, CRM can write.

State backend selection is controlled by ``CHAOS_STATE_BACKEND``:

* ``db`` — row in ``chaos_state`` table (default).
* ``object_storage`` — JSON object in OCI Object Storage bucket
  ``CHAOS_STATE_BUCKET`` (implementation in wave 2).

The reader path is deliberately defensive: any error collapses to an
"inactive" state so application traffic is never blocked by chaos
infrastructure issues.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

SCENARIO_ID_PATTERN = "^[a-z0-9][a-z0-9-]{1,63}$"
MAX_TTL_SECONDS = int(os.getenv("CHAOS_MAX_TTL_SECONDS", "3600"))


@dataclass(frozen=True)
class ChaosScenario:
    """Immutable description of a chaos scenario preset."""

    id: str
    description: str
    targets: tuple[str, ...]            # e.g. ("shop",), ("crm",), ("shop", "crm")
    faults: tuple[str, ...]             # identifiers consumed by middleware
    default_ttl_seconds: int = 300


@dataclass(frozen=True)
class ChaosScenarioState:
    """Runtime state of an applied scenario."""

    scenario_id: str
    target: str                         # "shop" | "crm" | "both"
    applied_by: str                     # hashed user id from CRM auth
    applied_at: float
    expires_at: float
    faults: tuple[str, ...]
    trace_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "target": self.target,
            "applied_by": self.applied_by,
            "applied_at": self.applied_at,
            "expires_at": self.expires_at,
            "faults": list(self.faults),
            "trace_id": self.trace_id,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ChaosScenarioState":
        return cls(
            scenario_id=str(payload["scenario_id"]),
            target=str(payload.get("target", "both")),
            applied_by=str(payload.get("applied_by", "unknown")),
            applied_at=float(payload.get("applied_at", time.time())),
            expires_at=float(payload["expires_at"]),
            faults=tuple(payload.get("faults") or ()),
            trace_id=payload.get("trace_id"),
            extra=dict(payload.get("extra") or {}),
        )


PRESETS: tuple[ChaosScenario, ...] = (
    ChaosScenario(
        id="db-slow-checkout",
        description="Inject 2–5s latency on SQL during /checkout flow.",
        targets=("shop",),
        faults=("db.slow", "workflow:checkout"),
    ),
    ChaosScenario(
        id="crm-sync-fail",
        description="Shop→CRM customer sync returns 502 50% of calls.",
        targets=("shop", "crm"),
        faults=("http.502", "path:/api/crm/sync"),
    ),
    ChaosScenario(
        id="payment-timeout",
        description="Payment gateway hangs for ~8s on 20% of calls.",
        targets=("shop",),
        faults=("http.timeout", "path:/api/payments"),
    ),
    ChaosScenario(
        id="deadlock-cart",
        description="Raise ORA-00060 deadlock on cart writes.",
        targets=("shop",),
        faults=("db.deadlock", "workflow:add-to-cart"),
    ),
    ChaosScenario(
        id="pool-exhaustion",
        description="Hold DB connections for 30s to exhaust the pool.",
        targets=("shop", "crm"),
        faults=("db.pool_hold",),
        default_ttl_seconds=600,
    ),
    ChaosScenario(
        id="crm-admin-abuse",
        description="Flood CRM admin endpoints to trigger WAF detections.",
        targets=("crm",),
        faults=("http.burst", "path:/api/admin"),
    ),
)

PRESETS_BY_ID: dict[str, ChaosScenario] = {p.id: p for p in PRESETS}


# ---------------------------------------------------------------------------
# Backend abstraction (read-only on Shop, read/write on CRM).
# ---------------------------------------------------------------------------

class _BackendError(RuntimeError):
    pass


def _backend_name() -> str:
    return os.getenv("CHAOS_STATE_BACKEND", "db").strip().lower() or "db"


def _read_from_db() -> ChaosScenarioState | None:
    """Read the latest non-expired scenario row from the ``chaos_state`` table.

    Falls back silently (returns ``None``) on any error so that app traffic
    is not impacted by chaos infrastructure problems.
    """
    try:
        from sqlalchemy import text

        from server.database import sync_engine  # type: ignore[attr-defined]
    except Exception:
        return None

    try:
        with sync_engine.connect() as conn:  # type: ignore[union-attr]
            row = conn.execute(
                text(
                    "SELECT payload FROM chaos_state "
                    "WHERE expires_at > :now "
                    "ORDER BY applied_at DESC FETCH FIRST 1 ROWS ONLY"
                ),
                {"now": time.time()},
            ).fetchone()
    except Exception as exc:
        logger.debug("chaos_state read failed: %s", exc)
        return None

    if row is None:
        return None
    raw = row[0]
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return ChaosScenarioState.from_json(payload)
    except Exception as exc:
        logger.warning("chaos_state payload malformed: %s", exc)
        return None


def get_active_state() -> ChaosScenarioState | None:
    """Return the currently active scenario state, or ``None``."""
    if os.getenv("CHAOS_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
        return None

    backend = _backend_name()
    state: ChaosScenarioState | None
    if backend == "db":
        state = _read_from_db()
    else:
        # Other backends are implemented in wave 2; default to inactive.
        logger.debug("chaos backend %r not yet implemented on reader", backend)
        state = None

    if state is not None and state.is_expired:
        return None
    return state
