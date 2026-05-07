"""Demo storyboard and attack-lab helper coverage."""

from __future__ import annotations

import pytest

from server.modules.api_gateway_observability import build_api_gateway_observation
from server.modules.attack_simulation import build_attack_plan, run_attack_simulation
from server.modules.shop import _attack_story, _bounded_string, _safe_card_summary


def test_safe_card_summary_never_returns_full_card_number() -> None:
    summary = _safe_card_summary({"brand": "Visa!!!", "number": "4242 4242 4242 4242"})

    assert summary["brand"] == "visa"
    assert summary["last4"] == "4242"
    assert "4242424242424242" not in str(summary)


def test_bounded_string_sanitizes_newlines_and_length() -> None:
    value = _bounded_string("hello\nworld\t" + "x" * 300, fallback="fallback", limit=32)

    assert "\n" not in value
    assert "\t" not in value
    assert len(value) == 32


def test_attack_story_contains_complete_mitre_and_connection_context() -> None:
    story = _attack_story(source_ip="203.0.113.77")

    assert len(story) >= 6
    assert {stage["technique_id"] for stage in story} >= {
        "T1190",
        "T1059",
        "T1046",
        "T1218",
        "T1543",
        "T1056.001",
        "T1557",
    }
    for stage in story:
        assert stage["source_ip"] == "203.0.113.77"
        assert stage["destination_ip"]
        assert stage["destination_port"]
        assert stage["server_address"]
        assert stage["osquery_query"]
        assert stage["osquery_sql"].startswith("SELECT")


def test_api_gateway_observation_masks_sensitive_headers_and_models_edge_policy() -> None:
    observation = build_api_gateway_observation(
        request_id="req-edge-001",
        source_ip="203.0.113.77",
        route="/api/shop/attack/simulate",
        route_id="public-attack-simulate",
        scenario="rate_limit",
        headers={
            "Authorization": "Bearer super-secret-token",
            "X-Forwarded-For": "203.0.113.77",
            "Traceparent": "00-11111111111111111111111111111111-2222222222222222-01",
        },
    )

    fields = observation.log_fields()

    assert observation.action == "throttle"
    assert observation.http_status_code == 429
    assert fields["oci.api_gateway.name"] == "octo-public-api-gateway"
    assert fields["oci.api_gateway.scope"] == "public"
    assert fields["oci.api_gateway.route"] == "/api/shop/attack/simulate"
    assert fields["oci.api_gateway.route_id"] == "public-attack-simulate"
    assert fields["oci.api_gateway.action"] == "throttle"
    assert fields["oci.api_gateway.policy.decision"] == "rate_limit_exceeded"
    assert fields["oci.api_gateway.request_id"] == "req-edge-001"
    assert fields["http.status_code"] == 429
    assert fields["security.attack.detected"] is True
    assert fields["security.attack.type"] == "api_gateway_rate_limit"
    assert fields["security.attack.severity"] == "high"
    assert "super-secret-token" not in str(fields)
    assert fields["http.request.header.authorization"] == "<redacted>"
    assert fields["http.request.header.traceparent"].startswith("00-11111111111111111111111111111111")


def test_attack_plan_models_compromised_vms_payment_interception_and_redirect() -> None:
    plan = build_attack_plan({
        "source_ip": "203.0.113.88",
        "user_agent": "curl/8.4.0 lab",
        "card": {"brand": "Visa!!!", "number": "4242 4242 4242 4242"},
        "payment_redirect_url": "https://pay-update.example.test/checkout/session?token=secret",
    })

    stages = {stage.stage: stage for stage in plan.stages}

    assert {"api_gateway_edge_control", "vm_compromise", "payment_interception", "payment_redirect"}.issubset(stages)
    assert len(plan.compromised_hosts) >= 2
    assert all(host["cloud.instance.id"] for host in plan.compromised_hosts)
    gateway_fields = stages["api_gateway_edge_control"].extra_fields
    assert gateway_fields["oci.api_gateway.name"] == "octo-public-api-gateway"
    assert gateway_fields["oci.api_gateway.action"] == "allow"
    assert gateway_fields["oci.api_gateway.route"] == "/api/shop/attack/simulate"
    assert gateway_fields["oci.api_gateway.policy.decision"] == "suspicious_burst_observed"
    assert gateway_fields["http.status_code"] == 200
    assert stages["payment_interception"].extra_fields["payment.interception.detected"] is True
    assert stages["payment_interception"].extra_fields["payment.card_last4"] == "4242"
    assert "4242424242424242" not in str(stages["payment_interception"].extra_fields)
    assert stages["payment_redirect"].extra_fields["payment.redirect.url"] == "https://pay-update.example.test/checkout/session"
    assert plan.hunt_pivots()["attack_id"] == plan.attack_id
    assert plan.hunt_pivots()["request_id"] == plan.request_id
    assert any("Request ID" in pivot for pivot in plan.hunt_pivots()["log_analytics_pivots"])
    assert any("Attack ID" in pivot for pivot in plan.hunt_pivots()["log_analytics_pivots"])
    assert any("API Gateway Request ID" in pivot for pivot in plan.hunt_pivots()["log_analytics_pivots"])


@pytest.mark.asyncio
async def test_run_attack_simulation_emits_huntable_app_logs(monkeypatch) -> None:
    captured: list[tuple[str, str, dict]] = []
    metric_calls: list[tuple[str, str, str]] = []
    gateway_metric_calls: list[tuple[str, str, int, str]] = []

    class _FakeJavaClient:
        async def simulate(self, name, payload):
            return {"status": "ok", "name": name, "payload": payload}

    async def _noop_sleep(_seconds):
        return None

    monkeypatch.setattr("server.modules.attack_simulation.asyncio.sleep", _noop_sleep)
    monkeypatch.setattr(
        "server.modules.attack_simulation.business_metrics.record_attack_stage",
        lambda stage, severity, technique_id: metric_calls.append((stage, severity, technique_id)),
    )
    monkeypatch.setattr(
        "server.modules.attack_simulation.business_metrics.record_api_gateway_event",
        lambda action, route_family, status_code, scope: gateway_metric_calls.append(
            (action, route_family, status_code, scope)
        ),
    )

    result = await run_attack_simulation(
        {
            "source_ip": "203.0.113.99",
            "external_status_code": 503,
            "sql_error_code": "ora-00942",
        },
        java_client=_FakeJavaClient(),
        log_func=lambda level, message, **fields: captured.append((level, message, fields)),
    )

    assert result["status"] == "completed"
    assert result["attack_id"].startswith("attack-")
    assert result["run_id"].startswith("run-")
    assert result["request_id"]
    assert len(captured) >= 8
    assert {fields["security.attack.id"] for _, _, fields in captured} == {result["attack_id"]}
    assert {fields["request_id"] for _, _, fields in captured} == {result["request_id"]}
    assert any(fields.get("vm.compromised") is True for _, _, fields in captured)
    assert any(fields.get("oci.api_gateway.action") == "allow" for _, _, fields in captured)
    assert any(fields.get("oci.api_gateway.request_id") == result["api_gateway"]["request_id"] for _, _, fields in captured)
    assert any(fields.get("payment.interception.detected") is True for _, _, fields in captured)
    assert any(fields.get("payment.redirect.detected") is True for _, _, fields in captured)
    assert any(fields.get("cloud.instance.id") for _, _, fields in captured)
    assert len(metric_calls) == len(build_attack_plan().stages)
    assert ("allow", "shop_attack", 200, "public") in gateway_metric_calls
    assert ("payment_interception", "critical", "T1056.001") in metric_calls
    assert result["java_app_server"]["payload"]["api_gateway_request_id"] == result["api_gateway"]["request_id"]
    assert result["java_app_server"]["payload"]["workflow_id"] == "attack-lab"
    assert result["external_error"]["payload"]["api_gateway_action"] == "allow"
    assert result["sql_error"]["payload"]["api_gateway_route"] == "/api/shop/attack/simulate"
    assert result["api_gateway"]["action"] == "allow"
    assert result["api_gateway"]["route"] == "/api/shop/attack/simulate"
