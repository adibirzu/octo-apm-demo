"""FastAPI route tests — uses InMemoryLedger + a fake executor backend
so no network calls."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from octo_load_control.api import create_app
from octo_load_control.executor import ExecutorBackend
from octo_load_control.runs import InMemoryLedger


class _FakeClient:
    """Mimics httpx.AsyncClient.post → returns (status, body) stub."""

    def __init__(self, status_code: int = 202):
        self.status_code = status_code
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, *, json: Any = None, headers: dict[str, str] | None = None) -> Any:
        self.calls.append({"url": url, "json": json, "headers": headers})

        class _Resp:
            pass

        r = _Resp()
        r.status_code = self.status_code  # type: ignore[attr-defined]
        return r


@pytest.fixture
def client() -> TestClient:
    ledger = InMemoryLedger()
    executor = ExecutorBackend(
        traffic_generator_client=_FakeClient(status_code=202),
        chaos_admin_client=_FakeClient(status_code=200),
    )
    app = create_app(ledger=ledger, executor=executor)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["ledger_type"] == "InMemoryLedger"


def test_list_profiles_has_twelve(client: TestClient) -> None:
    resp = client.get("/profiles")
    assert resp.status_code == 200
    assert len(resp.json()) == 12


def test_get_profile_by_name(client: TestClient) -> None:
    resp = client.get("/profiles/db-read-burst")
    assert resp.status_code == 200
    assert resp.json()["name"] == "db-read-burst"


def test_get_unknown_profile_404(client: TestClient) -> None:
    resp = client.get("/profiles/not-real")
    assert resp.status_code == 404


def test_launch_and_list_run(client: TestClient) -> None:
    resp = client.post(
        "/runs",
        json={"profile": "db-read-burst", "duration_seconds": 30, "operator": "alice"},
    )
    assert resp.status_code == 202
    body = resp.json()
    run_id = body["run_id"]
    assert run_id

    listing = client.get("/runs").json()
    assert any(r["run_id"] == run_id for r in listing)


def test_launch_unknown_profile_422(client: TestClient) -> None:
    resp = client.post(
        "/runs",
        json={"profile": "not-real", "duration_seconds": 30, "operator": "alice"},
    )
    assert resp.status_code == 422  # pydantic validator catches it


def test_launch_duration_bounds_enforced(client: TestClient) -> None:
    too_short = client.post(
        "/runs",
        json={"profile": "db-read-burst", "duration_seconds": 5, "operator": "a"},
    )
    assert too_short.status_code == 422
    too_long = client.post(
        "/runs",
        json={"profile": "db-read-burst", "duration_seconds": 10_000, "operator": "a"},
    )
    assert too_long.status_code == 422


def test_cancel_run(client: TestClient) -> None:
    created = client.post(
        "/runs",
        json={"profile": "db-read-burst", "duration_seconds": 300, "operator": "alice"},
    ).json()
    run_id = created["run_id"]

    resp = client.delete(f"/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    # The delete can legitimately race with the background watcher task
    # and see a terminal state (succeeded/cancelled) — either outcome
    # still produces a 200 + ok=True; the invariant we guard here is
    # that the handler does not 500 or silently ignore the request.
    assert body["ok"] is True
    assert body.get("cancelled") == run_id or body.get("already_terminal") in {
        "succeeded", "failed", "cancelled"
    }


def test_cancel_unknown_run_404(client: TestClient) -> None:
    assert client.delete("/runs/ghost").status_code == 404
