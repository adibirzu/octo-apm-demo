"""Run model + ledger abstraction.

A Run is an instance of a Profile executing with a unique ``run_id``.
The ledger is the append-only record of every run — used for audit +
postmortem. Two implementations:

- ``LocalJsonLedger``: writes to ``~/.octo-load-control/runs.jsonl``.
  Default in dev + VM deploy.
- ``OCIObjectStorageLedger``: writes each run as its own object under
  ``<bucket>/runs/<YYYY>/<MM>/<run_id>.json``. Used in production so
  ledger retention is decoupled from the service lifecycle.

Both implementations honour the same append-only contract: once written,
a run record is immutable. Status transitions are recorded as new
*events* under the run, never as rewrites.
"""

from __future__ import annotations

import enum
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .profiles import Profile


class RunState(str, enum.Enum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Run:
    run_id: str
    profile_name: str
    operator: str
    duration_seconds: int
    state: RunState
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    executor_metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def new(cls, *, profile: Profile, operator: str, duration_seconds: int) -> "Run":
        return cls(
            run_id=str(uuid.uuid4()),
            profile_name=profile.name.value,
            operator=operator,
            duration_seconds=duration_seconds,
            state=RunState.PENDING,
            created_at=_now_iso(),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "Run":
        d = json.loads(raw)
        d["state"] = RunState(d["state"])
        return cls(**d)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Ledger(Protocol):
    def append(self, run: Run) -> None: ...
    def update(self, run: Run) -> None: ...
    def get(self, run_id: str) -> Run | None: ...
    def list_recent(self, limit: int = 50) -> list[Run]: ...


class LocalJsonLedger:
    """Append-only JSON-lines file. ``update()`` writes a new line; the
    newest line wins on ``get()``. Crash-safe via append-only semantics."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(
            path
            or os.getenv("LOAD_CONTROL_LEDGER_PATH", "~/.octo-load-control/runs.jsonl")
        ).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, run: Run) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(run.to_json() + "\n")

    def update(self, run: Run) -> None:
        # Same append-only pattern — latest entry wins on read.
        self.append(run)

    def get(self, run_id: str) -> Run | None:
        if not self.path.exists():
            return None
        latest: Run | None = None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = Run.from_json(line)
                except Exception:
                    continue
                if r.run_id == run_id:
                    latest = r
        return latest

    def list_recent(self, limit: int = 50) -> list[Run]:
        if not self.path.exists():
            return []
        by_id: dict[str, Run] = {}
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = Run.from_json(line)
                except Exception:
                    continue
                by_id[r.run_id] = r  # latest state
        runs = sorted(by_id.values(), key=lambda r: r.created_at, reverse=True)
        return runs[:limit]


class InMemoryLedger:
    """Used by tests — never touches disk."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def append(self, run: Run) -> None:
        self._runs[run.run_id] = run

    def update(self, run: Run) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list_recent(self, limit: int = 50) -> list[Run]:
        runs = sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
        return runs[:limit]
