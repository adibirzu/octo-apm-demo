"""Attack-lab Log Analytics and Cloud Guard asset coverage."""

from __future__ import annotations

import json
import re
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _load_log_analytics_apply_helper():
    path = ROOT / "deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py"
    spec = importlib.util.spec_from_file_location("octo_log_analytics_apply_helper", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        "Service",
        "Service Name",
        "Service Namespace",
        "Service Version",
        "Service Instance ID",
        "Deployment Environment",
        "App Name",
        "App Brand",
        "App Runtime",
        "App Service",
        "Trace ID",
        "Trace Parent",
        "Span ID",
        "Order ID",
        "Source Order ID",
        "Parent Span ID",
        "Span Name",
        "Span Kind",
        "Span Attributes",
        "APM Domain",
        "Metric Name",
        "Metric Value",
        "Metric Unit",
        "DB Target",
        "DB Statement",
        "DB Elapsed ms",
        "DB Connection Name",
        "Java APM Path",
        "Java APM Status Code",
        "Java APM Latency ms",
        "Java APM Error Type",
        "User ID",
        "Business Object",
        "Event Status",
        "Session ID",
        "Provider",
        "Model Version",
        "Result Count",
        "Security Additional Attributes",
        "Version",
        "Server Response Wait Time",
        "Error Type",
        "Subsystem",
        "Application Hash",
        "Request Length",
        "Current Hash",
        "Upstream Response Length",
        "Content Size In",
        "Content Size Out",
        "Total Size",
        "Session",
        "Program Details",
        "Event Types",
        "Attack ID",
        "Attack Stage",
        "Security Event Classification",
        "Attack Entry Point",
        "Attack Payload",
        "MITRE Technique ID",
        "MITRE Tactic",
        "Host IP Address (Client)",
        "User Agent String",
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
        "Payment Gateway Request ID",
        "Payment Network",
        "Payment Wallet Token Hash",
        "Step Id",
        "Process Phase",
        "Elapsed Time (Gateway)",
        "Latency",
        "ORDER_AMOUNT",
        "BillingCurrency",
        "Provider Type",
        "Request Type",
        "Authorization Scheme",
        "Response Code",
        "Gateway ID",
        "Transaction ID",
        "Result",
        "Security Result",
        "Program",
        "Flow Code",
        "Flow",
        "Payment Interception",
        "Payment Redirect",
        "Payment Redirect URL",
        "HTTP Redirect Location",
        "Method",
        "HTTP Status Code",
        "Gateway",
        "Scope",
        "Deployment ID",
        "API Gateway Route",
        "Object ID",
        "Family",
        "API Gateway Request ID",
        "API Gateway Action",
        "API Gateway Policy Decision",
        "API Gateway Latency ms",
        "API Gateway Rate Limit",
        "API Gateway Rate Remaining",
        "API Gateway Threat Signal",
        "Network Bytes Out",
    }

    for parser_name in ("octo-shop-v2.json", "octo-crm-v2.json"):
        parser = json.loads(_read(f"deploy/oci/log_analytics/parsers/{parser_name}"))
        mapped = {field["logFieldName"] for field in parser["fieldMaps"]}
        assert required_fields.issubset(mapped)
        assert "Original Log Content" not in mapped
        assert {
            "Assistant Session ID",
            "LLM Prompt Hash",
            "Payment Processor Response Code",
            "Payment Network Transaction ID",
            "Client IP",
            "HTTP Request Method",
            "API Gateway Name",
        }.isdisjoint(mapped)
        source_paths = {field["sourcePath"] for field in parser["fieldMaps"]}
        message_maps = [
            field for field in parser["fieldMaps"] if field["sourcePath"] == "$.message"
        ]
        assert message_maps == [{"sourcePath": "$.message", "logFieldName": "msg"}]
        required_source_paths = {
            "$.level",
            "$.severity",
            "$.service.name",
            "$.service.namespace",
            "$.trace_id",
            "$.span_id",
            "$.oracleApmTraceId",
            "$.oracleApmSpanId",
            "$.traceparent",
            "$.orders.order_id",
            "$.order_id",
            "$.source_order_id",
            "$.http.method",
            "$.http.status_code",
            "$.java_apm.path",
            "$.java_apm.error_type",
            "$.assistant.session_id",
            "$.assistant.provider",
            "$.assistant.model_id",
            "$.assistant.guardrail.allowed",
            "$.assistant.guardrail.reason",
            "$.llmetry.latency_ms",
            "$.llmetry.error_type",
            "$.llm.prompt.hash",
            "$.llm.response.hash",
            "$.gen_ai.usage.input_tokens",
            "$.gen_ai.usage.output_tokens",
            "$.langfuse.session.id",
            "$.langfuse.trace.name",
            "$.payment.gateway.request_id",
            "$.payment.gateway.name",
            "$.payment.gateway.provider",
            "$.payment.gateway.version",
            "$.payment.gateway.step",
            "$.payment.gateway.step_index",
            "$.payment.gateway.phase",
            "$.payment.gateway.step_status",
            "$.payment.gateway.step_latency_ms",
            "$.payment.method",
            "$.payment.amount_minor_units",
            "$.payment.currency",
            "$.payment.wallet_token_hash",
            "$.payment.card.brand",
            "$.payment.card.last4",
            "$.payment.verification.decision",
            "$.payment.verification.error_code",
            "$.payment.processor.decision",
            "$.payment.processor.error_code",
            "$.payment.processor.response_code",
            "$.payment.network.response_code",
            "$.payment.network.gateway_code",
            "$.payment.network.route",
            "$.payment.network.transaction_id",
            "$.payment.3ds.flow",
            "$.payment.redirect.url",
            "$.oci.api_gateway.action",
            "$.oci.api_gateway.request_id",
            "$.oci.api_gateway.threat_signal",
            "$.security.attack.id",
        }
        assert required_source_paths <= source_paths


def test_fast_troubleshooting_searches_cover_trace_log_relations() -> None:
    expected_searches = {
        "auth-login-correlation.sql",
        "checkout-payment-correlation.sql",
        "connector-live-log-coverage.sql",
        "genai-assistant-llmetry.sql",
        "oke-checkout-payment-correlation.sql",
        "payment-gateway-security-triage.sql",
        "payment-threats.sql",
        "rule-api-gateway-threat-count.sql",
        "rule-compromised-vm-count.sql",
        "rule-java-payment-error-count.sql",
        "rule-payment-interception-count.sql",
        "rule-payment-redirect-count.sql",
        "service-error-triage.sql",
        "service-trace-log-coverage.sql",
        "trace-drilldown.sql",
    }
    search_dir = ROOT / "deploy/oci/log_analytics/searches"
    searches = {path.name for path in search_dir.glob("*.sql")}
    assert expected_searches.issubset(searches)

    required_tokens = {
        "auth-login-correlation.sql": ["Trace ID", "Request ID", "User ID", "DB Statement"],
        "checkout-payment-correlation.sql": [
            "Trace ID",
            "Order ID",
            "Payment Gateway Request ID",
            "Payment Status",
            "Payment Network",
            "Response Code",
            "Transaction ID",
            "Java APM Error Type",
        ],
        "connector-live-log-coverage.sql": [
            "OCI Unified Schema Logs",
            "jsonextract",
            "trace_id",
            "service_name",
            "workflow_id",
        ],
        "payment-gateway-security-triage.sql": [
            "Trace ID",
            "Order ID",
            "Payment Gateway Request ID",
            "Process Phase",
            "Elapsed Time (Gateway)",
            "Java APM Error Type",
        ],
        "oke-checkout-payment-correlation.sql": [
            "SOC Application Logs",
            "Trace ID",
            "Order ID",
            "Payment Gateway Request ID",
            "Downstream Component",
        ],
        "payment-threats.sql": [
            "Attack ID",
            "Payment Interception",
            "Payment Redirect URL",
            "Payment Risk Score",
            "Payment Gateway Request ID",
        ],
        "rule-api-gateway-threat-count.sql": ["ApiGatewayThreatEvents", "API Gateway Threat Signal"],
        "rule-compromised-vm-count.sql": ["CompromisedVmEvents", "Compromised VM"],
        "rule-java-payment-error-count.sql": ["JavaPaymentErrorEvents", "Java APM Error Type", "Response Code"],
        "rule-payment-interception-count.sql": ["PaymentInterceptionEvents", "Payment Interception"],
        "rule-payment-redirect-count.sql": ["PaymentRedirectEvents", "Payment Redirect URL"],
        "genai-assistant-llmetry.sql": [
            "Trace ID",
            "Service Name",
            "LLMetry",
            "GenAI",
            "Langfuse",
            "Session ID",
            "Application Hash",
        ],
        "service-error-triage.sql": [
            "Trace ID",
            "Service Name",
            "Java APM Error Type",
            "Payment Gateway Request ID",
            "API Gateway Threat Signal",
        ],
        "service-trace-log-coverage.sql": ["Trace ID", "Span ID", "Service Name", "Log Source"],
        "trace-drilldown.sql": ["Trace ID", "Payment Gateway Request ID", "Payment Status"],
    }
    for filename, tokens in required_tokens.items():
        content = _read(f"deploy/oci/log_analytics/searches/{filename}")
        for token in tokens:
            assert token in content


def test_log_analytics_custom_field_manifest_covers_new_pivots() -> None:
    manifest = json.loads(_read("deploy/oci/log_analytics/fields/octo-apm-correlation-fields.json"))
    assert manifest["policy"] == "reuse-existing-fields-first"
    fields = {field["semanticName"]: field for field in manifest["fields"]}
    assert {
        "Order ID",
        "Source Order ID",
        "Payment Gateway Request ID",
        "Payment Network Transaction ID",
        "Payment Processor Response Code",
        "Payment Gateway Name",
        "Payment Gateway Provider",
        "Payment Gateway Step",
        "Payment Gateway Phase",
        "Payment Gateway Step Status",
        "Payment Gateway Step Latency",
        "Payment Method",
        "Payment Amount Minor Units",
        "Payment Currency",
        "Payment Verification Error",
        "Payment Downstream Latency",
        "Payment Network Route",
        "Java APM Response Code",
        "Assistant Session ID",
        "LLM Prompt Hash",
        "LLM Response Hash",
        "LLMetry Latency ms",
        "GenAI Input Tokens",
        "GenAI Output Tokens",
        "Langfuse Session ID",
    } <= set(fields)
    assert fields["LLMetry Latency ms"]["parserFieldName"] == "Server Response Wait Time"
    assert fields["GenAI Input Tokens"]["parserFieldName"] == "Content Size In"
    assert fields["Payment Processor Response Code"]["parserFieldName"] == "Response Code"
    assert fields["Payment Network Transaction ID"]["parserFieldName"] == "Transaction ID"
    assert fields["Payment Gateway Step Latency"]["parserFieldName"] == "Elapsed Time (Gateway)"
    assert fields["Payment Gateway Phase"]["parserFieldName"] == "Process Phase"
    assert fields["Payment Amount Minor Units"]["parserFieldName"] == "ORDER_AMOUNT"
    assert fields["Java APM Response Code"]["parserFieldName"] == "Response Code"
    assert all(field["createIfMissing"] is False for field in manifest["fields"])

    script = _read("deploy/oci/log_analytics/apply_fields.sh")
    assert "upsert-field" in script
    assert "REUSE existing field" in script
    assert "createIfMissing" in script
    assert "DRY_RUN" in script
    assert "ocid1." not in script


def test_log_analytics_queries_and_widgets_are_live_safe() -> None:
    search_dir = ROOT / "deploy/oci/log_analytics/searches"
    searches = {path.stem for path in search_dir.glob("*.sql")}
    assert searches

    for dashboard_path in (ROOT / "deploy/oci/log_analytics/dashboards").glob("*.json"):
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        for widget in dashboard["widgets"]:
            assert widget["search"] in searches, f"{dashboard_path.name} references missing search {widget['search']}"

    unsupported_tokens = ("countif(", " is not null", "'Client IP'", "'WAF Action'", "security.attack.")
    for path in search_dir.glob("*.sql"):
        query = path.read_text(encoding="utf-8")
        lowered = query.lower()
        for token in unsupported_tokens:
            assert token.lower() not in lowered, f"{path.name} uses unsupported or unmapped token {token}"
        for group_fields in _stats_group_fields(query):
            assert len(group_fields) <= 4, f"{path.name} exceeds OCI Log Analytics four-field STATS limit"


def test_octo_detection_rule_searches_mirror_detection_rules_repo() -> None:
    expected_rule_files = {
        "apps/apm_octo_rule_api_gateway_threat_count.json": "rule-api-gateway-threat-count.sql",
        "apps/apm_octo_rule_compromised_vm_count.json": "rule-compromised-vm-count.sql",
        "apps/apm_octo_rule_java_payment_error_count.json": "rule-java-payment-error-count.sql",
        "apps/apm_octo_rule_payment_interception_count.json": "rule-payment-interception-count.sql",
        "apps/apm_octo_rule_payment_redirect_count.json": "rule-payment-redirect-count.sql",
    }
    detections_script = ROOT.parent / "oci-log-analytics-detections/scripts/octo_apm_workshop.py"
    if detections_script.exists():
        content = detections_script.read_text(encoding="utf-8")
        for query_file in expected_rule_files:
            assert query_file in content

    for query_file, search_file in expected_rule_files.items():
        search = _read(f"deploy/oci/log_analytics/searches/{search_file}")
        assert "stats count as " in search
        assert query_file.replace("apps/", "oci-log-analytics-detections/apps/") in search
        group_fields = _stats_group_fields(search)
        assert group_fields
        assert len(group_fields[0]) <= 3


def _stats_group_fields(query: str) -> list[list[str]]:
    groups: list[list[str]] = []
    commands = [command.strip() for command in query.split("|")]
    for command in commands:
        if not command.lower().startswith("stats "):
            continue
        by_match = re.search(r"\sby\s(.+)$", command, flags=re.IGNORECASE | re.DOTALL)
        if not by_match:
            continue
        fields = [
            field.strip().strip("'\"")
            for field in by_match.group(1).split(",")
            if field.strip()
        ]
        groups.append(fields)
    return groups


def test_apm_trace_explorer_saved_query_catalog_is_complete() -> None:
    query_dir = ROOT / "deploy/oci/apm/saved-queries"
    query_files = sorted(path for path in query_dir.glob("*.json"))
    assert {path.name for path in query_files} >= {
        "assistant-genai-llmetry.json",
        "checkout-end-to-end.json",
        "db-slow-spans.json",
        "login-auth-flow.json",
        "payment-java-sidecar.json",
        "platform-workflows.json",
        "service-errors.json",
        "trace-drilldown.json",
    }

    combined_services: set[str] = set()
    pivot_searches: set[str] = set()
    for path in query_files:
        descriptor = json.loads(path.read_text(encoding="utf-8"))
        assert descriptor["name"].startswith("octo-apm-")
        assert descriptor["displayName"].startswith("OCTO APM - ")
        assert descriptor["queryText"].startswith("show (")
        assert "TraceId" in descriptor["queryText"]
        assert "ServiceName" in descriptor["queryText"]
        assert descriptor["logAnalyticsPivots"]
        combined_services.update(descriptor["scope"]["services"])
        pivot_searches.update(pivot["savedSearch"] for pivot in descriptor["logAnalyticsPivots"])

    assert {
        "octo-drone-shop",
        "enterprise-crm-portal",
        "octo-java-app-server",
        "octo-workflow-gateway",
        "octo-async-worker",
        "octo-load-control",
        "octo-browser-runner",
        "octo-object-pipeline",
        "octo-remediator",
    } <= combined_services
    assert {
        "auth-login-correlation",
        "checkout-payment-correlation",
        "db-slowness-hotspots",
        "genai-assistant-llmetry",
        "service-error-triage",
        "service-trace-log-coverage",
        "trace-drilldown",
    } <= pivot_searches

    apply_script = _read("deploy/oci/apm/apply_saved_queries.sh")
    assert "management-dashboard saved-search" in apply_script
    assert "APM_SAVED_QUERY_PROVIDER_ID" in apply_script
    assert "DRY_RUN" in apply_script
    assert "ocid1." not in apply_script


def test_attack_lab_saved_searches_use_queryable_message_field() -> None:
    for search_name in ("attack-lab-trace-timeline.sql", "trace-drilldown.sql"):
        content = _read(f"deploy/oci/log_analytics/searches/{search_name}")

        assert "Original Log Content" not in content
        assert "msg" in content


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


def test_octo_apm_workshop_deploy_wrapper_is_scoped_and_variable_driven() -> None:
    script = ROOT / "deploy/oci/log_analytics/deploy_octo_apm_workshop.sh"
    assert script.exists()
    content = script.read_text(encoding="utf-8")

    assert "DETECTIONS_REPO" in content
    assert "setup_log_sources.py\" --octo-apm-only" in content
    assert "octo_apm_workshop.py\" --export-bundle" in content
    assert "octo_apm_workshop.py\" --generate-data" in content
    assert "ingest_test_data.py\" --mode" in content
    assert "octo_apm_workshop_application_logs.jsonl" in content
    assert "deploy_dashboard.py" in content
    assert "--dashboard-name" in content
    assert "verify_deployed_dashboards.py\" --dashboard-name" in content
    assert "detection_rule_creator.py\" --write-default" in content
    assert "ocid1." not in content
    assert "octodemo.cloud" not in content
    assert "161.153." not in content
    assert "cap-live" not in content


def test_log_analytics_saved_search_dashboard_apply_helper_is_scoped() -> None:
    script = ROOT / "deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py"
    assert script.exists()
    content = script.read_text(encoding="utf-8")

    assert "management-dashboard" in content
    assert "dashboard" in content
    assert "import" in content
    assert "override-same-name" in content
    assert "scheduled-task" in content
    assert "create-standard-task" in content
    assert "Octo APM Detection - API Gateway Threat" in content
    assert 'RULE_METRIC_NAMESPACE = "octo_log_analytics_detections"' in content
    assert "DRY RUN" in content
    assert "COMPARTMENT_ID is required" in content
    assert "LA_NAMESPACE is required" in content
    assert "ocid1." not in content
    assert "octodemo.cloud" not in content
    assert "161.153." not in content


def test_log_analytics_saved_searches_do_not_use_unsupported_laql_parameters() -> None:
    helper = _load_log_analytics_apply_helper()

    for query_path in (ROOT / "deploy/oci/log_analytics/searches").glob("*.sql"):
        query = helper.clean_query(query_path)
        assert helper.query_parameter_names(query) == [], query_path.name


def test_dashboard_embedded_saved_searches_do_not_use_unsupported_laql_parameters() -> None:
    helper = _load_log_analytics_apply_helper()

    for dashboard_path in (ROOT / "deploy/oci/log_analytics/dashboards").glob("*.json"):
        payload = helper.build_dashboard_payload("COMPARTMENT_OCID", dashboard_path)
        for saved_search in payload["savedSearches"]:
            query = saved_search["uiConfig"]["queryString"]
            assert helper.query_parameter_names(query) == [], saved_search["displayName"]


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
