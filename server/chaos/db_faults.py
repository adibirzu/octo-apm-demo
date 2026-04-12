"""SQLAlchemy chaos injection hooks.

Runs *inside* existing DB spans so that injected latency, deadlocks, and
connection holds are visible in APM + Log Analytics as first-class span
events. No monkey-patching — we attach to the standard SQLAlchemy
``before_cursor_execute`` event hook. The hook is installed once, is
idempotent, and is a no-op when:

* ``CHAOS_ENABLED`` is falsy,
* there is no active scenario from the registry,
* the request's current workflow is not targeted by the scenario, or
* the scenario has expired.

Faults supported in wave 2:

* ``db.slow`` — synchronous ``time.sleep`` for N ms (range configurable).
* ``db.deadlock`` — raises ``DBAPIError`` mimicking ORA-00060 on 50% of
  matching statements.
* ``db.pool_hold`` — holds the statement for a long period (emulating
  exhausted pool) on 10% of matching statements.

All injected faults emit a structured log line with the full correlation
context so LA searches can distinguish ``chaos.injected = 'true'`` from
organic errors.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from server.chaos.registry import ChaosScenarioState, get_active_state
from server.observability.workflow_context import current_workflow

try:
    from opentelemetry import trace as _otel_trace

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - defensive
    _OTEL_AVAILABLE = False

logger = logging.getLogger("chaos.db")

_INSTALLED: set[int] = set()


def _scenario_applies(state: ChaosScenarioState) -> bool:
    """Check whether the scenario targets the caller's workflow, if any."""
    wf = current_workflow()
    wf_id = wf.workflow_id if wf else None
    for fault in state.faults:
        if fault.startswith("workflow:"):
            if fault.removeprefix("workflow:") == wf_id:
                return True
    # Faults without a workflow filter match everything.
    return not any(f.startswith("workflow:") for f in state.faults)


def _emit_log(kind: str, state: ChaosScenarioState, extra: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "chaos": {
            "injected": True,
            "scenario": state.scenario_id,
            "fault": kind,
            "target": state.target,
        }
    }
    payload.update(extra)
    logger.warning("chaos_db %s", payload)
    if _OTEL_AVAILABLE:
        span = _otel_trace.get_current_span()
        if span is not None and span.is_recording():
            attributes: dict[str, Any] = {
                "chaos.injected": True,
                "chaos.scenario": state.scenario_id,
                "chaos.fault": kind,
                "chaos.target": state.target,
            }
            for k, v in extra.items():
                # OTel attribute types: only primitives.
                if isinstance(v, (str, int, float, bool)):
                    attributes[f"chaos.{k}"] = v
            span.add_event("chaos.db.fault", attributes=attributes)


def _inject(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:  # noqa: D401
    state = get_active_state()
    if state is None or not _scenario_applies(state):
        return

    faults = set(state.faults)

    if "db.slow" in faults:
        delay = random.uniform(2.0, 5.0)
        _emit_log("db.slow", state, {"delay_seconds": round(delay, 3)})
        time.sleep(delay)

    if "db.deadlock" in faults and random.random() < 0.5:
        _emit_log("db.deadlock", state, {"statement_prefix": statement[:120]})
        # Use a StatementError subclass via SQLAlchemy's DBAPIError so the
        # app's normal error handling surfaces the failure as a 5xx.
        from sqlalchemy.exc import DBAPIError

        class _FakeOracleError(Exception):
            pass

        raise DBAPIError(
            statement=statement,
            params=parameters,
            orig=_FakeOracleError("ORA-00060: deadlock detected while waiting for resource"),
        )

    if "db.pool_hold" in faults and random.random() < 0.1:
        _emit_log("db.pool_hold", state, {"hold_seconds": 30})
        time.sleep(30)


def install(engine: Any) -> None:
    """Idempotently attach the chaos hook to the given engine."""
    try:
        from sqlalchemy import event
    except Exception:
        return

    key = id(engine)
    if key in _INSTALLED:
        return
    event.listen(engine, "before_cursor_execute", _inject)
    _INSTALLED.add(key)
    logger.debug("chaos.db hook installed on engine %s", engine)
