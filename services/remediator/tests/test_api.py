"""API surface tests — drives the FastAPI app with TestClient."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from octo_remediator.api import _RunStore, create_app


@pytest.fixture
def client(monkeypatch) -> TestClient:
    # Force dry-run on cache-flush by pre-patching the execute method
    # so tests don't touch a real Redis.
    from octo_remediator.playbooks.cache_flush import CacheFlushPlaybook

    async def _fake_execute(self, ctx):
        return [{
            "kind": "cache_flush_mocked",
            "target": ctx.run.params.get("namespace"),
            "result": "mocked",
        }]

    monkeypatch.setattr(CacheFlushPlaybook, "execute", _fake_execute)

    return TestClient(create_app(store=_RunStore()))


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_list_playbooks(client: TestClient) -> None:
    r = client.get("/playbooks")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert {"cache-flush", "scale-hpa", "restart-deployment"}.issubset(names)


def test_alarm_cache_triggers_auto_flush(client: TestClient) -> None:
    r = client.post(
        "/events/alarm",
        json={
            "id": "alarm-xyz",
            "title": "cache hit ratio stale",
            "body": "cache hit ratio stale for 5m",
            "metric_name": "cache.hit_ratio",
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert "cache-flush" in body["matched_playbooks"]
    assert len(body["proposed_runs"]) >= 1

    # Run state is SUCCEEDED (auto-applied because tier=LOW)
    run_id = body["proposed_runs"][0]
    run = client.get(f"/runs/{run_id}").json()
    assert run["state"] == "succeeded"
    assert run["playbook_name"] == "cache-flush"


def test_alarm_crashloop_proposes_but_does_not_execute(client: TestClient) -> None:
    r = client.post(
        "/events/alarm",
        json={
            "id": "alarm-crash",
            "title": "deployment unhealthy",
            "body": "pod crashloop backoff for octo-drone-shop",
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert "restart-deployment" in body["matched_playbooks"]

    run_id = [rid for rid, pn in zip(body["proposed_runs"], body["matched_playbooks"])
              if pn == "restart-deployment"][0]
    run = client.get(f"/runs/{run_id}").json()
    # Tier HIGH — stays PROPOSED until approved
    assert run["state"] == "proposed"


def test_approve_transitions_to_succeeded(client: TestClient, monkeypatch) -> None:
    from octo_remediator.playbooks.restart_deployment import RestartDeploymentPlaybook

    async def _fake_execute(self, ctx):
        return [{"kind": "rollout_restart_mocked", "target": "x", "result": "ok"}]

    monkeypatch.setattr(RestartDeploymentPlaybook, "execute", _fake_execute)

    r = client.post(
        "/events/alarm",
        json={"id": "alarm-approve", "body": "deployment unhealthy"},
    )
    run_ids = r.json()["proposed_runs"]
    matched = r.json()["matched_playbooks"]
    run_id = [rid for rid, pn in zip(run_ids, matched) if pn == "restart-deployment"][0]

    approve = client.post(f"/runs/{run_id}/approve", json={"approver": "alice"})
    assert approve.status_code == 200
    assert approve.json()["state"] == "succeeded"
    assert approve.json()["approver"] == "alice"


def test_reject_locks_run(client: TestClient) -> None:
    r = client.post(
        "/events/alarm",
        json={"id": "alarm-rej", "body": "deployment unhealthy"},
    )
    run_ids = r.json()["proposed_runs"]
    matched = r.json()["matched_playbooks"]
    run_id = [rid for rid, pn in zip(run_ids, matched) if pn == "restart-deployment"][0]

    rej = client.post(f"/runs/{run_id}/reject", json={"approver": "bob"})
    assert rej.status_code == 200
    assert rej.json()["state"] == "rejected"

    # Can't approve once rejected
    again = client.post(f"/runs/{run_id}/approve", json={"approver": "c"})
    assert again.status_code == 409


def test_approve_unknown_run_404(client: TestClient) -> None:
    r = client.post("/runs/ghost/approve", json={})
    assert r.status_code == 404
