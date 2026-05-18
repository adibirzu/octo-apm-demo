#!/usr/bin/env bash
# Create OCI APM Availability Monitoring checks for the private demo lab.
#
# Dry-run by default. Set --apply after DNS or DNS override validation.
#
# Usage:
#   APM_DOMAIN_ID=ocid1.apmdomain... ./deploy/oci/ensure_availability_monitors.sh
#   OCI_CLI_PROFILE=<profile> \
#   APM_DOMAIN_ID=ocid1.apmdomain... \
#   OVERRIDE_DNS_IP=203.0.113.10 \
#   ./deploy/oci/ensure_availability_monitors.sh --apply
#   SYNTHETIC_BROWSER_MONITOR_ENABLED=true \
#   OCTO_LIVE_SHOP_URL=https://shop.example.test \
#   OCTO_LIVE_ADMIN_URL=https://admin.example.test \
#   OCTO_ADMIN_PASSWORD_SECRET_OCID=<ADMIN_PASSWORD_SECRET_OCID> \
#   OCTO_ADMIN_PASSWORD_SECRET_REGION=<OCI_REGION> \
#   ./deploy/oci/ensure_availability_monitors.sh --apply

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

APPLY=false
SCRIPTED_BROWSER_ARG=false
for arg in "$@"; do
    case "${arg}" in
        -h|--help)
            show_usage
            exit 0
            ;;
        --apply)
            APPLY=true
            ;;
        --dry-run)
            APPLY=false
            ;;
        --scripted-browser)
            SCRIPTED_BROWSER_ARG=true
            ;;
        *)
            echo "Unknown argument: ${arg}" >&2
            show_usage >&2
            exit 2
            ;;
    esac
done

: "${APM_DOMAIN_ID:?APM_DOMAIN_ID is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SHOP_READY_URL="${SHOP_READY_URL:-https://shop.example.test/ready}"
ADMIN_READY_URL="${ADMIN_READY_URL:-https://admin.example.test/ready}"
MONITOR_PREFIX="${MONITOR_PREFIX:-octo-demo}"
REPEAT_INTERVAL_SECONDS="${REPEAT_INTERVAL_SECONDS:-300}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-60}"
OVERRIDE_DNS_IP="${OVERRIDE_DNS_IP:-}"
VANTAGE_POINTS_CSV="${VANTAGE_POINTS_CSV:-OraclePublic-us-phoenix-1,OraclePublic-us-ashburn-1,OraclePublic-eu-frankfurt-1,OraclePublic-uk-london-1,OraclePublic-ap-tokyo-1,OraclePublic-ap-sydney-1}"
SYNTHETIC_BROWSER_MONITOR_ENABLED="${SYNTHETIC_BROWSER_MONITOR_ENABLED:-false}"
if [[ "${SCRIPTED_BROWSER_ARG}" == "true" ]]; then
    SYNTHETIC_BROWSER_MONITOR_ENABLED=true
fi
SYNTHETIC_SCRIPT_PATH="${SYNTHETIC_SCRIPT_PATH:-${REPO_ROOT}/shop/tools/apm/octo-apm-demo-synthetic.spec.ts}"
SYNTHETIC_SCRIPT_NAME="${SYNTHETIC_SCRIPT_NAME:-${MONITOR_PREFIX}-octo-apm-demo-synthetic}"
SYNTHETIC_MONITOR_NAME="${SYNTHETIC_MONITOR_NAME:-${MONITOR_PREFIX}-checkout-browser-synthetic}"
SYNTHETIC_REPEAT_INTERVAL_SECONDS="${SYNTHETIC_REPEAT_INTERVAL_SECONDS:-600}"
SYNTHETIC_TIMEOUT_SECONDS="${SYNTHETIC_TIMEOUT_SECONDS:-300}"
SYNTHETIC_FAILURE_RETRIED="${SYNTHETIC_FAILURE_RETRIED:-false}"
SYNTHETIC_DEFAULT_SNAPSHOT_ENABLED="${SYNTHETIC_DEFAULT_SNAPSHOT_ENABLED:-true}"
SYNTHETIC_SHOP_URL="${OCTO_LIVE_SHOP_URL:-${SHOP_SYNTHETIC_URL:-https://shop.example.test}}"
SYNTHETIC_ADMIN_URL="${OCTO_LIVE_ADMIN_URL:-${ADMIN_SYNTHETIC_URL:-https://admin.example.test}}"
SYNTHETIC_DEMO_MODE="${OCTO_APM_DEMO_MODE:-monitor}"
SYNTHETIC_ADMIN_USERNAME="${OCTO_ADMIN_USERNAME:-admin}"
TMP_FILES=()
cleanup() {
    if [[ "${#TMP_FILES[@]}" -eq 0 ]]; then
        return 0
    fi
    for file in "${TMP_FILES[@]}"; do
        [[ -n "${file}" && -f "${file}" ]] && rm -f "${file}"
    done
}
trap cleanup EXIT

oci_cli() {
    if [[ -n "${OCI_CLI_PROFILE:-}" ]]; then
        oci --profile "${OCI_CLI_PROFILE}" "$@"
    else
        oci "$@"
    fi
}

json_array_from_csv() {
    python3 - "$1" <<'PY'
import json
import sys
print(json.dumps([item.strip() for item in sys.argv[1].split(",") if item.strip()]))
PY
}

vantage_points_json="$(json_array_from_csv "${VANTAGE_POINTS_CSV}")"
dns_config_json="{}"
if [[ -n "${OVERRIDE_DNS_IP}" ]]; then
    dns_config_json="$(python3 - "${OVERRIDE_DNS_IP}" <<'PY'
import json
import sys
print(json.dumps({"isOverrideDns": True, "overrideDnsIp": sys.argv[1]}))
PY
)"
fi

json_bool() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
        true|1|yes|y|on) printf 'true' ;;
        *) printf 'false' ;;
    esac
}

new_temp_json() {
    local file
    file="$(mktemp)"
    chmod 0600 "${file}"
    TMP_FILES+=("${file}")
    printf '%s' "${file}"
}

create_monitor() {
    local display_name="$1"
    local target="$2"
    local existing

    existing="$(oci_cli apm-synthetics monitor-collection list-monitors \
        --apm-domain-id "${APM_DOMAIN_ID}" \
        --display-name "${display_name}" \
        --all \
        --query 'data.items[0].id' \
        --raw-output 2>/dev/null || true)"
    if [[ -n "${existing}" && "${existing}" != "null" && "${existing}" != "None" ]]; then
        echo "[availability] Monitor exists: ${display_name} (${existing})"
        return 0
    fi

    if [[ "${APPLY}" != "true" ]]; then
        cat <<EOF
[DRY RUN] Would create REST monitor:
  name:          ${display_name}
  target:        ${target}
  interval:      ${REPEAT_INTERVAL_SECONDS}s
  timeout:       ${TIMEOUT_SECONDS}s
  vantagePoints: ${vantage_points_json}
  dnsOverride:   ${OVERRIDE_DNS_IP:-none}
EOF
        return 0
    fi

    oci_cli apm-synthetics monitor create-rest-monitor \
        --apm-domain-id "${APM_DOMAIN_ID}" \
        --display-name "${display_name}" \
        --monitor-type REST \
        --target "${target}" \
        --vantage-points "${vantage_points_json}" \
        --repeat-interval-in-seconds "${REPEAT_INTERVAL_SECONDS}" \
        --timeout-in-seconds "${TIMEOUT_SECONDS}" \
        --status ENABLED \
        --is-run-now true \
        --is-failure-retried true \
        --is-redirection-enabled true \
        --is-certificate-validation-enabled true \
        --dns-configuration "${dns_config_json}" \
        --request-method GET \
        --verify-response-codes '["2xx"]' \
        --verify-response-content 'ready' \
        --availability-configuration '{"maxAllowedFailuresPerInterval":1,"minAllowedRunsPerInterval":3}' \
        --freeform-tags '{"project":"octo-apm-demo","deployment":"private-demo","lab":"availability-monitoring"}' >/dev/null
    echo "[availability] Monitor created: ${display_name}"
}

script_parameters_json() {
    python3 <<'PY'
import json

print(json.dumps([
    {"paramName": "OCTO_LIVE_SHOP_URL", "paramValue": "https://shop.example.test", "isSecret": False},
    {"paramName": "OCTO_LIVE_ADMIN_URL", "paramValue": "https://admin.example.test", "isSecret": False},
    {"paramName": "OCTO_APM_DEMO_MODE", "paramValue": "monitor", "isSecret": False},
    {"paramName": "OCTO_ADMIN_USERNAME", "paramValue": "admin", "isSecret": False},
    {"paramName": "OCTO_ADMIN_PASSWORD", "paramValue": "<configured-in-monitor>", "isSecret": True},
    {"paramName": "OCTO_INTERNAL_SERVICE_KEY", "paramValue": "<optional-configured-in-monitor>", "isSecret": True},
]))
PY
}

write_monitor_parameters_json() {
    local params_file="$1"
    if [[ -z "${OCTO_ADMIN_PASSWORD:-}" && -n "${OCTO_ADMIN_PASSWORD_SECRET_OCID:-}" ]]; then
        : "${OCTO_ADMIN_PASSWORD_SECRET_REGION:?OCTO_ADMIN_PASSWORD_SECRET_REGION is required when OCTO_ADMIN_PASSWORD_SECRET_OCID is set}"
    fi

    SYNTHETIC_SHOP_URL="${SYNTHETIC_SHOP_URL}" \
    SYNTHETIC_ADMIN_URL="${SYNTHETIC_ADMIN_URL}" \
    SYNTHETIC_DEMO_MODE="${SYNTHETIC_DEMO_MODE}" \
    SYNTHETIC_ADMIN_USERNAME="${SYNTHETIC_ADMIN_USERNAME}" \
    python3 - >"${params_file}" <<'PY'
import json
import os

shop_url = os.environ["SYNTHETIC_SHOP_URL"]
admin_url = os.environ["SYNTHETIC_ADMIN_URL"]
mode = os.environ["SYNTHETIC_DEMO_MODE"]
admin_username = os.environ["SYNTHETIC_ADMIN_USERNAME"]
admin_password = os.environ.get("OCTO_ADMIN_PASSWORD", "")
internal_key = os.environ.get("OCTO_INTERNAL_SERVICE_KEY") or os.environ.get("INTERNAL_SERVICE_KEY", "")
secret_ocid = os.environ.get("OCTO_ADMIN_PASSWORD_SECRET_OCID", "")
if not admin_password and secret_ocid:
    secret_region = os.environ["OCTO_ADMIN_PASSWORD_SECRET_REGION"]
    secret_auth = os.environ.get("OCTO_ADMIN_PASSWORD_SECRET_AUTH", "RESOURCE_PRINCIPAL")
    admin_password = f"<ORAS>{secret_ocid}</ORAS><ORASREG>{secret_region}</ORASREG><ORASAUTH>{secret_auth}</ORASAUTH>"

params = [
    {"paramName": "OCTO_LIVE_SHOP_URL", "paramValue": shop_url},
    {"paramName": "OCTO_LIVE_ADMIN_URL", "paramValue": admin_url},
    {"paramName": "OCTO_APM_DEMO_MODE", "paramValue": mode},
    {"paramName": "OCTO_ADMIN_USERNAME", "paramValue": admin_username},
]
if admin_password:
    params.append({"paramName": "OCTO_ADMIN_PASSWORD", "paramValue": admin_password})
if internal_key:
    params.append({"paramName": "OCTO_INTERNAL_SERVICE_KEY", "paramValue": internal_key})
print(json.dumps(params))
PY
}

write_script_payload() {
    local payload_file="$1"
    python3 - \
        "${APM_DOMAIN_ID}" \
        "${SYNTHETIC_SCRIPT_NAME}" \
        "${SYNTHETIC_SCRIPT_PATH}" \
        "$(script_parameters_json)" >"${payload_file}" <<'PY'
import json
import pathlib
import sys

apm_domain_id, display_name, script_path, parameters_json = sys.argv[1:5]
path = pathlib.Path(script_path)
payload = {
    "apmDomainId": apm_domain_id,
    "displayName": display_name,
    "contentType": "PLAYWRIGHT_TS",
    "content": path.read_text(encoding="utf-8"),
    "contentFileName": path.name,
    "parameters": json.loads(parameters_json),
    "freeformTags": {
        "project": "octo-apm-demo",
        "deployment": "private-demo",
        "lab": "availability-monitoring",
        "script": "checkout-payment-observability",
    },
}
print(json.dumps(payload))
PY
}

write_scripted_monitor_payload() {
    local payload_file="$1"
    local script_id="$2"
    local monitor_params_file
    monitor_params_file="$(new_temp_json)"
    write_monitor_parameters_json "${monitor_params_file}"
    python3 - \
        "${APM_DOMAIN_ID}" \
        "${SYNTHETIC_MONITOR_NAME}" \
        "${script_id}" \
        "${SYNTHETIC_SHOP_URL}" \
        "${vantage_points_json}" \
        "${SYNTHETIC_REPEAT_INTERVAL_SECONDS}" \
        "${SYNTHETIC_TIMEOUT_SECONDS}" \
        "$(json_bool "${SYNTHETIC_FAILURE_RETRIED}")" \
        "$(json_bool "${SYNTHETIC_DEFAULT_SNAPSHOT_ENABLED}")" \
        "${dns_config_json}" \
        "${monitor_params_file}" >"${payload_file}" <<'PY'
import json
import pathlib
import sys

(
    apm_domain_id,
    display_name,
    script_id,
    target,
    vantage_points_json,
    repeat_interval,
    timeout_seconds,
    failure_retried,
    default_snapshot_enabled,
    dns_config_json,
    monitor_parameters_file,
) = sys.argv[1:12]

payload = {
    "apmDomainId": apm_domain_id,
    "displayName": display_name,
    "monitorType": "SCRIPTED_BROWSER",
    "scriptId": script_id,
    "target": target,
    "vantagePoints": json.loads(vantage_points_json),
    "repeatIntervalInSeconds": int(repeat_interval),
    "timeoutInSeconds": int(timeout_seconds),
    "status": "ENABLED",
    "isRunNow": True,
    "isFailureRetried": json.loads(failure_retried),
    "isDefaultSnapshotEnabled": json.loads(default_snapshot_enabled),
    "isCertificateValidationEnabled": True,
    "dnsConfiguration": json.loads(dns_config_json),
    "scriptParameters": json.loads(pathlib.Path(monitor_parameters_file).read_text(encoding="utf-8")),
    "availabilityConfiguration": {
        "maxAllowedFailuresPerInterval": 1,
        "minAllowedRunsPerInterval": 1,
    },
    "freeformTags": {
        "project": "octo-apm-demo",
        "deployment": "private-demo",
        "lab": "availability-monitoring",
        "journey": "browser-checkout-payment-observability",
    },
}
print(json.dumps(payload))
PY
}

ensure_scripted_browser_monitor() {
    if [[ ! -f "${SYNTHETIC_SCRIPT_PATH}" ]]; then
        echo "[availability] Synthetic script not found: ${SYNTHETIC_SCRIPT_PATH}" >&2
        return 2
    fi

    if [[ "${APPLY}" == "true" && -z "${OCTO_ADMIN_PASSWORD:-}" && -z "${OCTO_ADMIN_PASSWORD_SECRET_OCID:-}" ]]; then
        echo "[availability] OCTO_ADMIN_PASSWORD or OCTO_ADMIN_PASSWORD_SECRET_OCID is required for the scripted browser monitor admin steps." >&2
        return 2
    fi

    if [[ "${APPLY}" != "true" ]]; then
        cat <<EOF
[DRY RUN] Would upsert Scripted Browser monitor:
  script:        ${SYNTHETIC_SCRIPT_NAME}
  scriptFile:    ${SYNTHETIC_SCRIPT_PATH}
  monitor:       ${SYNTHETIC_MONITOR_NAME}
  target:        ${SYNTHETIC_SHOP_URL}
  adminTarget:   ${SYNTHETIC_ADMIN_URL}
  mode:          ${SYNTHETIC_DEMO_MODE}
  interval:      ${SYNTHETIC_REPEAT_INTERVAL_SECONDS}s
  timeout:       ${SYNTHETIC_TIMEOUT_SECONDS}s
  retry:         ${SYNTHETIC_FAILURE_RETRIED}
  secretParams:  OCTO_ADMIN_PASSWORD required; OCTO_INTERNAL_SERVICE_KEY optional
EOF
        return 0
    fi

    local script_payload script_id monitor_payload monitor_id
    script_payload="$(new_temp_json)"
    write_script_payload "${script_payload}"
    script_id="$(oci_cli apm-synthetics script-collection list-scripts \
        --apm-domain-id "${APM_DOMAIN_ID}" \
        --display-name "${SYNTHETIC_SCRIPT_NAME}" \
        --all \
        --query 'data.items[0].id' \
        --raw-output 2>/dev/null || true)"

    if [[ -n "${script_id}" && "${script_id}" != "null" && "${script_id}" != "None" ]]; then
        oci_cli apm-synthetics script update \
            --script-id "${script_id}" \
            --from-json "file://${script_payload}" \
            --force >/dev/null
        echo "[availability] Script updated: ${SYNTHETIC_SCRIPT_NAME}"
    else
        script_id="$(oci_cli apm-synthetics script create \
            --from-json "file://${script_payload}" \
            --query 'data.id' \
            --raw-output)"
        echo "[availability] Script created: ${SYNTHETIC_SCRIPT_NAME}"
    fi

    monitor_payload="$(new_temp_json)"
    write_scripted_monitor_payload "${monitor_payload}" "${script_id}"
    monitor_id="$(oci_cli apm-synthetics monitor-collection list-monitors \
        --apm-domain-id "${APM_DOMAIN_ID}" \
        --display-name "${SYNTHETIC_MONITOR_NAME}" \
        --all \
        --query 'data.items[0].id' \
        --raw-output 2>/dev/null || true)"

    if [[ -n "${monitor_id}" && "${monitor_id}" != "null" && "${monitor_id}" != "None" ]]; then
        oci_cli apm-synthetics monitor update-scripted-browser-monitor \
            --monitor-id "${monitor_id}" \
            --from-json "file://${monitor_payload}" \
            --force >/dev/null
        echo "[availability] Scripted Browser monitor updated: ${SYNTHETIC_MONITOR_NAME}"
    else
        oci_cli apm-synthetics monitor create-scripted-browser-monitor \
            --from-json "file://${monitor_payload}" >/dev/null
        echo "[availability] Scripted Browser monitor created: ${SYNTHETIC_MONITOR_NAME}"
    fi
}

echo "[availability] APM domain: ${APM_DOMAIN_ID}"
echo "[availability] Apply:      ${APPLY}"
echo "[availability] Vantage points:"
printf '  - %s\n' ${VANTAGE_POINTS_CSV//,/ }

create_monitor "${MONITOR_PREFIX}-drones-ready-global" "${SHOP_READY_URL}"
create_monitor "${MONITOR_PREFIX}-admin-ready-global" "${ADMIN_READY_URL}"
if [[ "$(json_bool "${SYNTHETIC_BROWSER_MONITOR_ENABLED}")" == "true" ]]; then
    ensure_scripted_browser_monitor
fi

cat <<EOF

Availability monitor setup complete.

Console:
  OCI Console -> Observability & Management -> Application Performance Monitoring -> Availability Monitoring

Validation:
  oci apm-synthetics monitor-collection list-monitors --apm-domain-id "${APM_DOMAIN_ID}" --all
EOF
