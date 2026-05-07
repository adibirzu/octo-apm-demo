#!/usr/bin/env bash
# Read-only post-deployment verifier for the two-instance Compute stack.
#
# Checks Terraform outputs, optional drift, DNS, public /ready endpoints,
# Load Balancer lifecycle and backend health, WAF, APM, ATP, Database
# Management, Operations Insights, Log Analytics Service Connectors,
# Management Agents, and Stack Monitoring auto-promote state. It does not
# create, update, or delete OCI resources.
#
# Usage:
#   ./deploy/compute/verify-deployment.sh --profile <OCI_PROFILE> --plan
#   ./deploy/compute/verify-deployment.sh --terraform-dir deploy/compute/terraform
#   ./deploy/compute/verify-deployment.sh --outputs-json outputs.json --profile <OCI_PROFILE>
#   ./deploy/compute/verify-deployment.sh --profile <OCI_PROFILE> --require-https
#   ./deploy/compute/verify-deployment.sh --profile <OCI_PROFILE> --skip-dns

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
OUTPUTS_JSON_FILE=""
OCI_PROFILE_VALUE="${OCI_PROFILE:-${TF_VAR_oci_profile:-}}"
RUN_PLAN=false
REQUIRE_HTTPS=false
SKIP_ENDPOINTS=false
SKIP_DNS=false
SKIP_OCI=false
TIMEOUT_SECONDS=20

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_usage
            exit 0
            ;;
        --terraform-dir)
            TERRAFORM_DIR="${2:?--terraform-dir requires a directory path}"
            shift 2
            ;;
        --outputs-json)
            OUTPUTS_JSON_FILE="${2:?--outputs-json requires a file path}"
            shift 2
            ;;
        --profile)
            OCI_PROFILE_VALUE="${2:?--profile requires an OCI profile name}"
            shift 2
            ;;
        --plan)
            RUN_PLAN=true
            shift
            ;;
        --require-https)
            REQUIRE_HTTPS=true
            shift
            ;;
        --skip-endpoints)
            SKIP_ENDPOINTS=true
            shift
            ;;
        --skip-dns)
            SKIP_DNS=true
            shift
            ;;
        --skip-oci)
            SKIP_OCI=true
            shift
            ;;
        --timeout)
            TIMEOUT_SECONDS="${2:?--timeout requires seconds}"
            shift 2
            ;;
        *)
            printf 'Unknown option: %s\n\n' "$1" >&2
            show_usage >&2
            exit 2
            ;;
    esac
done

if [[ -n "${OUTPUTS_JSON_FILE}" && ! -s "${OUTPUTS_JSON_FILE}" ]]; then
    printf 'Outputs JSON file does not exist or is empty: %s\n' "${OUTPUTS_JSON_FILE}" >&2
    exit 2
fi

if [[ -z "${OUTPUTS_JSON_FILE}" || "${RUN_PLAN}" == "true" ]]; then
    if [[ ! -d "${TERRAFORM_DIR}" ]]; then
        printf 'Terraform directory does not exist: %s\n' "${TERRAFORM_DIR}" >&2
        exit 2
    fi
    if ! command -v terraform >/dev/null 2>&1; then
        printf 'terraform is required unless --outputs-json is used without --plan\n' >&2
        exit 2
    fi
fi

if [[ -n "${OUTPUTS_JSON_FILE}" && "${RUN_PLAN}" == "true" ]]; then
    printf 'WARN --plan checks local Terraform state even when --outputs-json is supplied\n'
fi

if [[ -n "${OUTPUTS_JSON_FILE}" && "${SKIP_OCI}" == "true" && "${SKIP_ENDPOINTS}" == "true" && "${SKIP_DNS}" == "true" ]]; then
    printf 'WARN --outputs-json with --skip-oci --skip-endpoints --skip-dns only validates output shape\n'
fi

if [[ -n "${OUTPUTS_JSON_FILE}" ]]; then
    printf 'Using deployment outputs from %s\n' "${OUTPUTS_JSON_FILE}"
fi

if [[ -n "${OUTPUTS_JSON_FILE}" && ! -r "${OUTPUTS_JSON_FILE}" ]]; then
    printf 'Outputs JSON file is not readable: %s\n' "${OUTPUTS_JSON_FILE}" >&2
    exit 2
fi

if [[ "${SKIP_OCI}" != "true" ]] && ! command -v oci >/dev/null 2>&1; then
    printf 'oci CLI is required unless --skip-oci is used\n' >&2
    exit 2
fi

output_json="$(mktemp)"
plan_log="$(mktemp)"
trap 'rm -f "${output_json}" "${plan_log}"' EXIT

if [[ -n "${OUTPUTS_JSON_FILE}" ]]; then
    cp "${OUTPUTS_JSON_FILE}" "${output_json}"
elif ! terraform -chdir="${TERRAFORM_DIR}" output -json >"${output_json}" 2>"${plan_log}"; then
    printf 'FAIL terraform outputs could not be read from %s\n' "${TERRAFORM_DIR}" >&2
    sed 's/^/     /' "${plan_log}" >&2
    exit 1
fi

plan_failed=0
if [[ "${RUN_PLAN}" == "true" ]]; then
    set +e
    terraform -chdir="${TERRAFORM_DIR}" plan -detailed-exitcode -no-color -input=false >"${plan_log}" 2>&1
    plan_code=$?
    set -e
    case "${plan_code}" in
        0)
            printf 'PASS terraform plan reports no changes\n'
            ;;
        2)
            printf 'FAIL terraform plan reports pending changes\n' >&2
            grep -E '^(Plan:|No changes\.|Error:|  # )' "${plan_log}" | sed -n '1,80p' >&2 || true
            plan_failed=1
            ;;
        *)
            printf 'FAIL terraform plan failed\n' >&2
            grep -E '^(Error:|│ Error:)' "${plan_log}" | sed -n '1,80p' >&2 || true
            plan_failed=1
            ;;
    esac
fi

set +e
python3 - "${output_json}" "${OCI_PROFILE_VALUE}" "${REQUIRE_HTTPS}" "${SKIP_ENDPOINTS}" "${SKIP_DNS}" "${SKIP_OCI}" "${TIMEOUT_SECONDS}" <<'PY'
import json
import ssl
import socket
import subprocess
import sys
import urllib.error
import urllib.request

output_path, oci_profile, require_https, skip_endpoints, skip_dns, skip_oci, timeout = sys.argv[1:]
require_https = require_https == "true"
skip_endpoints = skip_endpoints == "true"
skip_dns = skip_dns == "true"
skip_oci = skip_oci == "true"
timeout = int(timeout)

errors = 0
warnings = 0


def ok(message: str) -> None:
    print(f"PASS {message}")


def warn(message: str) -> None:
    global warnings
    warnings += 1
    print(f"WARN {message}")


def fail(message: str) -> None:
    global errors
    errors += 1
    print(f"FAIL {message}", file=sys.stderr)


def value(outputs: dict, name: str, default=None):
    item = outputs.get(name)
    if not item:
        return default
    if isinstance(item, dict) and "value" in item and (
        "type" in item or "sensitive" in item or "description" in item
    ):
        return item.get("value", default)
    return item


def oci_json(args: list[str]):
    command = ["oci", *args, "--output", "json"]
    if oci_profile:
        command.extend(["--profile", oci_profile])
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "OCI CLI failed")
    return json.loads(result.stdout)["data"]


def check_endpoint(url: str) -> None:
    context = ssl._create_unverified_context() if url.startswith("https://") else None
    request = urllib.request.Request(url, headers={"User-Agent": "octo-compute-verifier/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            status = response.getcode()
            if 200 <= status < 400:
                ok(f"{url} returned HTTP {status}")
            else:
                fail(f"{url} returned HTTP {status}")
    except (urllib.error.URLError, TimeoutError) as exc:
        fail(f"{url} is not reachable: {exc}")


def check_dns(hostname: str, expected_ip: str) -> None:
    if not expected_ip:
        warn(f"cannot verify DNS for {hostname}; Load Balancer output has no public IP")
        return
    try:
        _, _, addresses = socket.gethostbyname_ex(hostname)
    except OSError as exc:
        fail(f"{hostname} DNS lookup failed: {exc}")
        return
    if expected_ip in addresses:
        ok(f"{hostname} resolves to Load Balancer IP {expected_ip}")
    else:
        fail(f"{hostname} resolves to {', '.join(addresses) or '<none>'}, expected {expected_ip}")


outputs = json.load(open(output_path, encoding="utf-8"))

load_balancer = value(outputs, "load_balancer", {})
hostnames = load_balancer.get("hostnames", {})
listeners = load_balancer.get("listeners", {})
lb_id = load_balancer.get("id", "")
lb_ip = load_balancer.get("ip_address", "")
waf_id = load_balancer.get("waf_id", "")

if lb_id:
    ok("load_balancer output includes an OCI Load Balancer OCID")
else:
    fail("load_balancer output is missing the Load Balancer OCID")

if listeners.get("https"):
    ok("HTTPS listener is enabled in Terraform outputs")
elif require_https:
    fail("HTTPS listener is not enabled, but --require-https was supplied")
else:
    warn("HTTPS listener is not enabled; use configure-lb-certificate.sh after certificate files are available")

if listeners.get("http"):
    ok("HTTP listener is enabled in Terraform outputs")
elif not listeners.get("https"):
    fail("neither HTTP nor HTTPS listener is enabled")

if not skip_dns:
    for role in ("shop", "crm"):
        hostname = hostnames.get(role)
        if hostname:
            check_dns(hostname, lb_ip)
        else:
            fail(f"{role} hostname is missing from load_balancer output")

if not skip_endpoints:
    schemes = []
    if listeners.get("http"):
        schemes.append("http")
    if listeners.get("https") or require_https:
        schemes.append("https")
    for role in ("shop", "crm"):
        hostname = hostnames.get(role)
        if not hostname:
            fail(f"{role} hostname is missing from load_balancer output")
            continue
        for scheme in schemes:
            check_endpoint(f"{scheme}://{hostname}/ready")

if skip_oci:
    warn("OCI API checks skipped")
    raise SystemExit(1 if errors else 0)

if lb_id:
    try:
        lb = oci_json(["lb", "load-balancer", "get", "--load-balancer-id", lb_id])
        state = lb.get("lifecycle-state")
        if state == "ACTIVE":
            ok("Load Balancer is ACTIVE")
        else:
            fail(f"Load Balancer lifecycle state is {state}")
    except RuntimeError as exc:
        fail(f"Load Balancer check failed: {exc}")

    for backend_set in ("shop", "crm"):
        try:
            health = oci_json([
                "lb", "backend-set-health", "get",
                "--load-balancer-id", lb_id,
                "--backend-set-name", backend_set,
            ])
            status = health.get("status")
            if status == "OK":
                ok(f"Load Balancer backend set {backend_set} is OK")
            else:
                fail(f"Load Balancer backend set {backend_set} status is {status}")
        except RuntimeError as exc:
            fail(f"Load Balancer backend set {backend_set} health check failed: {exc}")

if waf_id:
    try:
        waf = oci_json(["waf", "web-app-firewall", "get", "--web-app-firewall-id", waf_id])
        state = waf.get("lifecycle-state")
        if state == "ACTIVE":
            ok("WAF attachment is ACTIVE")
        else:
            fail(f"WAF attachment lifecycle state is {state}")
    except RuntimeError as exc:
        fail(f"WAF attachment check failed: {exc}")
else:
    warn("WAF OCID is empty in load_balancer output")

apm = value(outputs, "apm", {})
if apm and apm.get("domain_id"):
    try:
        domain = oci_json([
            "apm-control-plane", "apm-domain", "get",
            "--apm-domain-id", apm["domain_id"],
        ])
        state = domain.get("lifecycle-state")
        if state == "ACTIVE":
            ok("APM domain is ACTIVE")
        else:
            fail(f"APM domain lifecycle state is {state}")
    except RuntimeError as exc:
        fail(f"APM domain check failed: {exc}")
else:
    warn("APM domain output is empty")

atp = value(outputs, "atp", {})
if atp and atp.get("id"):
    try:
        database = oci_json([
            "db", "autonomous-database", "get",
            "--autonomous-database-id", atp["id"],
        ])
        state = database.get("lifecycle-state")
        if state == "AVAILABLE":
            ok("ATP database is AVAILABLE")
        else:
            fail(f"ATP database lifecycle state is {state}")
    except RuntimeError as exc:
        fail(f"ATP database check failed: {exc}")
        database = {}
else:
    fail("ATP output is missing the Autonomous Database OCID")
    database = {}

log_analytics = value(outputs, "log_analytics", {})
if log_analytics.get("enabled"):
    connectors = log_analytics.get("connectors", {})
    if not log_analytics.get("connectors_enabled", True):
        warn("Log Analytics Service Connectors are disabled in Terraform outputs")
    elif connectors:
        for name, connector_id in sorted(connectors.items()):
            if not connector_id:
                warn(f"Log Analytics Service Connector {name} is not configured")
                continue
            try:
                connector = oci_json([
                    "sch", "service-connector", "get",
                    "--service-connector-id", connector_id,
                ])
                state = connector.get("lifecycle-state")
                if state == "ACTIVE":
                    ok(f"Log Analytics Service Connector {name} is ACTIVE")
                else:
                    fail(f"Log Analytics Service Connector {name} lifecycle state is {state}")
            except RuntimeError as exc:
                fail(f"Log Analytics Service Connector {name} check failed: {exc}")
    else:
        fail("Log Analytics is enabled but no connector OCIDs were output")
else:
    warn("Log Analytics is disabled in Terraform outputs")

stack_monitoring = value(outputs, "stack_monitoring", {})
if stack_monitoring.get("database_management_enabled"):
    if database.get("database-management-status") == "ENABLED":
        ok("ATP Database Management status is ENABLED")
    else:
        fail(f"ATP Database Management status is {database.get('database-management-status')}")

    endpoint_id = stack_monitoring.get("db_management_endpoint_id")
    if endpoint_id:
        try:
            endpoint = oci_json([
                "database-management", "private-endpoint", "get",
                "--private-endpoint-id", endpoint_id,
            ])
            state = endpoint.get("lifecycle-state")
            if state == "ACTIVE":
                ok("Database Management private endpoint is ACTIVE")
            else:
                fail(f"Database Management private endpoint lifecycle state is {state}")
        except RuntimeError as exc:
            fail(f"Database Management private endpoint check failed: {exc}")
    else:
        fail("Database Management is enabled but the private endpoint OCID is missing")
else:
    warn("Database Management is disabled in Terraform outputs")

if stack_monitoring.get("operations_insights_enabled"):
    if database.get("operations-insights-status") == "ENABLED":
        ok("ATP Operations Insights status is ENABLED")
    else:
        fail(f"ATP Operations Insights status is {database.get('operations-insights-status')}")

    endpoint_id = stack_monitoring.get("opsi_endpoint_id")
    if endpoint_id:
        try:
            endpoint = oci_json([
                "opsi", "opsi-private-endpoint", "get",
                "--opsi-private-endpoint-id", endpoint_id,
            ])
            state = endpoint.get("lifecycle-state")
            if state == "ACTIVE":
                ok("Operations Insights private endpoint is ACTIVE")
            else:
                fail(f"Operations Insights private endpoint lifecycle state is {state}")
        except RuntimeError as exc:
            fail(f"Operations Insights private endpoint check failed: {exc}")
    else:
        fail("Operations Insights is enabled but the private endpoint OCID is missing")
else:
    warn("Operations Insights is disabled in Terraform outputs")

if stack_monitoring.get("standard_enabled"):
    agent_ids = stack_monitoring.get("agent_ids", {})
    if agent_ids:
        for role, agent_id in sorted(agent_ids.items()):
            try:
                agent = oci_json(["management-agent", "agent", "get", "--agent-id", agent_id])
                state = agent.get("lifecycle-state")
                if state == "ACTIVE":
                    ok(f"Management Agent for {role} is ACTIVE")
                else:
                    fail(f"Management Agent for {role} lifecycle state is {state}")
            except RuntimeError as exc:
                fail(f"Management Agent for {role} check failed: {exc}")
    else:
        fail("Stack Monitoring Standard is enabled but no Management Agent OCIDs were output")

    plugin_ids = stack_monitoring.get("plugin_resource_ids", {})
    if stack_monitoring.get("agent_plugin_enabled"):
        for role in ("shop", "crm"):
            if plugin_ids.get(role):
                ok(f"Stack Monitoring plugin resource is present for {role}")
            else:
                fail(f"Stack Monitoring plugin resource is missing for {role}")

    config_id = stack_monitoring.get("host_auto_promote_config_id")
    if not stack_monitoring.get("configs_enabled", True):
        warn("Stack Monitoring HOST auto-promote config is disabled in Terraform outputs")
    elif config_id:
        try:
            config = oci_json(["stack-monitoring", "config", "get", "--config-id", config_id])
            state = config.get("lifecycle-state")
            if state == "ACTIVE":
                ok("Stack Monitoring HOST auto-promote config is ACTIVE")
            else:
                fail(f"Stack Monitoring HOST auto-promote config lifecycle state is {state}")
        except RuntimeError as exc:
            fail(f"Stack Monitoring HOST auto-promote config check failed: {exc}")
    else:
        fail("Stack Monitoring HOST auto-promote config OCID is missing")

    if stack_monitoring.get("atp_registration_enabled"):
        if stack_monitoring.get("atp_resource_id"):
            ok("ATP Stack Monitoring monitored-resource OCID is present")
        else:
            fail("ATP Stack Monitoring registration is enabled but no resource OCID was output")
    else:
        warn("ATP explicit Stack Monitoring resource registration is disabled")
else:
    warn("Stack Monitoring Standard is disabled in Terraform outputs")

print(f"SUMMARY errors={errors} warnings={warnings}")
raise SystemExit(1 if errors else 0)
PY
python_code=$?
set -e

if [[ "${plan_failed}" -ne 0 || "${python_code}" -ne 0 ]]; then
    exit 1
fi
