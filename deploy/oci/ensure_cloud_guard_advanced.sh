#!/usr/bin/env bash
# Enable/preflight OCI Cloud Guard Instance Security for a private demo and prepare
# OSQuery saved/ad-hoc queries.
#
# Safe default: DRY_RUN=true. The script performs read-only discovery, prints
# what would change, and exits without creating targets or queries. Set
# DRY_RUN=false only after deployment tests pass and you accept Instance
# Security licensing/entitlement requirements in the tenancy.
#
# Required:
#   COMPARTMENT_ID          Compartment to target
# Optional:
#   REPORTING_REGION        Cloud Guard reporting region
#   TARGET_NAME             Cloud Guard target display name
#   INSTANCE_SECURITY_DETECTOR_RECIPE_ID
#   OSQUERY_INSTANCE_IDS    Comma-separated Compute instance OCIDs for ad-hoc queries
#   RUN_ADHOC               true to submit ad-hoc OSQueries when DRY_RUN=false
#
# Usage:
#   OCI_CLI_PROFILE=<profile> \
#   COMPARTMENT_ID=ocid1.compartment... \
#   ./deploy/oci/ensure_cloud_guard_advanced.sh
#
#   DRY_RUN=false RUN_ADHOC=true OSQUERY_INSTANCE_IDS=ocid1.instance... \
#   COMPARTMENT_ID=ocid1.compartment... \
#   ./deploy/oci/ensure_cloud_guard_advanced.sh

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

DRY_RUN="${DRY_RUN:-true}"
RUN_ADHOC="${RUN_ADHOC:-false}"
REPORTING_REGION="${REPORTING_REGION:-${OCI_REGION:-${OCI_CLI_REGION:-}}}"
DEPLOYMENT_PREFIX="${DEPLOYMENT_PREFIX:-octo-demo}"
TARGET_NAME="${TARGET_NAME:-${DEPLOYMENT_PREFIX}-instance-security}"
QUERY_PREFIX="${QUERY_PREFIX:-${DEPLOYMENT_PREFIX}}"

if ! command -v oci >/dev/null 2>&1; then
    echo "[cloudguard-advanced] OCI CLI is required" >&2
    exit 1
fi

echo "[cloudguard-advanced] Compartment: ${COMPARTMENT_ID}"
echo "[cloudguard-advanced] Target:      ${TARGET_NAME}"
echo "[cloudguard-advanced] Dry run:     ${DRY_RUN}"

cg_json="$(oci cloud-guard configuration get \
    --compartment-id "${COMPARTMENT_ID}" \
    --query 'data.{status:status,reportingRegion:"reporting-region"}' \
    --output json 2>/dev/null || echo '{}')"
cg_status="$(printf '%s' "${cg_json}" | python3 -c 'import json,sys; print((json.load(sys.stdin) or {}).get("status","UNKNOWN"))')"
detected_region="$(printf '%s' "${cg_json}" | python3 -c 'import json,sys; print((json.load(sys.stdin) or {}).get("reportingRegion",""))')"
REPORTING_REGION="${REPORTING_REGION:-${detected_region}}"

echo "[cloudguard-advanced] Cloud Guard: ${cg_status} (reporting region: ${REPORTING_REGION:-unknown})"
if [[ "${cg_status}" != "ENABLED" ]]; then
    echo "[cloudguard-advanced] Cloud Guard must be enabled at tenancy/root before Instance Security can be targeted." >&2
    exit 1
fi

recipe_id="${INSTANCE_SECURITY_DETECTOR_RECIPE_ID:-}"
if [[ -z "${recipe_id}" ]]; then
    recipe_id="$(oci cloud-guard detector-recipe list \
        --compartment-id "${COMPARTMENT_ID}" \
        --all \
        --query "data.items[?detector=='IAAS_INSTANCE_SECURITY_DETECTOR'].id | [0]" \
        --raw-output 2>/dev/null || true)"
fi

if [[ -z "${recipe_id}" || "${recipe_id}" == "null" || "${recipe_id}" == "None" ]]; then
    echo "[cloudguard-advanced] No IAAS_INSTANCE_SECURITY_DETECTOR recipe found in this compartment." >&2
    echo "[cloudguard-advanced] Enable Cloud Guard Instance Security/Advanced Security or provide INSTANCE_SECURITY_DETECTOR_RECIPE_ID." >&2
    exit 1
fi
echo "[cloudguard-advanced] Instance Security detector recipe: ${recipe_id}"

existing_target="$(oci cloud-guard target list \
    --compartment-id "${COMPARTMENT_ID}" \
    --display-name "${TARGET_NAME}" \
    --lifecycle-state ACTIVE \
    --query 'data.items[0].id' \
    --raw-output 2>/dev/null || true)"

if [[ -n "${existing_target}" && "${existing_target}" != "null" && "${existing_target}" != "None" ]]; then
    echo "[cloudguard-advanced] Target exists: ${existing_target}"
    target_id="${existing_target}"
else
    target_id=""
    echo "[cloudguard-advanced] Target missing: ${TARGET_NAME}"
    target_detector_recipes="[{\"detectorRecipeId\":\"${recipe_id}\"}]"
    if [[ "${DRY_RUN}" == "true" ]]; then
        echo "[DRY RUN] Would create Cloud Guard target with Instance Security detector:"
        cat <<EOF
oci cloud-guard target create \\
  --compartment-id "${COMPARTMENT_ID}" \\
  --display-name "${TARGET_NAME}" \\
  --target-resource-id "${COMPARTMENT_ID}" \\
  --target-resource-type COMPARTMENT \\
  --target-detector-recipes '${target_detector_recipes}'
EOF
    else
        target_id="$(oci cloud-guard target create \
            --compartment-id "${COMPARTMENT_ID}" \
            --display-name "${TARGET_NAME}" \
            --target-resource-id "${COMPARTMENT_ID}" \
            --target-resource-type COMPARTMENT \
            --description "Cloud Guard Instance Security for private demo app and compute hosts" \
            --target-detector-recipes "${target_detector_recipes}" \
            --query 'data.id' \
            --raw-output)"
        echo "[cloudguard-advanced] Target created: ${target_id}"
    fi
fi

OSQUERY_KEYS=(
    "unexpected-listeners"
    "lotl-processes"
    "suspicious-shell-history"
    "persistence-systemd"
    "recent-processes"
    "listening-ports"
    "unexpected-users"
    "startup-items"
    "crontab"
    "sudoers"
    "kernel-modules"
)
OSQUERY_SQL=(
    "SELECT p.pid, p.name, p.path, p.cmdline, pos.local_address, pos.local_port, pos.remote_address, pos.remote_port FROM processes p JOIN process_open_sockets pos ON p.pid = pos.pid WHERE pos.local_port NOT IN (22,80,443,8080,18080) OR pos.remote_port IN (4444,8080,8443);"
    "SELECT pid, name, path, cmdline, parent, cwd FROM processes WHERE lower(name) IN ('bash','sh','curl','wget','python','python3','perl','openssl','nc','ncat','socat','ssh') OR lower(cmdline) LIKE '%/dev/tcp%' OR lower(cmdline) LIKE '%base64%' OR lower(cmdline) LIKE '%chmod +x%';"
    "SELECT username, command, history_file FROM shell_history WHERE command LIKE '%curl%' OR command LIKE '%wget%' OR command LIKE '%/dev/tcp%' OR command LIKE '%base64%' OR command LIKE '%chmod +x%' OR command LIKE '%nc %';"
    "SELECT name, path, status, type FROM systemd_units WHERE name LIKE '%octo%' OR name LIKE '%tmp%' OR path LIKE '/tmp/%' OR path LIKE '/var/tmp/%';"
    "SELECT pid, name, path, cmdline, start_time FROM processes WHERE start_time > strftime('%s','now','-30 minutes') ORDER BY start_time DESC;"
    "SELECT pid, port, protocol, address FROM listening_ports;"
    "SELECT username, uid, gid, directory, shell FROM users WHERE uid >= 1000 OR uid = 0;"
    "SELECT name, path, args FROM startup_items;"
    "SELECT event, command, path FROM crontab;"
    "SELECT header, rule_details FROM sudoers;"
    "SELECT name, used_by, status FROM kernel_modules;"
)

create_saved_query() {
    local key="$1"
    local query="$2"
    local display_name="${QUERY_PREFIX}-${key}"
    local existing
    existing="$(oci cloud-guard saved-query list \
        --compartment-id "${COMPARTMENT_ID}" \
        --all \
        --query "data.items[?\"display-name\"=='${display_name}'].id | [0]" \
        --raw-output 2>/dev/null || true)"
    if [[ -n "${existing}" && "${existing}" != "null" && "${existing}" != "None" ]]; then
        echo "[cloudguard-advanced] Saved OSQuery exists: ${display_name} (${existing})"
        return 0
    fi
    if [[ "${DRY_RUN}" == "true" ]]; then
        echo "[DRY RUN] Would create saved OSQuery: ${display_name} -> ${query}"
        return 0
    fi
    oci cloud-guard saved-query create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${display_name}" \
        --description "Private demo OSQuery security control: ${key}" \
        --query-parameterconflict "${query}" \
        --wait-for-state ACTIVE >/dev/null
    echo "[cloudguard-advanced] Saved OSQuery created: ${display_name}"
}

for idx in "${!OSQUERY_KEYS[@]}"; do
    create_saved_query "${OSQUERY_KEYS[$idx]}" "${OSQUERY_SQL[$idx]}"
done

if [[ "${RUN_ADHOC}" == "true" ]]; then
    if [[ -z "${OSQUERY_INSTANCE_IDS:-}" ]]; then
        echo "[cloudguard-advanced] RUN_ADHOC=true requires OSQUERY_INSTANCE_IDS." >&2
        exit 1
    fi
    IFS=',' read -r -a instance_ids <<< "${OSQUERY_INSTANCE_IDS}"
    resources_json="$(mktemp)"
    trap 'rm -f "${resources_json}" "${query_json:-}"' EXIT
    python3 - "${resources_json}" "${REPORTING_REGION}" "${OSQUERY_INSTANCE_IDS}" <<'PY'
import json
import sys

out, region, ids = sys.argv[1], sys.argv[2], [i.strip() for i in sys.argv[3].split(",") if i.strip()]
json.dump([{"region": region, "resourceType": "INSTANCE", "resourceIds": ids}], open(out, "w", encoding="utf-8"))
PY
    for idx in 0 1 2 3 4; do
        key="${OSQUERY_KEYS[$idx]}"
        query_json="$(mktemp)"
        python3 - "${query_json}" "${OSQUERY_SQL[$idx]}" "${resources_json}" <<'PY'
import json
import sys

query_path, query, resources_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(resources_path, encoding="utf-8") as handle:
    resources = json.load(handle)
json.dump({"query": query, "adhocQueryResources": resources}, open(query_path, "w", encoding="utf-8"))
PY
        if [[ "${DRY_RUN}" == "true" ]]; then
            echo "[DRY RUN] Would run ad-hoc OSQuery '${key}' using ${query_json}"
        else
            oci cloud-guard adhoc-query create \
                --compartment-id "${COMPARTMENT_ID}" \
                --adhoc-query-details "file://${query_json}" \
                --wait-for-state ACTIVE
        fi
        rm -f "${query_json}"
    done
fi

cat <<EOF

Cloud Guard Advanced Security preflight complete.

Next validation:
  OCI Console -> Cloud Guard -> Targets -> ${TARGET_NAME}
  OCI Console -> Cloud Guard -> Instance Security -> Queries / Results
  Export completed ad-hoc query results into OCI Logging for Log Analytics:
    ATTACK_ID=<attack-id> ADHOC_QUERY_ID=<adhoc-query-ocid> OCI_LOG_ID=<custom-log-ocid> \
      ./deploy/oci/export_osquery_results_to_logging.sh

Notes:
  - OCI CLI ${OCI_CLI_PROFILE:+profile ${OCI_CLI_PROFILE}, }version: $(oci --version 2>/dev/null || echo unknown)
  - This CLI exposes saved-query and adhoc-query; no scheduled-query command is present in OCI CLI 3.81.1.
EOF
