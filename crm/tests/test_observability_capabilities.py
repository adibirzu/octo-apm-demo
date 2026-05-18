"""Machine-readable observability capability inventory tests."""

from __future__ import annotations

from pathlib import Path

from server.modules.observability_dashboard import _observability_capabilities


ROOT = Path(__file__).resolve().parents[2]


def test_crm_observability_capabilities_are_dashboard_safe() -> None:
    payload = _observability_capabilities()

    assert payload["endpoints"]["capabilities"] == "/api/observability/capabilities"
    assert payload["endpoints"]["melts"] == "/api/observability/melts"
    assert payload["endpoints"]["frontend_ingest"] == "/api/observability/frontend"
    assert payload["endpoints"]["admin_coordinator"] == "/api/admin/coordinator/query"
    assert payload["melts"]["coverage"]["metrics"]["namespace"] == "octo_apm_demo"
    assert "app.order_sync.count" in payload["melts"]["coverage"]["metrics"]["families"]
    assert "auth-login-correlation" in payload["melts"]["coverage"]["logs"]["saved_searches"]
    assert payload["signals"]["admin_coordinator"]["surface"] == "admin.octodemo.cloud"
    assert payload["signals"]["admin_coordinator"]["scope"] == "octo-apm-demo"
    assert payload["signals"]["admin_coordinator"]["admin_only"] is True
    assert payload["signals"]["admin_coordinator"]["scope_enforced"] is True
    assert payload["signals"]["admin_coordinator"]["oci_auth_mode"] == "instance_principal"
    assert payload["signals"]["admin_coordinator"]["raw_prompt_logged"] is False
    assert "coordinator.scope.enforced" in payload["signals"]["admin_coordinator"]["log_fields"]
    assert "oci.auth.mode" in payload["signals"]["admin_coordinator"]["log_fields"]
    assert payload["signals"]["logs"]["trace_correlation_fields"] == [
        "trace_id",
        "span_id",
        "oracleApmTraceId",
        "oracleApmSpanId",
    ]
    assert payload["signals"]["rum"]["same_origin_w3c_trace_propagation"] is True
    assert payload["signals"]["rum"]["login_actions"] == ["auth.login.submit", "auth.login.result"]
    assert "order_sync" in payload["signals"]["metrics"]["business_metric_families"]
    assert payload["signals"]["database"]["sql_id_enrichment"] in (True, False)
    assert payload["privacy"]["raw_shared_secret_exposed"] is False


def test_crm_observability_capabilities_do_not_expose_secrets() -> None:
    payload_text = str(_observability_capabilities()).lower()

    assert "internal_service_key" not in payload_text
    assert "drone_shop_internal_key" not in payload_text
    assert "private_datakey" not in payload_text


def test_crm_tracing_middleware_keeps_request_workflow_and_span_names() -> None:
    content = (ROOT / "crm/server/middleware/tracing.py").read_text(encoding="utf-8")

    for token in (
        "workflow_id",
        "workflow.step",
        "request.state.request_id",
        "http.url.path",
        "http.method",
        "http.status_code",
        "http.response_time_ms",
        "correlation.id",
        "auth.check",
        "request.validate",
        "response.finalize",
    ):
        assert token in content
