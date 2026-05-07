#!/usr/bin/env bash
# Create the private-demo OCI Logging -> Log Analytics Service Connector path when
# quota is available.
#
# Safe default: DRY_RUN=true. The script discovers the OCTO logs in one OCI
# Logging log group, builds one consolidated Service Connector source, checks
# service-connector-count availability, and prints the create action. Set
# DRY_RUN=false only after smoke tests pass and quota is available.
#
# Required:
#   COMPARTMENT_ID       Compartment where the connector is created
#   OCI_LOG_GROUP_ID     OCI Logging log group containing the OCTO logs
#   LA_LOG_GROUP_ID      OCI Log Analytics log group destination
#
# Optional:
#   DEPLOYMENT_PREFIX    Default: octo-demo
#   CONNECTOR_NAME       Default: ${DEPLOYMENT_PREFIX}-la-observability
#   LOG_DISPLAY_NAMES    Comma-separated log display names to include
#   LOG_IDS              Comma-separated log OCIDs; bypasses display-name lookup
#   LA_LOG_SOURCE_IDENTIFIER Optional Log Analytics source identifier
#   DRY_RUN              true by default; false creates the connector
#
# Usage:
#   OCI_CLI_PROFILE=<profile> \
#   COMPARTMENT_ID=ocid1.compartment... \
#   OCI_LOG_GROUP_ID=ocid1.loggroup... \
#   LA_LOG_GROUP_ID=ocid1.loganalyticsloggroup... \
#   ./deploy/oci/ensure_log_analytics_connectors.sh
#
#   DRY_RUN=false OCI_CLI_PROFILE=<profile> \
#   COMPARTMENT_ID=ocid1.compartment... \
#   OCI_LOG_GROUP_ID=ocid1.loggroup... \
#   LA_LOG_GROUP_ID=ocid1.loganalyticsloggroup... \
#   ./deploy/oci/ensure_log_analytics_connectors.sh

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
esac

: "${COMPARTMENT_ID:?COMPARTMENT_ID is required}"
: "${OCI_LOG_GROUP_ID:?OCI_LOG_GROUP_ID is required}"
: "${LA_LOG_GROUP_ID:?LA_LOG_GROUP_ID is required}"

DRY_RUN="${DRY_RUN:-true}"
DEPLOYMENT_PREFIX="${DEPLOYMENT_PREFIX:-octo-demo}"
CONNECTOR_NAME="${CONNECTOR_NAME:-${DEPLOYMENT_PREFIX}-la-observability}"
LOG_DISPLAY_NAMES="${LOG_DISPLAY_NAMES:-octo-app,${DEPLOYMENT_PREFIX}-app-stdout,${DEPLOYMENT_PREFIX}-os,octo-security,octo-chaos-audit,${DEPLOYMENT_PREFIX}-waf,${DEPLOYMENT_PREFIX}-cloudguard-raw,${DEPLOYMENT_PREFIX}-cloudguard-query-results}"

if ! command -v oci >/dev/null 2>&1; then
    echo "[la-connector] OCI CLI is required" >&2
    exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

connector_list="${tmpdir}/connectors.json"
log_list="${tmpdir}/logs.json"
source_json="${tmpdir}/source.json"
target_json="${tmpdir}/target.json"
selected_json="${tmpdir}/selected-logs.json"
limit_json="${tmpdir}/limits.json"

echo "[la-connector] Compartment: ${COMPARTMENT_ID}"
echo "[la-connector] OCI log group: ${OCI_LOG_GROUP_ID}"
echo "[la-connector] LA log group:  ${LA_LOG_GROUP_ID}"
echo "[la-connector] Connector:    ${CONNECTOR_NAME}"
echo "[la-connector] Dry run:      ${DRY_RUN}"

oci sch service-connector list \
    --compartment-id "${COMPARTMENT_ID}" \
    --all \
    --output json >"${connector_list}"

existing_id="$(python3 - "${connector_list}" "${CONNECTOR_NAME}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
name = sys.argv[2]
for item in payload.get("data", {}).get("items", []):
    if item.get("display-name") == name and item.get("lifecycle-state") != "DELETED":
        print(item.get("id", ""))
        break
PY
)"

if [[ -n "${existing_id}" ]]; then
    echo "[la-connector] Connector already exists: ${existing_id}"
    exit 0
fi

if [[ -n "${LOG_IDS:-}" ]]; then
    python3 - "${source_json}" "${selected_json}" "${COMPARTMENT_ID}" "${OCI_LOG_GROUP_ID}" "${LOG_IDS}" <<'PY'
import json
import sys

source_path, selected_path, compartment_id, log_group_id, raw_ids = sys.argv[1:6]
log_ids = [value.strip() for value in raw_ids.split(",") if value.strip()]
selected = [{"displayName": log_id.rsplit(".", 1)[-1], "id": log_id} for log_id in log_ids]
source = {
    "kind": "logging",
    "logSources": [
        {"compartmentId": compartment_id, "logGroupId": log_group_id, "logId": item["id"]}
        for item in selected
    ],
}
json.dump(source, open(source_path, "w", encoding="utf-8"), indent=2)
json.dump(selected, open(selected_path, "w", encoding="utf-8"), indent=2)
PY
else
    oci logging log list \
        --log-group-id "${OCI_LOG_GROUP_ID}" \
        --all \
        --output json >"${log_list}"

    python3 - "${log_list}" "${source_json}" "${selected_json}" "${COMPARTMENT_ID}" "${OCI_LOG_GROUP_ID}" "${LOG_DISPLAY_NAMES}" <<'PY'
import json
import sys

log_list_path, source_path, selected_path, compartment_id, log_group_id, raw_names = sys.argv[1:7]
with open(log_list_path, encoding="utf-8") as handle:
    payload = json.load(handle)
logs = payload.get("data", [])
by_name = {item.get("display-name"): item for item in logs}
selected = []
missing = []
for name in [value.strip() for value in raw_names.split(",") if value.strip()]:
    item = by_name.get(name)
    if item and item.get("id"):
        selected.append({"displayName": name, "id": item["id"]})
    else:
        missing.append(name)

if not selected:
    print("No requested logs were found in the OCI log group.", file=sys.stderr)
    if missing:
        print("Missing: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(4)

source = {
    "kind": "logging",
    "logSources": [
        {"compartmentId": compartment_id, "logGroupId": log_group_id, "logId": item["id"]}
        for item in selected
    ],
}
json.dump(source, open(source_path, "w", encoding="utf-8"), indent=2)
json.dump({"selected": selected, "missing": missing}, open(selected_path, "w", encoding="utf-8"), indent=2)
PY
fi

python3 - "${target_json}" "${LA_LOG_GROUP_ID}" "${LA_LOG_SOURCE_IDENTIFIER:-}" <<'PY'
import json
import sys

target_path, log_group_id, source_identifier = sys.argv[1:4]
target = {"kind": "loggingAnalytics", "logGroupId": log_group_id}
if source_identifier:
    target["logSourceIdentifier"] = source_identifier
json.dump(target, open(target_path, "w", encoding="utf-8"), indent=2)
PY

echo "[la-connector] Log sources selected:"
python3 - "${selected_json}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
items = payload.get("selected", payload if isinstance(payload, list) else [])
for item in items:
    print(f"  - {item.get('displayName')}: {item.get('id')}")
missing = payload.get("missing", []) if isinstance(payload, dict) else []
if missing:
    print("  missing optional logs: " + ", ".join(missing))
PY

if ! oci limits resource-availability get \
    --service-name service-connector-hub \
    --limit-name service-connector-count \
    --compartment-id "${COMPARTMENT_ID}" \
    --output json >"${limit_json}" 2>/dev/null; then
    printf '{"data":{"available":0}}\n' >"${limit_json}"
fi

available="$(python3 - "${limit_json}" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
    value = payload.get("data", {}).get("available", 0)
    print(int(float(value or 0)))
except Exception:
    print(0)
PY
)"

if [[ "${available}" -lt 1 ]]; then
    echo "[la-connector] service-connector-count available=${available}; no connector can be created."
    echo "[la-connector] Existing shared connectors were not modified."
    if [[ "${DRY_RUN}" == "true" ]]; then
        exit 0
    fi
    exit 3
fi

if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY RUN] Would create consolidated Logging -> Log Analytics connector:"
    cat <<EOF
oci sch service-connector create \\
  --compartment-id "${COMPARTMENT_ID}" \\
  --display-name "${CONNECTOR_NAME}" \\
  --description "Route private-demo app, OS, security, OSQuery, and WAF logs into Log Analytics." \\
  --source file://${source_json} \\
  --target file://${target_json}
EOF
    exit 0
fi

oci sch service-connector create \
    --compartment-id "${COMPARTMENT_ID}" \
    --display-name "${CONNECTOR_NAME}" \
    --description "Route private-demo app, OS, security, OSQuery, and WAF logs into Log Analytics." \
    --source "file://${source_json}" \
    --target "file://${target_json}" \
    --freeform-tags '{"project":"octo-apm-demo","deployment":"private-demo","lab":"log-analytics"}' \
    --wait-for-state SUCCEEDED \
    --max-wait-seconds 900 >/dev/null

echo "[la-connector] Connector created: ${CONNECTOR_NAME}"
