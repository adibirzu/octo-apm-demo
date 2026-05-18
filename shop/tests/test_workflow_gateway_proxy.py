from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.auth_security as auth_security
import server.modules.workflow_gateway as workflow_gateway


def _client(monkeypatch, fake_cfg) -> TestClient:
    monkeypatch.setattr(workflow_gateway, "cfg", fake_cfg)
    app = FastAPI()
    app.include_router(workflow_gateway.router)
    return TestClient(app)


def _admin_headers(monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(auth_security.cfg, "environment", "test")
    monkeypatch.setattr(auth_security.cfg, "auth_token_secret", "x" * 32)
    token = auth_security.issue_token(user_id=1, username="admin", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_workflow_gateway_proxy_forwards_allowed_request(monkeypatch) -> None:
    calls = []

    class FakeAsyncClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, params=None, content=None, headers=None):
            calls.append(
                {
                    "method": method,
                    "url": url,
                    "params": str(params),
                    "content": content,
                    "headers": headers,
                }
            )
            return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(workflow_gateway.httpx, "AsyncClient", FakeAsyncClient)
    client = _client(
        monkeypatch,
        SimpleNamespace(
            workflow_gateway_configured=True,
            workflow_api_base_url="http://127.0.0.1:8090",
            workflow_service_name="octo-workflow-gateway",
            selectai_configured=True,
            selectai_profile_name="OCTO_SELECTAI",
        ),
    )

    response = client.post(
        "/api/workflow-gateway/api/selectai/generate?action=showsql",
        json={"prompt": "show active drone inventory"},
        headers={
            **_admin_headers(monkeypatch),
            "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == "http://127.0.0.1:8090/api/selectai/generate"
    assert calls[0]["params"] == "action=showsql"
    assert calls[0]["headers"]["traceparent"].startswith("00-")


def test_workflow_gateway_proxy_rejects_unknown_paths(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        SimpleNamespace(
            workflow_gateway_configured=True,
            workflow_api_base_url="http://127.0.0.1:8090",
            workflow_service_name="octo-workflow-gateway",
            selectai_configured=False,
            selectai_profile_name="",
        ),
    )

    response = client.get("/api/workflow-gateway/admin/metadata", headers=_admin_headers(monkeypatch))

    assert response.status_code == 404


def test_workflow_gateway_proxy_requires_admin_token(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        SimpleNamespace(
            workflow_gateway_configured=True,
            workflow_api_base_url="http://127.0.0.1:8090",
            workflow_service_name="octo-workflow-gateway",
            selectai_configured=False,
            selectai_profile_name="",
        ),
    )

    response = client.post(
        "/api/workflow-gateway/api/selectai/generate",
        json={"prompt": "show active drone inventory"},
    )

    assert response.status_code == 401


def test_workflow_gateway_proxy_rejects_admin_token_on_public_shop_host(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        SimpleNamespace(
            workflow_gateway_configured=True,
            workflow_api_base_url="http://127.0.0.1:8090",
            workflow_service_name="octo-workflow-gateway",
            selectai_configured=True,
            selectai_profile_name="OCTO_SELECTAI",
            crm_public_hostname="admin.octodemo.cloud",
            dns_domain="octodemo.cloud",
        ),
    )

    response = client.post(
        "/api/workflow-gateway/api/selectai/generate",
        json={"prompt": "show active drone inventory"},
        headers={**_admin_headers(monkeypatch), "host": "drones.octodemo.cloud"},
    )

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


def test_workflow_gateway_proxy_reports_disabled_gateway(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        SimpleNamespace(
            workflow_gateway_configured=False,
            workflow_api_base_url="",
            workflow_service_name="octo-workflow-gateway",
            selectai_configured=False,
            selectai_profile_name="",
        ),
    )

    response = client.get("/api/workflow-gateway/api/workflows/overview", headers=_admin_headers(monkeypatch))

    assert response.status_code == 503


def test_workflow_gateway_proxy_rejects_oversized_selectai_prompt(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        SimpleNamespace(
            workflow_gateway_configured=True,
            workflow_api_base_url="http://127.0.0.1:8090",
            workflow_service_name="octo-workflow-gateway",
            selectai_configured=True,
            selectai_profile_name="OCTO_SELECTAI",
        ),
    )

    response = client.post(
        "/api/workflow-gateway/api/selectai/generate",
        json={"prompt": "x" * 1001, "action": "showsql"},
        headers=_admin_headers(monkeypatch),
    )

    assert response.status_code == 400
