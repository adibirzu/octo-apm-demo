"""Local contract tests for OCTO APM observability source assets."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_APM_QUERIES = frozenset(
    {
        "assistant-genai-llmetry",
        "checkout-end-to-end",
        "db-slow-spans",
        "login-auth-flow",
        "payment-java-sidecar",
        "platform-workflows",
        "service-errors",
        "trace-drilldown",
    }
)

REQUIRED_LOG_ANALYTICS_SEARCHES = frozenset(
    {
        "service-trace-log-coverage",
        "checkout-payment-correlation",
        "auth-login-correlation",
        "genai-assistant-llmetry",
        "service-error-triage",
        "db-slowness-hotspots",
        "melts-collection-completeness",
        "oke-checkout-payment-correlation",
        "oke-onm-ingestion-health",
    }
)

REQUIRED_REUSE_FIELDS = frozenset(
    {
        "Trace ID",
        "Span ID",
        "Service Name",
        "Service Namespace",
        "Order ID",
        "Payment Gateway Request ID",
    }
)

MONITORING_CONTRACT_VALUES = frozenset({"octo_apm_demo", "telemetry-ingestion"})


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _load_json(relative_path: str) -> dict:
    return json.loads(_read(relative_path))


def test_required_apm_saved_query_descriptors_exist_and_pivot_to_logs() -> None:
    query_dir = ROOT / "deploy/oci/apm/saved-queries"
    query_stems = {path.stem for path in query_dir.glob("*.json")}
    missing = REQUIRED_APM_QUERIES - query_stems
    assert not missing, f"Missing APM saved-query descriptors: {sorted(missing)}"

    for query_name in REQUIRED_APM_QUERIES:
        descriptor = _load_json(f"deploy/oci/apm/saved-queries/{query_name}.json")
        query_text = descriptor["queryText"]
        services = descriptor.get("scope", {}).get("services", [])
        pivots = descriptor.get("logAnalyticsPivots", [])
        fields = descriptor.get("troubleshootingFields", [])

        assert descriptor["name"].startswith("octo-apm-")
        assert descriptor["displayName"].startswith("OCTO APM - ")
        assert query_text.startswith("show (")
        assert "TraceId" in query_text
        assert "ServiceName" in query_text
        assert services or fields, f"{query_name} has no OCTO services or field pivots"
        assert pivots, f"{query_name} must define at least one Log Analytics pivot"
        assert any(pivot["savedSearch"] in REQUIRED_LOG_ANALYTICS_SEARCHES or pivot["savedSearch"] == "trace-drilldown" for pivot in pivots)


def test_required_log_analytics_searches_exist_and_keep_trace_pivots() -> None:
    search_dir = ROOT / "deploy/oci/log_analytics/searches"
    search_stems = {path.stem for path in search_dir.glob("*.sql")}
    missing = REQUIRED_LOG_ANALYTICS_SEARCHES - search_stems
    assert not missing, f"Missing Log Analytics searches: {sorted(missing)}"

    for search_name in REQUIRED_LOG_ANALYTICS_SEARCHES:
        query = _read(f"deploy/oci/log_analytics/searches/{search_name}.sql")
        assert query.strip()
        assert "Trace ID" in query or "oracleApmTraceId" in query


def test_field_reuse_map_keeps_core_apm_log_analytics_join_fields() -> None:
    manifest = _load_json("deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json")
    assert manifest["policy"] == "reuse-existing-fields-first"

    display_names = {
        field.get("semanticName")
        for field in manifest["fields"]
    } | {
        field.get("parserFieldName")
        for field in manifest["fields"]
    } | {
        field.get("existingDisplayName")
        for field in manifest["fields"]
    }
    missing = REQUIRED_REUSE_FIELDS - display_names
    assert not missing, f"Missing field reuse-map display names: {sorted(missing)}"
    assert all(field.get("createIfMissing") is False for field in manifest["fields"])


def test_dashboards_reference_versioned_saved_searches() -> None:
    search_names = {
        path.stem
        for path in (ROOT / "deploy/oci/log_analytics/searches").glob("*.sql")
    }
    assert search_names

    dashboard_dir = ROOT / "deploy/oci/log_analytics/dashboards"
    dashboards = sorted(dashboard_dir.glob("*.json"))
    assert dashboards

    for dashboard_path in dashboards:
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert dashboard["displayName"]
        widgets = dashboard.get("widgets", [])
        assert widgets, f"{dashboard_path.name} has no widgets"
        for widget in widgets:
            assert widget["search"] in search_names, (
                f"{dashboard_path.name} references missing search {widget['search']}"
            )


def test_monitoring_publishers_keep_octo_namespace_and_ingestion_endpoint() -> None:
    for relative_path in (
        "shop/server/observability/oci_monitoring.py",
        "crm/server/observability/oci_monitoring.py",
    ):
        content = _read(relative_path)
        missing = {value for value in MONITORING_CONTRACT_VALUES if value not in content}
        assert not missing, f"{relative_path} missing Monitoring values: {sorted(missing)}"
