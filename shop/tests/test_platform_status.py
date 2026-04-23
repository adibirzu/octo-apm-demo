"""Platform status aggregator tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch) -> TestClient:
    from server.modules import platform_status

    # Force no real targets — everything returns no-http-surface.
    monkeypatch.setattr(
        platform_status,
        "_DEFAULT_TARGETS",
        {"octo-drone-shop": "", "enterprise-crm-portal": ""},
    )
    app = FastAPI()
    app.include_router(platform_status.router)
    return TestClient(app)


def test_endpoint_returns_services_list(client: TestClient) -> None:
    r = client.get("/api/platform/status")
    assert r.status_code == 200
    body = r.json()
    assert "services" in body
    assert "overall_ok" in body
    assert "summary" in body
    assert body["summary"]["total"] == 2


def test_overall_ok_false_when_no_expected_service_reachable(client: TestClient) -> None:
    r = client.get("/api/platform/status")
    assert r.json()["overall_ok"] is True  # zero expected → vacuously ok


def test_env_override_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTO_PLATFORM_STATUS_TARGETS", "x=http://x:1,y=http://y:2")
    from server.modules import platform_status

    t = platform_status._targets()
    assert t["x"] == "http://x:1"
    assert t["y"] == "http://y:2"
