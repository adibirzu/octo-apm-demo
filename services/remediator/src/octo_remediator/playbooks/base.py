"""Playbook base class + types."""

from __future__ import annotations

import abc
import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class RemediationTier(str, enum.Enum):
    LOW = "low"       # auto-apply — no side effects on customer traffic
    MEDIUM = "medium"  # proposes; auto-applies if `auto_medium=True` env
    HIGH = "high"     # always requires operator approval


class RemediationState(str, enum.Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class RemediationRun:
    run_id: str
    playbook_name: str
    tier: RemediationTier
    alarm_id: str
    alarm_summary: str
    params: dict[str, Any]
    state: RemediationState
    proposed_at: str
    started_at: str | None = None
    completed_at: str | None = None
    approver: str | None = None
    error: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def propose(
        cls,
        *,
        playbook: "Playbook",
        alarm_id: str,
        alarm_summary: str,
        params: dict[str, Any],
    ) -> "RemediationRun":
        return cls(
            run_id=str(uuid.uuid4()),
            playbook_name=playbook.name,
            tier=playbook.tier,
            alarm_id=alarm_id,
            alarm_summary=alarm_summary,
            params=params,
            state=RemediationState.PROPOSED,
            proposed_at=_now_iso(),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ExecutionContext:
    """Passed to ``Playbook.execute()``. Captures the state of the
    platform at execution time so playbooks stay pure-ish."""

    run: RemediationRun
    alarm: dict[str, Any]
    dry_run: bool = False


class Playbook(abc.ABC):
    """Every playbook subclasses this and sets ``name``, ``description``,
    ``tier``, then implements :py:meth:`matches` + :py:meth:`execute`."""

    name: str
    description: str
    tier: RemediationTier

    @abc.abstractmethod
    def matches(self, alarm: dict[str, Any]) -> bool:
        """Return True if this playbook applies to ``alarm``."""

    @abc.abstractmethod
    async def execute(self, ctx: ExecutionContext) -> list[dict[str, Any]]:
        """Perform the remediation. Return a list of action-audit dicts.

        Every entry should include ``kind``, ``target``, ``result``,
        ``completed_at``. The remediator logs + emits OCI Events for
        each action.
        """

    def extract_params(self, alarm: dict[str, Any]) -> dict[str, Any]:
        """Override in subclasses to derive params from the alarm
        payload (target namespace, deployment name, desired replicas,
        …). Default: empty dict."""
        return {}
