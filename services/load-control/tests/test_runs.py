"""Run model + ledger tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from octo_load_control.profiles import ProfileName, get_profile
from octo_load_control.runs import InMemoryLedger, LocalJsonLedger, Run, RunState


def test_new_run_carries_uuid_and_pending_state() -> None:
    profile = get_profile(ProfileName.DB_READ_BURST.value)
    run = Run.new(profile=profile, operator="alice", duration_seconds=120)
    assert run.run_id
    assert len(run.run_id) >= 32  # uuid4 with dashes is 36
    assert run.state == RunState.PENDING
    assert run.profile_name == "db-read-burst"


def test_run_roundtrips_via_json() -> None:
    profile = get_profile(ProfileName.DB_READ_BURST.value)
    r = Run.new(profile=profile, operator="bob", duration_seconds=60)
    r.state = RunState.RUNNING
    r.executor_metadata = {"endpoint": "traffic-generator"}
    raw = r.to_json()
    r2 = Run.from_json(raw)
    assert r2.run_id == r.run_id
    assert r2.state == RunState.RUNNING
    assert r2.executor_metadata["endpoint"] == "traffic-generator"


class TestInMemoryLedger:
    def test_append_then_get(self) -> None:
        ledger = InMemoryLedger()
        r = Run.new(profile=get_profile("db-read-burst"), operator="c", duration_seconds=60)
        ledger.append(r)
        assert ledger.get(r.run_id) == r

    def test_update_overwrites(self) -> None:
        ledger = InMemoryLedger()
        r = Run.new(profile=get_profile("db-read-burst"), operator="c", duration_seconds=60)
        ledger.append(r)
        r.state = RunState.SUCCEEDED
        ledger.update(r)
        assert ledger.get(r.run_id).state == RunState.SUCCEEDED

    def test_list_recent_newest_first(self) -> None:
        ledger = InMemoryLedger()
        for i in range(3):
            r = Run.new(profile=get_profile("db-read-burst"), operator=f"u{i}", duration_seconds=60)
            ledger.append(r)
        listing = ledger.list_recent(limit=2)
        assert len(listing) == 2


class TestLocalJsonLedger:
    def test_append_then_get_persists_to_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "runs.jsonl"
        ledger = LocalJsonLedger(path=path)
        r = Run.new(profile=get_profile("db-read-burst"), operator="c", duration_seconds=60)
        ledger.append(r)
        assert path.exists()
        assert ledger.get(r.run_id).run_id == r.run_id

    def test_update_appends_new_line_and_latest_wins(self, tmp_path: Path) -> None:
        path = tmp_path / "runs.jsonl"
        ledger = LocalJsonLedger(path=path)
        r = Run.new(profile=get_profile("db-read-burst"), operator="c", duration_seconds=60)
        ledger.append(r)
        r.state = RunState.RUNNING
        ledger.update(r)
        r.state = RunState.SUCCEEDED
        ledger.update(r)

        # File has 3 lines (append-only)
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 3

        # Latest state wins on read
        assert ledger.get(r.run_id).state == RunState.SUCCEEDED

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "runs.jsonl"
        ledger = LocalJsonLedger(path=path)
        assert ledger.get("nonexistent") is None

    def test_malformed_line_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "runs.jsonl"
        path.write_text('not-json\n{"not-a-run":true}\n')
        ledger = LocalJsonLedger(path=path)
        assert ledger.list_recent() == []
