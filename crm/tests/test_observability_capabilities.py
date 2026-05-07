"""Machine-readable observability capability inventory tests."""

from __future__ import annotations

from server.modules.observability_dashboard import _observability_capabilities


def test_crm_observability_capabilities_are_dashboard_safe() -> None:
    payload = _observability_capabilities()

    assert payload["endpoints"]["capabilities"] == "/api/observability/capabilities"
    assert payload["endpoints"]["frontend_ingest"] == "/api/observability/frontend"
    assert payload["signals"]["logs"]["trace_correlation_fields"] == [
        "trace_id",
        "span_id",
        "oracleApmTraceId",
        "oracleApmSpanId",
    ]
    assert "order_sync" in payload["signals"]["metrics"]["business_metric_families"]
    assert payload["signals"]["database"]["sql_id_enrichment"] in (True, False)
    assert payload["privacy"]["raw_shared_secret_exposed"] is False


def test_crm_observability_capabilities_do_not_expose_secrets() -> None:
    payload_text = str(_observability_capabilities()).lower()

    assert "internal_service_key" not in payload_text
    assert "drone_shop_internal_key" not in payload_text
    assert "private_datakey" not in payload_text
