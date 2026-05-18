"""Source-level inventory for OCTO APM demo signal-contract drift."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_APP_FIELDS = frozenset(
    {
        "trace_id",
        "span_id",
        "oracleApmTraceId",
        "oracleApmSpanId",
        "request_id",
        "current_request_id",
        "workflow_id",
        "workflow_step",
        "service.name",
        "service.namespace",
        "service.instance.id",
        "deployment.environment",
    }
)

REQUIRED_RESOURCE_FIELDS = frozenset(
    {
        "service.name",
        "service.namespace",
        "service.instance.id",
        "SERVICE_INSTANCE_ID",
        "deployment.environment",
        "cloud.provider",
        "oci.demo.stack",
    }
)

REQUIRED_PAYMENT_FIELDS = frozenset(
    {
        "payment_gateway_request_id",
        "payment.method",
        "payment.network",
        "payment.provider",
        "payment.status",
        "payment.risk_score",
    }
)

REQUIRED_MONITORING_VALUES = frozenset(
    {
        "octo_apm_demo",
        "OCI_REGION",
        "OCI_REGION_ID",
        "telemetry-ingestion",
    }
)

EXPECTED_APM_SAVED_QUERIES = frozenset(
    {
        "assistant-genai-llmetry.json",
        "checkout-end-to-end.json",
        "db-slow-spans.json",
        "login-auth-flow.json",
        "payment-java-sidecar.json",
        "platform-workflows.json",
        "service-errors.json",
        "trace-drilldown.json",
    }
)

SUPPORT_TELEMETRY_FILES = (
    "services/async-worker/src/octo_async_worker/telemetry.py",
    "services/edge-fuzz/src/octo_edge_fuzz/telemetry.py",
    "services/load-control/src/octo_load_control/telemetry.py",
    "services/object-pipeline/src/octo_object_pipeline/telemetry.py",
    "services/remediator/src/octo_remediator/telemetry.py",
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _missing_tokens(content: str, required: frozenset[str]) -> set[str]:
    return {token for token in required if token not in content}


def test_shop_and_crm_logging_sdks_keep_core_app_fields() -> None:
    for relative_path in (
        "shop/server/observability/logging_sdk.py",
        "crm/server/observability/logging_sdk.py",
    ):
        content = _read(relative_path)
        missing = _missing_tokens(content, REQUIRED_APP_FIELDS)
        assert not missing, f"{relative_path} missing signal fields: {sorted(missing)}"


def test_java_structured_events_keep_trace_and_payment_fields() -> None:
    content = _read("services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java")
    required = frozenset(
        {
            "trace_id",
            "span_id",
            "oracleApmTraceId",
            "oracleApmSpanId",
            "service_name",
            "service_namespace",
            "service.name",
            "request_id",
            "workflow_id",
            "payment.token.safe",
            "payment.gateway.request_id",
            "payment_gateway_request_id",
        }
    )
    missing = _missing_tokens(content, required)
    assert not missing, f"Java structured event contract missing: {sorted(missing)}"
    assert "System.out.println(JSON.writeValueAsString(event))" in content


def test_payment_signal_dictionary_is_present_in_app_logging() -> None:
    for relative_path in (
        "shop/server/observability/logging_sdk.py",
        "crm/server/observability/logging_sdk.py",
    ):
        content = _read(relative_path)
        missing = _missing_tokens(content, REQUIRED_PAYMENT_FIELDS)
        assert not missing, f"{relative_path} missing payment fields: {sorted(missing)}"


def test_support_service_telemetry_keeps_resource_identity() -> None:
    for relative_path in SUPPORT_TELEMETRY_FILES:
        content = _read(relative_path)
        missing = _missing_tokens(content, REQUIRED_RESOURCE_FIELDS)
        assert not missing, f"{relative_path} missing resource fields: {sorted(missing)}"


def test_apm_saved_query_catalog_covers_operator_drilldowns() -> None:
    query_dir = ROOT / "deploy/oci/apm/saved-queries"
    query_names = {path.name for path in query_dir.glob("*.json")}
    missing = EXPECTED_APM_SAVED_QUERIES - query_names
    assert not missing, f"APM saved-query descriptors missing: {sorted(missing)}"

    for query_name in EXPECTED_APM_SAVED_QUERIES:
        descriptor = json.loads((query_dir / query_name).read_text(encoding="utf-8"))
        assert descriptor["queryText"].startswith("show (")
        assert "TraceId" in descriptor["queryText"]
        assert "ServiceName" in descriptor["queryText"]
        assert descriptor["logAnalyticsPivots"], f"{query_name} has no Log Analytics pivot"


def test_log_analytics_field_reuse_map_keeps_core_join_fields() -> None:
    manifest = json.loads(
        _read("deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json")
    )
    field_names = {
        field.get("semanticName")
        for field in manifest["fields"]
    } | {
        field.get("parserFieldName")
        for field in manifest["fields"]
    } | {
        field.get("existingDisplayName")
        for field in manifest["fields"]
    }
    required = {
        "Trace ID",
        "Span ID",
        "Service Name",
        "Service Namespace",
        "Order ID",
        "Payment Gateway Request ID",
    }
    missing = required - field_names
    assert not missing, f"Log Analytics field reuse map missing: {sorted(missing)}"
    assert all(field.get("createIfMissing") is False for field in manifest["fields"])


def test_monitoring_publishers_keep_namespace_region_and_ingestion_endpoint() -> None:
    for relative_path in (
        "shop/server/observability/oci_monitoring.py",
        "crm/server/observability/oci_monitoring.py",
    ):
        content = _read(relative_path)
        missing = _missing_tokens(content, REQUIRED_MONITORING_VALUES)
        assert not missing, f"{relative_path} missing Monitoring values: {sorted(missing)}"
