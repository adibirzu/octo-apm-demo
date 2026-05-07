"""Attack-lab Log Analytics and Cloud Guard asset coverage."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_attack_lab_saved_searches_and_dashboard_are_present() -> None:
    search_names = {
        "api-gateway-edge-detections.sql",
        "attack-lab-detections.sql",
        "attack-lab-trace-timeline.sql",
        "osquery-attack-findings.sql",
    }
    searches = {path.name for path in (ROOT / "deploy/oci/log_analytics/searches").glob("*.sql")}
    assert search_names.issubset(searches)

    dashboard = json.loads(_read("deploy/oci/log_analytics/dashboards/attack-lab-command-center.json"))
    assert dashboard["displayName"] == "Attack Lab Command Center"
    widget_searches = {widget["search"] for widget in dashboard["widgets"]}
    assert {
        "api-gateway-edge-detections",
        "attack-lab-detections",
        "attack-lab-trace-timeline",
        "osquery-attack-findings",
    }.issubset(widget_searches)


def test_private_demo_architecture_diagram_is_published() -> None:
    drawio = ROOT / "site/architecture/diagrams/private-demo-observability-reference.drawio"
    svg = ROOT / "site/architecture/diagrams/private-demo-observability-reference.svg"
    assert drawio.exists()
    assert svg.exists()

    for relative_path in (
        "README.md",
        "site/index.md",
        "site/architecture/index.md",
        "site/architecture/diagrams/README.md",
    ):
        content = _read(relative_path)
        assert "private-demo-observability-reference" in content


def test_app_log_parsers_extract_attack_and_osquery_fields() -> None:
    required_fields = {
        "Attack ID",
        "MITRE Technique ID",
        "MITRE Tactic",
        "Client IP",
        "Source IP",
        "Server Address",
        "Destination IP",
        "Destination Port",
        "OSQuery Query",
        "OSQuery Finding",
        "OSQuery SQL",
        "Security Severity",
        "Run ID",
        "Compromised VM",
        "Host Role",
        "Process Name",
        "Process Command Line",
        "Payment Provider",
        "Payment Status",
        "Payment Risk Score",
        "Payment Card Last4",
        "Payment Interception",
        "Payment Redirect",
        "Payment Redirect URL",
        "HTTP Redirect Location",
        "HTTP Request Method",
        "HTTP Status Code",
        "API Gateway Name",
        "API Gateway Scope",
        "API Gateway Deployment ID",
        "API Gateway Route",
        "API Gateway Route ID",
        "API Gateway Request ID",
        "API Gateway Action",
        "API Gateway Policy Decision",
        "API Gateway Latency ms",
        "API Gateway Rate Limit",
        "API Gateway Rate Remaining",
        "API Gateway Threat Signal",
    }

    for parser_name in ("octo-shop-v2.json", "octo-crm-v2.json"):
        parser = json.loads(_read(f"deploy/oci/log_analytics/parsers/{parser_name}"))
        mapped = {field["logFieldName"] for field in parser["fieldMaps"]}
        assert required_fields.issubset(mapped)
        source_paths = {field["sourcePath"] for field in parser["fieldMaps"]}
        assert {"$.level", "$.severity"} <= source_paths
        assert {"$.http.method", "$.http.status_code"} <= source_paths
        assert {"$.oci.api_gateway.action", "$.oci.api_gateway.request_id"} <= source_paths


def test_cloud_guard_advanced_contains_attack_lab_osquery_queries() -> None:
    script = _read("deploy/oci/ensure_cloud_guard_advanced.sh")

    for key in (
        "lotl-processes",
        "suspicious-shell-history",
        "unexpected-listeners",
        "persistence-systemd",
        "recent-processes",
    ):
        assert key in script

    for table in ("processes", "process_open_sockets", "shell_history", "systemd_units"):
        assert table in script


def test_osquery_result_export_helper_is_dry_run_safe() -> None:
    script = ROOT / "deploy/oci/export_osquery_results_to_logging.sh"
    assert script.exists()
    content = script.read_text(encoding="utf-8")

    assert "DRY_RUN" in content
    assert "oci cloud-guard adhoc-query-result-collection" in content
    assert "oci logging-ingestion put-logs" in content
    assert "security.attack.id" in content
    assert "osquery.finding" in content


def test_log_analytics_connector_helper_is_quota_aware_and_consolidated() -> None:
    script = ROOT / "deploy/oci/ensure_log_analytics_connectors.sh"
    assert script.exists()
    content = script.read_text(encoding="utf-8")

    assert "DRY_RUN" in content
    assert "service-connector-count" in content
    assert "${DEPLOYMENT_PREFIX}-la-observability" in content
    assert "oci sch service-connector create" in content
    assert "loggingAnalytics" in content
    assert "LOG_DISPLAY_NAMES" in content
    assert "${DEPLOYMENT_PREFIX}-cloudguard-raw" in content
    assert "${DEPLOYMENT_PREFIX}-cloudguard-query-results" in content


def test_private_demo_observability_triage_skill_captures_runbook() -> None:
    skill = ROOT / "skills/private-demo-observability-triage/SKILL.md"
    assert skill.exists()
    content = skill.read_text(encoding="utf-8")

    for phrase in (
        "shop.example.test",
        "admin.example.test",
        "Demo Storyboard",
        "Attack Lab",
        "export_osquery_results_to_logging.sh",
        "ensure_availability_monitors.sh",
        "defaultloglevel",
        "Appserver=false",
        "resourcemanager/stacks/create",
    ):
        assert phrase in content
