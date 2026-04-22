"""Redis-stream-backed run store (KG-036).

Replaces the in-memory ``_RunStore`` in ``api.py`` for multi-replica
deployments. Writes every run + every state transition onto
``octo_remediator_runs`` as a Redis Stream entry so the audit trail
survives restarts and two remediator pods agree on run state.

Permissive-fail: if OCTO_REMEDIATOR_REDIS_URL is unset, the factory
returns the original in-memory store so tests and dev-loops without
Redis keep working.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from typing import Any

from .playbooks.base import RemediationRun, RemediationState

logger = logging.getLogger(__name__)

_STREAM = "octo.remediator.runs"


class RedisRunStore:
    """Append-only stream. `add()` XADDs; `get()` scans back from
    newest and returns the freshest entry matching run_id; list_recent
    returns the last N unique run_ids."""

    def __init__(self, *, redis_url: str):
        import redis.asyncio as redis_async  # type: ignore

        self._redis = redis_async.from_url(redis_url, decode_responses=False)

    async def aclose(self) -> None:
        await self._redis.aclose()

    async def add(self, run: RemediationRun) -> None:
        await self._redis.xadd(
            _STREAM,
            {"run_id": run.run_id, "payload": json.dumps(_dump(run), separators=(",", ":"))},
            maxlen=100_000,
            approximate=True,
        )

    async def get(self, run_id: str) -> RemediationRun | None:
        # Scan from newest toward oldest, return the first match.
        cursor = "+"
        batch = 200
        while True:
            entries = await self._redis.xrevrange(_STREAM, max=cursor, min="-", count=batch)
            if not entries:
                return None
            for entry_id, fields in entries:
                entry_run_id = _decode(fields.get(b"run_id"))
                if entry_run_id == run_id:
                    return _restore(json.loads(_decode(fields[b"payload"])))
                cursor = f"({entry_id.decode() if isinstance(entry_id, bytes) else entry_id}"
            if len(entries) < batch:
                return None

    async def list_recent(self, limit: int = 50) -> list[RemediationRun]:
        entries = await self._redis.xrevrange(_STREAM, count=limit * 3)
        seen: dict[str, RemediationRun] = {}
        for _entry_id, fields in entries:
            run_id = _decode(fields.get(b"run_id"))
            if run_id in seen:
                continue
            try:
                seen[run_id] = _restore(json.loads(_decode(fields[b"payload"])))
            except Exception:
                continue
            if len(seen) >= limit:
                break
        return list(seen.values())


def _decode(v: Any) -> str:
    if v is None:
        return ""
    return v.decode("utf-8") if isinstance(v, bytes) else str(v)


def _dump(run: RemediationRun) -> dict[str, Any]:
    d = asdict(run)
    d["state"] = run.state.value
    d["tier"] = run.tier.value
    return d


def _restore(d: dict[str, Any]) -> RemediationRun:
    from .playbooks.base import RemediationTier

    d = dict(d)
    d["state"] = RemediationState(d["state"])
    d["tier"] = RemediationTier(d["tier"])
    return RemediationRun(**d)


def build_store() -> Any:
    """Factory used by api.create_app()."""
    url = os.getenv("OCTO_REMEDIATOR_REDIS_URL", "").strip()
    if not url:
        logger.info("OCTO_REMEDIATOR_REDIS_URL not set — using in-memory run store")
        # Defer import to avoid cycle
        from .api import _RunStore

        return _RunStore()
    try:
        return RedisRunStore(redis_url=url)
    except ImportError:
        logger.warning("redis package missing — falling back to in-memory store")
        from .api import _RunStore

        return _RunStore()
