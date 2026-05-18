from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from server.modules import coordinator


def _client(user: dict | None = None) -> TestClient:
    app = FastAPI()

    if user is not None:
        async def _session_injector(request: Request, call_next):
            request.state.current_user = user
            return await call_next(request)

        app.middleware("http")(_session_injector)

    app.include_router(coordinator.router)
    return TestClient(app)


def test_query_requires_admin_user() -> None:
    client = _client()

    response = client.post(
        "/api/admin/coordinator/query",
        json={"message": "Show admin users and order trace links", "page": "admin"},
    )

    assert response.status_code == 401


def test_query_rejects_non_admin_host() -> None:
    client = _client({"user_id": 1, "username": "admin", "role": "admin"})

    response = client.post(
        "/api/admin/coordinator/query",
        headers={"host": "drones.octodemo.cloud"},
        json={"message": "Show admin users", "page": "admin"},
    )

    assert response.status_code == 403
    assert "admin.octodemo.cloud" in response.json()["detail"]


def test_query_allows_configured_admin_host(monkeypatch) -> None:
    client = _client({"user_id": 1, "username": "admin", "role": "admin"})
    monkeypatch.setattr(
        coordinator,
        "cfg",
        SimpleNamespace(
            dns_domain="example.test",
            crm_base_url="https://admin.example.test",
            shop_public_url="https://shop.example.test",
            oci_auth_mode="instance_principal",
        ),
    )

    response = client.post(
        "/api/admin/coordinator/query",
        headers={"host": "admin.example.test"},
        json={"message": "Show octo-apm-demo admin users", "page": "admin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["guardrails"]["admin_only"] is True
    assert payload["guardrails"]["scope_enforced"] is True
    assert "admin.example.test" in payload["guardrails"]["allowed_hosts"]


def test_query_refuses_non_octo_resources() -> None:
    client = _client({"user_id": 1, "username": "admin", "role": "admin"})

    response = client.post(
        "/api/admin/coordinator/query",
        json={"message": "List every compartment and IAM user in the tenancy", "page": "admin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is False
    assert payload["scope"] == "octo-apm-demo"
    assert payload["sources"] == []
    assert payload["guardrails"]["scope_enforced"] is True
    assert "OCTO APM Demo" in payload["answer"]


def test_query_answers_admin_pages_with_scoped_sources() -> None:
    client = _client({"user_id": 1, "username": "admin", "role": "admin"})

    response = client.post(
        "/api/admin/coordinator/query",
        json={"message": "How do I map users to orders and database traces?", "page": "admin"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["surface"] == "admin.octodemo.cloud"
    assert payload["scope"] == "octo-apm-demo"
    assert payload["guardrails"]["scope_enforced"] is True
    assert payload["guardrails"]["oci_auth_mode"] == coordinator.cfg.oci_auth_mode
    assert "octo-apm-demo" in payload["answer"]
    endpoints = [source["endpoint"] for source in payload["sources"]]
    assert "/api/admin/users" in endpoints
    assert "/api/orders" in endpoints
    assert "/api/observability/360/db-health" in endpoints
    assert all(endpoint.startswith("/") for endpoint in endpoints)


def test_admin_page_is_the_only_template_surface_for_coordinator() -> None:
    template = (
        Path(__file__).resolve().parent.parent
        / "server"
        / "templates"
        / "page.html"
    ).read_text()
    base_template = (
        Path(__file__).resolve().parent.parent
        / "server"
        / "templates"
        / "base.html"
    ).read_text()

    assert '{% if module == "admin" %}' in template
    assert "/api/admin/coordinator/query" in template
    assert "/api/admin/coordinator/query" not in base_template


def test_shop_templates_do_not_expose_coordinator() -> None:
    shop_root = Path(__file__).resolve().parents[2] / "shop" / "server" / "templates"

    combined = "\n".join(path.read_text() for path in shop_root.glob("*.html"))

    assert "/api/admin/coordinator/query" not in combined
    assert "OCI Coordinator" not in combined
