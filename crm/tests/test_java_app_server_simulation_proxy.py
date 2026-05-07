"""CRM admin simulation proxy coverage for Java app-server demos."""

from __future__ import annotations

import types
from pathlib import Path

import pytest
from starlette.requests import Request

from server.modules import simulation


class _FakeResponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True}


class _FakeAsyncClient:
    calls: list[dict] = []
    response = _FakeResponse()

    def __init__(self, timeout: float):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, target: str, content: bytes, headers: dict[str, str]):
        self.calls.append({"method": "POST", "target": target, "headers": headers, "content": content})
        return self.response

    async def get(self, target: str, headers: dict[str, str]):
        self.calls.append({"method": "GET", "target": target, "headers": headers})
        return self.response


@pytest.mark.asyncio
async def test_drone_shop_proxy_maps_java_app_server_actions(monkeypatch) -> None:
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.response = _FakeResponse()
    monkeypatch.setattr(simulation, "external_orders_base_url", lambda: "http://shop.internal:8080")
    monkeypatch.setattr(simulation.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(simulation, "cfg", types.SimpleNamespace(drone_shop_internal_key="internal-key"))

    async def _receive():
        return {"type": "http.request", "body": b'{"duration_ms":100}'}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/simulate/drone-shop/java-slow",
        "headers": [(b"content-type", b"application/json")],
    }
    request = Request(scope, _receive)

    result = await simulation.drone_shop_proxy("java-slow", request)

    assert result["status"] == "proxied"
    assert _FakeAsyncClient.calls[0]["target"] == "http://shop.internal:8080/api/shop/app-server/simulate/slow"
    assert _FakeAsyncClient.calls[0]["headers"]["X-Internal-Service-Key"] == "internal-key"


@pytest.mark.asyncio
async def test_attack_lab_proxy_logs_upstream_correlation_fields(monkeypatch) -> None:
    class _AttackLabResponse(_FakeResponse):
        def json(self):
            return {
                "attack_id": "attack-test",
                "run_id": "run-test",
                "request_id": "request-test",
                "trace_id": "trace-test",
                "source_ip": "203.0.113.77",
                "api_gateway": {
                    "request_id": "gw-request-test",
                    "route": "/api/shop/attack/simulate",
                    "action": "throttle",
                    "policy_decision": "rate_limit_exceeded",
                    "threat_signal": "quota_exhaustion",
                },
            }

    logs: list[tuple[str, str, dict]] = []
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.response = _AttackLabResponse()
    monkeypatch.setattr(simulation, "external_orders_base_url", lambda: "http://shop.internal:8080")
    monkeypatch.setattr(simulation.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(simulation, "cfg", types.SimpleNamespace(drone_shop_internal_key="internal-key"))
    monkeypatch.setattr(simulation, "push_log", lambda level, message, **kwargs: logs.append((level, message, kwargs)))

    async def _receive():
        return {"type": "http.request", "body": b""}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/simulate/drone-shop/attack-lab",
        "headers": [(b"content-type", b"application/json")],
    }
    request = Request(scope, _receive)

    result = await simulation.drone_shop_proxy("attack-lab", request)

    assert result["status"] == "proxied"
    correlation_log = next(log for log in logs if log[1] == "Drone shop proxy correlation: attack-lab")
    assert correlation_log[2]["security.attack.id"] == "attack-test"
    assert correlation_log[2]["run_id"] == "run-test"
    assert correlation_log[2]["request_id"] == "request-test"
    assert correlation_log[2]["oci.api_gateway.request_id"] == "gw-request-test"
    assert correlation_log[2]["oci.api_gateway.threat_signal"] == "quota_exhaustion"


def test_drone_shop_proxy_allows_java_and_payment_demo_actions() -> None:
    expected = {
        "java-health",
        "java-slow",
        "java-gc",
        "java-cpu",
        "java-error",
        "external-status-500",
        "external-status-503",
        "sql-error-942",
        "sql-error-1722",
        "payment-decline",
        "payment-timeout",
        "demo-storyboard",
        "attack-lab",
    }

    assert expected.issubset(simulation._ALLOWED_PROXY_ACTIONS)


def test_drone_shop_proxy_supplies_apm_widget_defaults() -> None:
    assert simulation._DRONE_SHOP_ACTION_PAYLOAD_DEFAULTS["external-status-503"]["status_code"] == 503
    assert simulation._DRONE_SHOP_ACTION_PAYLOAD_DEFAULTS["sql-error-942"]["error_code"] == "ora-00942"
    assert simulation._DRONE_SHOP_ACTION_PAYLOAD_DEFAULTS["attack-lab"]["source_ip"].startswith("203.0.113.")
    assert simulation._DRONE_SHOP_ACTION_PAYLOAD_DEFAULTS["attack-lab"]["payment_redirect_url"].startswith("https://")
    assert simulation._DRONE_SHOP_ACTION_PAYLOAD_DEFAULTS["attack-lab"]["card"]["number"].endswith("4242")


def test_admin_simulation_template_exposes_storyboard_and_attack_controls() -> None:
    template = Path(__file__).resolve().parents[1] / "server/templates/simulation.html"
    content = template.read_text()

    for label in (
        "Demo Storyboard",
        "Attack Lab",
        "Availability Monitoring",
        "External 503",
        "SQL ORA-00942",
        "Generate Attack",
        "Dummy card number",
        "Payment redirect URL",
    ):
        assert label in content


def test_crm_base_loads_advanced_rum_helpers_for_admin_lab() -> None:
    root = Path(__file__).resolve().parents[1] / "server"
    base = (root / "templates/base.html").read_text()

    assert "/static/js/rum-advanced.js" in base
    assert (root / "static/js/rum-advanced.js").exists()
