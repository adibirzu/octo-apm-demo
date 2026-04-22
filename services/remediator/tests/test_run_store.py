"""KG-036 — Redis run store tests (fakeredis)."""

from __future__ import annotations

import pytest
import pytest_asyncio

from octo_remediator.playbooks.base import RemediationRun, RemediationState, RemediationTier
from octo_remediator.playbooks.cache_flush import CacheFlushPlaybook
from octo_remediator.run_store import RedisRunStore


@pytest_asyncio.fixture
async def store(fake_redis):
    s = RedisRunStore.__new__(RedisRunStore)
    s._redis = fake_redis
    yield s


@pytest.fixture
def sample_run() -> RemediationRun:
    return RemediationRun.propose(
        playbook=CacheFlushPlaybook(),
        alarm_id="alarm-1",
        alarm_summary="cache stale",
        params={"namespace": "shop:catalog"},
    )


async def test_add_then_get(store, sample_run) -> None:
    await store.add(sample_run)
    found = await store.get(sample_run.run_id)
    assert found is not None
    assert found.run_id == sample_run.run_id
    assert found.tier == RemediationTier.LOW


async def test_add_update_returns_latest(store, sample_run) -> None:
    await store.add(sample_run)
    sample_run.state = RemediationState.SUCCEEDED
    await store.add(sample_run)
    found = await store.get(sample_run.run_id)
    assert found.state == RemediationState.SUCCEEDED


async def test_list_recent_dedupes_by_run_id(store, sample_run) -> None:
    await store.add(sample_run)
    sample_run.state = RemediationState.RUNNING
    await store.add(sample_run)

    pb = CacheFlushPlaybook()
    other = RemediationRun.propose(
        playbook=pb, alarm_id="a-2", alarm_summary="another", params={}
    )
    await store.add(other)

    recent = await store.list_recent(limit=10)
    ids = [r.run_id for r in recent]
    # Both unique run_ids present, no duplicates
    assert sample_run.run_id in ids
    assert other.run_id in ids
    assert len(ids) == 2


async def test_get_nonexistent_returns_none(store) -> None:
    assert await store.get("does-not-exist") is None
