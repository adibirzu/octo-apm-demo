"""End-to-end chaos apply -> read -> clear integration test.

Exercises the full CRM chaos admin router:

    POST /api/admin/chaos/apply   (role-guarded)
      ─► _persist(state)          (stubbed to in-memory dict)
    GET  /api/admin/chaos/state   (role-guarded, via get_active_state)
      ─► _read_from_db            (stubbed to in-memory dict)
    POST /api/admin/chaos/clear   (role-guarded)
      ─► _clear_all               (stubbed to in-memory dict)

The unit tests in test_chaos_admin.py cover individual handlers with
mocked DB; this test asserts that the three endpoints stay consistent
with each other through a real request cycle — i.e. that what `apply`
writes is what `state` reads, and `clear` wipes it.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


@pytest.fixture
def chaos_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAOS_ENABLED", "true")
    monkeypatch.setenv("CHAOS_STATE_BACKEND", "db")

    from server.chaos import admin as chaos_admin
    from server.chaos import registry as chaos_registry

    # In-memory chaos_state store. Single-row — matches the prod semantics
    # where _persist deletes everything first.
    store: dict[str, Any] = {"state": None}

    def _fake_persist(state):
        store["state"] = state

    def _fake_clear():
        store["state"] = None

    def _fake_read_from_db():
        return store.get("state")

    def _fake_ensure_table():
        return None

    monkeypatch.setattr(chaos_admin, "_persist", _fake_persist)
    monkeypatch.setattr(chaos_admin, "_clear_all", _fake_clear)
    monkeypatch.setattr(chaos_admin, "_ensure_table", _fake_ensure_table)
    monkeypatch.setattr(chaos_registry, "_read_from_db", _fake_read_from_db)

    # Attach a session with chaos-operator role on every request so the
    # role-guard dependency passes. Middleware runs before the dep.
    async def _session_injector(request: Request, call_next):
        request.state.session = {"user_id": "u1", "roles": ["chaos-operator"]}
        request.state.request_id = "req-test-1"
        return await call_next(request)

    app = FastAPI()
    app.middleware("http")(_session_injector)
    app.include_router(chaos_admin.router)

    return TestClient(app), store


def test_apply_read_clear_round_trip(chaos_client) -> None:
    client, store = chaos_client

    # 1. apply
    r = client.post(
        "/api/admin/chaos/apply",
        json={"scenario_id": "payment-timeout", "target": "shop", "ttl_seconds": 120},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["state"]["scenario_id"] == "payment-timeout"
    assert body["state"]["target"] == "shop"
    assert store["state"] is not None
    assert store["state"].scenario_id == "payment-timeout"

    # 2. read
    r = client.get("/api/admin/chaos/state")
    assert r.status_code == 200
    state_body = r.json()
    assert state_body["active"] is True
    assert state_body["state"]["scenario_id"] == "payment-timeout"
    assert state_body["state"]["target"] == "shop"
    # The applied_by is a 16-char hex hash (see _hash_user)
    assert len(state_body["state"]["applied_by"]) == 16

    # 3. clear
    r = client.post("/api/admin/chaos/clear")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert store["state"] is None

    # 4. read after clear
    r = client.get("/api/admin/chaos/state")
    assert r.status_code == 200
    assert r.json() == {"active": False, "state": None}


def test_apply_unknown_scenario_404(chaos_client) -> None:
    client, _ = chaos_client
    r = client.post(
        "/api/admin/chaos/apply",
        json={"scenario_id": "does-not-exist", "target": "both", "ttl_seconds": 120},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "scenario_not_found"


def test_ttl_clamped_to_max(chaos_client, monkeypatch) -> None:
    # Exceed MAX_TTL_SECONDS via direct import
    from server.chaos.registry import MAX_TTL_SECONDS

    client, store = chaos_client
    r = client.post(
        "/api/admin/chaos/apply",
        json={"scenario_id": "payment-timeout", "target": "shop", "ttl_seconds": MAX_TTL_SECONDS + 999},
    )
    # Pydantic validator caps ttl at MAX_TTL_SECONDS — request should 422.
    assert r.status_code == 422


def test_expired_state_is_not_returned(chaos_client) -> None:
    """After apply, mutate expires_at to the past — reader must return inactive."""
    client, store = chaos_client
    client.post(
        "/api/admin/chaos/apply",
        json={"scenario_id": "payment-timeout", "target": "shop", "ttl_seconds": 60},
    )
    assert store["state"] is not None

    # Replace with an expired copy.
    from dataclasses import replace

    store["state"] = replace(store["state"], expires_at=time.time() - 10)

    r = client.get("/api/admin/chaos/state")
    assert r.status_code == 200
    assert r.json() == {"active": False, "state": None}


def test_role_guard_blocks_without_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the chaos-operator role the dep must 403."""
    monkeypatch.setenv("CHAOS_ENABLED", "true")
    from server.chaos import admin as chaos_admin

    app = FastAPI()
    app.include_router(chaos_admin.router)
    client = TestClient(app)

    r = client.get("/api/admin/chaos/state")
    assert r.status_code == 403
    assert r.json()["detail"] == "role_required"
