#!/usr/bin/env python3
"""Apply Octo Log Analytics saved searches, dashboards, and detection rules.

This helper is intentionally scoped to the local Octo APM assets. It uses the
OCI CLI instead of Terraform so dashboard updates do not disturb the live load
balancer or connector topology.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SEARCH_DIR = ROOT / "deploy/oci/log_analytics/searches"
DASHBOARD_DIR = ROOT / "deploy/oci/log_analytics/dashboards"

PROVIDER_ID = "log-analytics"
PROVIDER_NAME = "Log Analytics"
PROVIDER_VERSION = "3.0.0"
METADATA_VERSION = "2.0"
DEFAULT_TIME_PERIOD = "l24h"
RULE_METRIC_NAMESPACE = "octo_log_analytics_detections"
RULE_RESOURCE_GROUP = "octo-apm-demo"
RULE_INTERVAL = "PT5M"
RULE_LOOKBACK = "PT15M"

QUERY_PARAMETER_RE = re.compile(r"(?<![A-Za-z0-9_]):([A-Za-z_][A-Za-z0-9_]*)")

SEARCH_DISPLAY_NAMES = {
    "api-gateway-edge-detections": "Octo APM: API Gateway Edge Decisions",
    "attack-lab-detections": "Octo APM: Attack Lab Detections",
    "attack-lab-trace-timeline": "Octo APM: Attack Timeline",
    "auth-login-correlation": "Octo APM: Auth Login Correlation",
    "chaos-vs-organic": "Octo APM: Chaos vs Organic Errors",
    "checkout-payment-correlation": "Octo APM: Checkout Payment Correlation",
    "connector-live-log-coverage": "Octo APM: Connector Live Log Coverage",
    "db-slowness-hotspots": "Octo APM: DB Slowness Hotspots",
    "ebpf-container-drift": "Octo APM: eBPF Container Drift",
    "genai-assistant-llmetry": "Octo APM: GenAI Assistant LLMetry",
    "melts-collection-completeness": "Octo APM: MELTS Collection Completeness",
    "osquery-attack-findings": "Octo APM: OSQuery Host Evidence",
    "oke-checkout-payment-correlation": "Octo APM: OKE Checkout Payment Correlation",
    "oke-kubernetes-trace-correlation": "Octo APM: OKE Kubernetes Trace Correlation",
    "oke-onm-ingestion-health": "Octo APM: OKE ONM Ingestion Health",
    "payment-gateway-security-triage": "Octo APM: Payment Gateway Security Triage",
    "payment-threats": "Octo APM: Payment Threats",
    "rule-api-gateway-threat-count": "APM: Octo Demo API Gateway Threat Detection Rule",
    "rule-compromised-vm-count": "APM: Octo Demo Compromised VM Detection Rule",
    "rule-java-payment-error-count": "APM: Octo Demo Java Payment Error Detection Rule",
    "rule-payment-interception-count": "APM: Octo Demo Payment Interception Detection Rule",
    "rule-payment-redirect-count": "APM: Octo Demo Payment Redirect Detection Rule",
    "rule-oke-collector-error-count": "APM: Octo Demo OKE Collector Error Rule",
    "rule-oke-onm-log-samples": "APM: Octo Demo OKE ONM Log Samples Rule",
    "service-health-errors": "Octo APM: Service Health Errors",
    "service-error-triage": "Octo APM: Service Error Triage",
    "service-trace-log-coverage": "Octo APM: Service Trace Log Coverage",
    "trace-drilldown": "Octo APM: Trace Drilldown",
    "waf-vs-app-errors": "Octo APM: WAF and App Errors",
    "workflow-health": "Octo APM: Workflow Health",
}

DETECTION_RULES = {
    "rule-api-gateway-threat-count": {
        "metric": "ApiGatewayThreatEvents",
        "dimensions": ["Attack ID", "Trace ID", "API Gateway Threat Signal"],
        "severity": "high",
    },
    "rule-compromised-vm-count": {
        "metric": "CompromisedVmEvents",
        "dimensions": ["Attack ID", "Compromised VM", "Host Role"],
        "severity": "critical",
    },
    "rule-java-payment-error-count": {
        "metric": "JavaPaymentErrorEvents",
        "dimensions": ["Java APM Error Type", "Trace ID", "Response Code"],
        "severity": "high",
    },
    "rule-payment-interception-count": {
        "metric": "PaymentInterceptionEvents",
        "dimensions": ["Attack ID", "Trace ID", "Payment Provider"],
        "severity": "critical",
    },
    "rule-payment-redirect-count": {
        "metric": "PaymentRedirectEvents",
        "dimensions": ["Attack ID", "Trace ID", "Payment Redirect URL"],
        "severity": "critical",
    },
    "rule-oke-onm-log-samples": {
        "metric": "OkeOnmLogSamples",
        "dimensions": ["Log Source", "Namespace"],
        "severity": "medium",
    },
    "rule-oke-collector-error-count": {
        "metric": "OkeCollectorErrorEvents",
        "dimensions": ["Pod", "Container"],
        "severity": "high",
    },
}

DETECTION_RULE_DISPLAY_NAMES = {
    "rule-api-gateway-threat-count": "Octo APM Detection - API Gateway Threat",
    "rule-compromised-vm-count": "Octo APM Detection - Compromised VM",
    "rule-java-payment-error-count": "Octo APM Detection - Java Payment Error",
    "rule-payment-interception-count": "Octo APM Detection - Payment Interception",
    "rule-payment-redirect-count": "Octo APM Detection - Payment Redirect",
    "rule-oke-onm-log-samples": "Octo APM Detection - OKE ONM Log Samples",
    "rule-oke-collector-error-count": "Octo APM Detection - OKE Collector Errors",
}


def run_oci(profile: str, args: list[str], *, capture_json: bool = True) -> Any:
    command = ["oci", *args, "--profile", profile]
    if capture_json and "--output" not in command:
        command += ["--output", "json"]
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    if capture_json:
        return json.loads(result.stdout or "{}")
    return result.stdout


def write_temp_json(payload: dict[str, Any]) -> str:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
    with handle:
        json.dump(payload, handle, indent=2)
    return handle.name


def query_parameter_names(query: str) -> list[str]:
    """Return unsupported LAQL colon placeholders present in a query string."""
    return sorted(set(QUERY_PARAMETER_RE.findall(query)))


def clean_query(path: Path, *, dashboard_safe: bool = False) -> str:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    ]
    query = "\n".join(lines).strip()
    params = query_parameter_names(query)
    if params:
        try:
            display_path = str(path.relative_to(ROOT))
        except ValueError:
            display_path = str(path)
        raise SystemExit(
            f"{display_path} contains unsupported LAQL parameter placeholders: "
            + ", ".join(f":{name}" for name in params)
        )
    return query


def display_name_for(stem: str) -> str:
    if stem in SEARCH_DISPLAY_NAMES:
        return SEARCH_DISPLAY_NAMES[stem]
    title = " ".join(part.upper() if part in {"db", "waf"} else part.title() for part in stem.split("-"))
    return f"Octo APM: {title}"


def detection_rule_display_name(stem: str) -> str:
    return DETECTION_RULE_DISPLAY_NAMES[stem]


def build_scope_filters(compartment_id: str) -> dict[str, Any]:
    log_group = {
        "type": "LogGroup",
        "values": [{"label": "root", "value": compartment_id}],
        "flags": {"IncludeSubCompartments": True},
    }
    entity = {
        "type": "Entity",
        "values": [],
        "flags": {"IncludeDependents": True, "ScopeCompartmentId": compartment_id},
    }
    log_set = {"type": "LogSet", "values": [], "flags": {}}
    return {
        "LogGroup": log_group,
        "Entity": entity,
        "LogSet": log_set,
        "filters": [log_group, entity, log_set],
        "isGlobal": False,
    }


def visualization_for(query: str) -> tuple[str, dict[str, Any]]:
    lowered = query.lower()
    if "| timestats" in lowered:
        return "line", {"valueField": "Events"}
    if "| stats" in lowered:
        return "summary_table", {"valueField": "Events"}
    return "table", {}


def parameter_config(query: str) -> list[dict[str, Any]]:
    params = query_parameter_names(query)
    return [
        {
            "name": name,
            "displayName": name.replace("_", " ").title(),
            "required": False,
            "valueFormat": {"type": "string"},
        }
        for name in params
    ]


def saved_search_payload(
    *,
    compartment_id: str,
    display_name: str,
    description: str,
    query: str,
    tags: dict[str, str] | None = None,
    search_type: str = "SEARCH_SHOW_IN_DASHBOARD",
) -> dict[str, Any]:
    visualization_type, visualization_options = visualization_for(query)
    return {
        "compartmentId": compartment_id,
        "displayName": display_name,
        "description": description,
        "providerId": PROVIDER_ID,
        "providerName": PROVIDER_NAME,
        "providerVersion": PROVIDER_VERSION,
        "metadataVersion": METADATA_VERSION,
        "type": search_type,
        "isOobSavedSearch": False,
        "nls": {},
        "dataConfig": [],
        "screenImage": " ",
        "widgetTemplate": "visualizations/chartWidgetTemplate.html",
        "widgetVM": "jet-modules/dashboards/widgets/lxSavedSearchWidget",
        "parametersConfig": parameter_config(query),
        "featuresConfig": {"crossService": {"shared": False}},
        "drilldownConfig": [],
        "uiConfig": {
            "enableWidgetInApp": True,
            "queryString": query,
            "scopeFilters": build_scope_filters(compartment_id),
            "showTitle": True,
            "timeSelection": {"timePeriod": DEFAULT_TIME_PERIOD},
            "visualizationOptions": visualization_options,
            "visualizationType": visualization_type,
            "vizType": "lxSavedSearchWidgetType",
        },
        "freeformTags": tags or {},
    }


def existing_saved_search_id(profile: str, compartment_id: str, display_name: str) -> str:
    response = run_oci(
        profile,
        [
            "management-dashboard",
            "saved-search",
            "list",
            "--compartment-id",
            compartment_id,
            "--display-name",
            display_name,
            "--all",
        ],
    )
    return response.get("data", {}).get("items", [{}])[0].get("id", "") if response.get("data", {}).get("items") else ""


def upsert_saved_search(profile: str, payload: dict[str, Any], *, dry_run: bool) -> str:
    display_name = payload["displayName"]
    if dry_run:
        print(f"DRY RUN: upsert saved search: {display_name}", flush=True)
        return f"<dry-run-saved-search:{display_name}>"

    existing_id = existing_saved_search_id(profile, payload["compartmentId"], display_name)
    path = write_temp_json(payload)
    try:
        if existing_id:
            run_oci(
                profile,
                [
                    "management-dashboard",
                    "saved-search",
                    "update",
                    "--management-saved-search-id",
                    existing_id,
                    "--from-json",
                    f"file://{path}",
                    "--force",
                ],
            )
            print(f"Updated saved search: {display_name}", flush=True)
            return existing_id
        response = run_oci(
            profile,
            [
                "management-dashboard",
                "saved-search",
                "create",
                "--from-json",
                f"file://{path}",
            ],
        )
        print(f"Created saved search: {display_name}", flush=True)
        return response.get("data", {}).get("id", "")
    finally:
        Path(path).unlink(missing_ok=True)


def build_dashboard_payload(compartment_id: str, dashboard_path: Path) -> dict[str, Any]:
    descriptor = json.loads(dashboard_path.read_text(encoding="utf-8"))
    tiles: list[dict[str, Any]] = []
    saved_searches: list[dict[str, Any]] = []
    row = 0
    column = 0
    row_height = 0

    for widget in descriptor["widgets"]:
        stem = widget["search"]
        query_path = SEARCH_DIR / f"{stem}.sql"
        if not query_path.exists():
            raise SystemExit(f"{dashboard_path.name} references missing search {stem}")

        search_id = f"{dashboard_path.stem}-{stem}"[:100]
        query = clean_query(query_path, dashboard_safe=True)
        width = 6
        height = 5
        if column and column + width > 12:
            row += row_height
            column = 0
            row_height = 0

        tiles.append(
            {
                "displayName": widget["title"],
                "savedSearchId": search_id,
                "row": row,
                "column": column,
                "height": height,
                "width": width,
                "nls": {},
                "uiConfig": {},
                "dataConfig": [],
                "state": "DEFAULT",
                "drilldownConfig": [],
                "parametersMap": {
                    "log-analytics-entity": "$(dashboard.params.log-analytics-entity-filter)",
                    "log-analytics-log-group-compartment": "$(dashboard.params.log-analytics-loggroup-filter)",
                    "time": "$(dashboard.params.time)",
                },
            }
        )
        column += width
        row_height = max(row_height, height)
        if column >= 12:
            row += row_height
            column = 0
            row_height = 0

        saved_searches.append(
            {
                **saved_search_payload(
                    compartment_id=compartment_id,
                    display_name=f"Octo APM Widget: {widget['title']}",
                    description=f"{descriptor['displayName']} widget backed by {stem}.sql.",
                    query=query,
                    tags={
                        "platform": "octo-apm-demo",
                        "managed_by": "deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py",
                        "dashboard": descriptor["displayName"],
                        "search_name": stem,
                    },
                ),
                "id": search_id,
            }
        )

    return {
        "dashboardId": f"octo-{dashboard_path.stem}",
        "providerId": PROVIDER_ID,
        "providerName": PROVIDER_NAME,
        "providerVersion": PROVIDER_VERSION,
        "displayName": descriptor["displayName"],
        "description": descriptor["description"],
        "compartmentId": compartment_id,
        "isOobDashboard": False,
        "isShowInHome": True,
        "isShowDescription": True,
        "metadataVersion": METADATA_VERSION,
        "type": "normal",
        "isFavorite": False,
        "nls": {},
        "uiConfig": {"isFilteringEnabled": True, "isRefreshEnabled": True},
        "dataConfig": [],
        "screenImage": " ",
        "freeformTags": {
            "platform": "octo-apm-demo",
            "managed_by": "deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py",
            **descriptor.get("freeformTags", {}),
        },
        "parametersConfig": [
            {
                "paramName": "log-analytics-loggroup-filter",
                "displayName": "Log Group Compartment",
                "paramType": "LogAnalyticsLogGroupCompartment",
                "defaultValue": compartment_id,
                "isRequired": False,
            },
            {
                "paramName": "log-analytics-entity-filter",
                "displayName": "Entity",
                "paramType": "LogAnalyticsEntity",
                "defaultValue": "",
                "isRequired": False,
            },
            {
                "paramName": "time",
                "displayName": "Time Range",
                "paramType": "Time",
                "defaultValue": DEFAULT_TIME_PERIOD,
                "isRequired": False,
            },
        ],
        "tiles": tiles,
        "savedSearches": saved_searches,
    }


def import_dashboard(profile: str, compartment_id: str, dashboard_path: Path, *, dry_run: bool) -> None:
    dashboard = build_dashboard_payload(compartment_id, dashboard_path)
    if dry_run:
        print(
            f"DRY RUN: import dashboard: {dashboard['displayName']} ({len(dashboard['tiles'])} widgets)",
            flush=True,
        )
        return

    payload_path = write_temp_json({"dashboards": [dashboard]})
    try:
        run_oci(
            profile,
            [
                "management-dashboard",
                "dashboard",
                "import",
                "--from-json",
                f"file://{payload_path}",
                "--override-same-name",
                "true",
                "--override-dashboard-compartment-ocid",
                compartment_id,
                "--override-saved-search-compartment-ocid",
                compartment_id,
            ],
        )
        print(f"Imported dashboard: {dashboard['displayName']}", flush=True)
    finally:
        Path(payload_path).unlink(missing_ok=True)


def dimension_name(field: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", field).strip("_")
    return name[:255] or "dimension"


def scheduled_task_payload(
    *,
    compartment_id: str,
    display_name: str,
    saved_search_id: str,
    rule: dict[str, Any],
) -> dict[str, Any]:
    first_execution = datetime.now(timezone.utc) + timedelta(minutes=5)
    metric = rule["metric"]
    return {
        "compartmentId": compartment_id,
        "displayName": display_name,
        "description": f"Octo APM Log Analytics detection rule for {display_name}.",
        "taskType": "SAVED_SEARCH",
        "action": {
            "type": "STREAM",
            "savedSearchId": saved_search_id,
            "savedSearchDuration": RULE_LOOKBACK,
            "metricExtraction": {
                "compartmentId": compartment_id,
                "namespace": RULE_METRIC_NAMESPACE,
                "resourceGroup": RULE_RESOURCE_GROUP,
                "metricName": metric,
                "metricCollections": [
                    {
                        "metricName": metric,
                        "metricQueryFieldName": metric,
                        "dimensions": [
                            {"dimensionName": dimension_name(field), "queryFieldName": field}
                            for field in rule["dimensions"]
                        ],
                    }
                ],
            },
        },
        "schedules": [
            {
                "type": "FIXED_FREQUENCY",
                "misfirePolicy": "SKIP",
                "queryOffsetSecs": 0,
                "recurringInterval": RULE_INTERVAL,
                "repeatCount": -1,
                "timeOfFirstExecution": first_execution.isoformat(timespec="seconds"),
            }
        ],
        "freeformTags": {
            "platform": "octo-apm-demo",
            "managed_by": "deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py",
            "severity": rule["severity"],
            "metric_namespace": RULE_METRIC_NAMESPACE,
        },
    }


def existing_scheduled_task_id(profile: str, namespace: str, compartment_id: str, display_name: str) -> str:
    response = run_oci(
        profile,
        [
            "log-analytics",
            "scheduled-task",
            "list",
            "--namespace-name",
            namespace,
            "--compartment-id",
            compartment_id,
            "--task-type",
            "SAVED_SEARCH",
            "--display-name",
            display_name,
            "--all",
        ],
    )
    return response.get("data", {}).get("items", [{}])[0].get("id", "") if response.get("data", {}).get("items") else ""


def upsert_detection_rule(
    profile: str,
    namespace: str,
    payload: dict[str, Any],
    *,
    dry_run: bool,
) -> None:
    display_name = payload["displayName"]
    if dry_run:
        print(f"DRY RUN: upsert scheduled detection rule: {display_name}", flush=True)
        return

    existing_id = existing_scheduled_task_id(profile, namespace, payload["compartmentId"], display_name)
    path = write_temp_json(payload)
    try:
        if existing_id:
            run_oci(
                profile,
                [
                    "log-analytics",
                    "scheduled-task",
                    "update",
                    "--namespace-name",
                    namespace,
                    "--scheduled-task-id",
                    existing_id,
                    "--from-json",
                    f"file://{path}",
                    "--force",
                ],
            )
            print(f"Updated scheduled detection rule: {display_name}", flush=True)
            return
        run_oci(
            profile,
            [
                "log-analytics",
                "scheduled-task",
                "create-standard-task",
                "--namespace-name",
                namespace,
                "--from-json",
                f"file://{path}",
            ],
        )
        print(f"Created scheduled detection rule: {display_name}", flush=True)
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Mutate OCI resources. Default is dry-run.")
    parser.add_argument(
        "--skip-detection-rules",
        action="store_true",
        help="Only apply saved searches and dashboards.",
    )
    parser.add_argument(
        "--only-detection-rules",
        action="store_true",
        help="Apply only the scheduled Log Analytics detection rules.",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    profile = os.environ.get("OCI_CLI_PROFILE") or os.environ.get("OCI_PROFILE") or "DEFAULT"
    compartment_id = os.environ.get("COMPARTMENT_ID")
    namespace = os.environ.get("LA_NAMESPACE")

    if not compartment_id:
        raise SystemExit("COMPARTMENT_ID is required")
    if not namespace and not args.skip_detection_rules:
        raise SystemExit("LA_NAMESPACE is required unless --skip-detection-rules is set")

    saved_search_ids: dict[str, str] = {}
    if not args.only_detection_rules:
        for query_path in sorted(SEARCH_DIR.glob("*.sql")):
            stem = query_path.stem
            query = clean_query(query_path)
            display_name = display_name_for(stem)
            payload = saved_search_payload(
                compartment_id=compartment_id,
                display_name=display_name,
                description=f"Octo APM Log Analytics saved search backed by {query_path.name}.",
                query=query,
                tags={
                    "platform": "octo-apm-demo",
                    "managed_by": "deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py",
                    "search_name": stem,
                },
            )
            saved_search_ids[stem] = upsert_saved_search(profile, payload, dry_run=dry_run)

        for dashboard_path in sorted(DASHBOARD_DIR.glob("*.json")):
            import_dashboard(profile, compartment_id, dashboard_path, dry_run=dry_run)

    if args.skip_detection_rules:
        return

    for stem, rule in DETECTION_RULES.items():
        if dry_run:
            saved_search_id = saved_search_ids.get(stem) or f"<dry-run-saved-search:{display_name_for(stem)}>"
        else:
            saved_search_id = saved_search_ids.get(stem) or existing_saved_search_id(
                profile,
                compartment_id,
                display_name_for(stem),
            )
        if not saved_search_id and not dry_run:
            raise SystemExit(f"Missing saved search id for detection rule {stem}")
        payload = scheduled_task_payload(
            compartment_id=compartment_id,
            display_name=detection_rule_display_name(stem),
            saved_search_id=saved_search_id or "<created-on-apply>",
            rule=rule,
        )
        upsert_detection_rule(profile, namespace or "", payload, dry_run=dry_run)


if __name__ == "__main__":
    main()
