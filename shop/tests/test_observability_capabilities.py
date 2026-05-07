"""Machine-readable observability capability inventory tests."""

from __future__ import annotations

from server.modules.observability_dashboard import _observability_capabilities


def test_shop_observability_capabilities_are_dashboard_safe() -> None:
    payload = _observability_capabilities()

    assert payload["endpoints"]["capabilities"] == "/api/observability/capabilities"
    assert payload["signals"]["logs"]["trace_correlation_fields"] == [
        "trace_id",
        "span_id",
        "oracleApmTraceId",
        "oracleApmSpanId",
    ]
    assert payload["signals"]["metrics"]["prometheus_endpoint"] == "/metrics"
    assert "payments" in payload["signals"]["metrics"]["business_metric_families"]
    assert "payment_orchestration" in payload["signals"]["metrics"]["business_metric_families"]
    assert "java_app_server" in payload["signals"]["metrics"]["business_metric_families"]
    assert "api_gateway" in payload["signals"]["metrics"]["business_metric_families"]
    assert "llmetry" in payload["signals"]["metrics"]["business_metric_families"]
    assert "api_gateway" in payload["signals"]["traces"]["span_enrichment"]
    assert "oci_genai" in payload["signals"]["traces"]["span_enrichment"]
    assert "llmetry" in payload["signals"]["traces"]["span_enrichment"]
    assert payload["signals"]["ai"]["assistant_endpoint"] == "/api/shop/assistant/query"
    assert payload["signals"]["ai"]["llmetry_enabled"] is True
    assert payload["signals"]["ai"]["llmetry_store"] == "llmetry_events"
    assert "llm.prompt.hash" in payload["signals"]["ai"]["correlation_fields"]
    assert payload["signals"]["edge"]["api_gateway"]["enabled"] is True
    assert payload["signals"]["edge"]["api_gateway"]["correlation_fields"] == [
        "oci.api_gateway.request_id",
        "oci.api_gateway.route",
        "oci.api_gateway.action",
        "oracleApmTraceId",
    ]
    assert payload["signals"]["security"]["api_gateway_detection"] is True
    assert payload["demo_generators"]["payment_gateway"]["methods"] == ["credit_card", "apple_pay", "google_pay"]
    assert payload["demo_generators"]["api_gateway_detection"]["endpoint"] == "/api/shop/attack/simulate"
    assert payload["demo_generators"]["api_gateway_detection"]["scenarios"] == [
        "allow",
        "rate_limit",
        "auth_failure",
        "backend_error",
        "route_not_found",
    ]
    assert payload["privacy"]["raw_card_numbers_logged"] is False
    assert payload["privacy"]["raw_card_numbers_persisted"] is False
    assert payload["privacy"]["raw_card_cvv_persisted"] is False
    assert payload["privacy"]["raw_llm_prompts_logged"] is False
    assert payload["privacy"]["raw_llm_responses_logged"] is False
    assert payload["privacy"]["raw_synthetic_user_email_in_rum_dimensions"] is False
    assert payload["privacy"]["raw_synthetic_user_email_in_http_headers"] is False


def test_shop_observability_capabilities_do_not_expose_private_cluster_urls() -> None:
    payload_text = str(_observability_capabilities()).lower()

    assert ".svc.cluster.local" not in payload_text
    assert "internal_service_key" not in payload_text
    assert "private_datakey" not in payload_text
