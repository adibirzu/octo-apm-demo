#!/usr/bin/env bash
# Export OCI Cloud Guard OSQuery ad-hoc results into an OCI custom log so the
# existing Logging -> Service Connector -> Log Analytics path can parse and
# dashboard the findings.
#
# Safe default: DRY_RUN=true. Set DRY_RUN=false only after the target
# OCI_LOG_ID is confirmed to feed the Log Analytics connector.
#
# Required:
#   COMPARTMENT_ID        Compartment containing the Cloud Guard ad-hoc query
#   OCI_LOG_ID            OCI custom log OCID to ingest normalized results
#
# Optional:
#   ADHOC_QUERY_ID        Single OCID or comma-separated ad-hoc query OCIDs
#   ATTACK_ID             Attack lab id to correlate results with app spans
#   QUERY_STATUS          Query status to auto-discover (default COMPLETED)
#   MAX_QUERIES           Auto-discovery limit (default 5)
#   MAX_ENTRIES           Max result entries per ad-hoc query (default 200)
#   DRY_RUN               true by default; false pushes to OCI Logging
#
# Usage:
#   OCI_CLI_PROFILE=<profile> \
#   COMPARTMENT_ID=ocid1.compartment... \
#   OCI_LOG_ID=ocid1.log... \
#   ./deploy/oci/export_osquery_results_to_logging.sh
#
#   DRY_RUN=false ATTACK_ID=attack-abc123 ADHOC_QUERY_ID=ocid1.cloudguardadhocquery... \
#   COMPARTMENT_ID=ocid1.compartment... OCI_LOG_ID=ocid1.log... \
#   ./deploy/oci/export_osquery_results_to_logging.sh

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
: "${OCI_LOG_ID:?OCI_LOG_ID is required}"

DRY_RUN="${DRY_RUN:-true}"
QUERY_STATUS="${QUERY_STATUS:-COMPLETED}"
MAX_QUERIES="${MAX_QUERIES:-5}"
MAX_ENTRIES="${MAX_ENTRIES:-200}"
ATTACK_ID="${ATTACK_ID:-}"

if ! command -v oci >/dev/null 2>&1; then
    echo "[osquery-export] OCI CLI is required" >&2
    exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

discover_query_ids() {
    if [[ -n "${ADHOC_QUERY_ID:-}" ]]; then
        printf '%s\n' "${ADHOC_QUERY_ID}" | tr ',' '\n' | sed '/^[[:space:]]*$/d'
        return 0
    fi

    local listing="${tmpdir}/adhoc-list.json"
    oci cloud-guard adhoc-query list \
        --compartment-id "${COMPARTMENT_ID}" \
        --adhoc-query-status "${QUERY_STATUS}" \
        --sort-by timeCreated \
        --sort-order DESC \
        --limit "${MAX_QUERIES}" \
        --output json >"${listing}"

    python3 - "${listing}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
for item in payload.get("data", {}).get("items", []):
    query_id = item.get("id")
    if query_id:
        print(query_id)
PY
}

normalize_results() {
    local adhoc_query_id="$1"
    local result_file="$2"
    local batch_file="$3"
    python3 - "${adhoc_query_id}" "${result_file}" "${batch_file}" "${COMPARTMENT_ID}" "${ATTACK_ID}" "${MAX_ENTRIES}" <<'PY'
import csv
import gzip
import io
import json
import sys
from datetime import datetime, timezone

adhoc_query_id, result_path, batch_path, compartment_id, attack_id, max_entries_raw = sys.argv[1:7]
max_entries = max(1, int(max_entries_raw or "200"))
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

with open(result_path, "rb") as handle:
    raw_bytes = handle.read()
if raw_bytes.startswith(b"\x1f\x8b"):
    raw_bytes = gzip.decompress(raw_bytes)
raw_text = raw_bytes.decode("utf-8", errors="replace").strip()

def records_from_json(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return [{"raw": value}]
    for key in ("items", "results", "data"):
        child = value.get(key)
        if isinstance(child, list):
            return child
        if isinstance(child, dict):
            for nested_key in ("items", "results"):
                nested = child.get(nested_key)
                if isinstance(nested, list):
                    return nested
    return [value]

def records_from_csv(text):
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames:
            return list(reader)
    except csv.Error:
        return []
    return []

try:
    parsed = json.loads(raw_text) if raw_text else {}
    records = records_from_json(parsed)
except json.JSONDecodeError:
    records = records_from_csv(raw_text)
    if not records:
        records = [{"raw": line} for line in raw_text.splitlines() if line.strip()]

entries = []
for index, record in enumerate(records[:max_entries]):
    if not isinstance(record, dict):
        record = {"raw": record}
    instance_id = (
        record.get("resourceId")
        or record.get("resource_id")
        or record.get("instanceId")
        or record.get("instance_id")
        or ""
    )
    query_name = (
        record.get("queryName")
        or record.get("query_name")
        or record.get("name")
        or "cloud-guard-adhoc"
    )
    finding = json.dumps(record, sort_keys=True, default=str)[:1200]
    event = {
        "timestamp": now,
        "level": "WARNING",
        "logger": "cloudguard.osquery",
        "message": "Cloud Guard OSQuery result",
        "service.name": "oci-cloud-guard",
        "deployment.environment": "private-demo",
        "security.attack.id": attack_id,
        "security.severity": record.get("severity") or "medium",
        "osquery.query": query_name,
        "osquery.finding": finding,
        "osquery.result_count": len(records),
        "cloud.adhoc_query.id": adhoc_query_id,
        "cloud.compartment.id": compartment_id,
        "cloud.instance.id": instance_id,
    }
    sql = record.get("query") or record.get("sql") or record.get("queryString") or ""
    if sql:
        event["osquery.sql"] = str(sql)
    entries.append({
        "id": f"osquery-{adhoc_query_id.rsplit('.', 1)[-1]}-{index}",
        "time": now,
        "data": json.dumps(event, sort_keys=True, default=str),
    })

batch = [
    {
        "source": "cloudguard-osquery",
        "type": "octo-osquery-result",
        "subject": "private-demo-attack-lab",
        "entries": entries,
    }
]
with open(batch_path, "w", encoding="utf-8") as handle:
    json.dump(batch, handle, indent=2)
print(len(entries))
PY
}

query_count=0
entry_count=0
while IFS= read -r adhoc_query_id; do
    [[ -z "${adhoc_query_id}" ]] && continue
    query_count=$((query_count + 1))
    result_file="${tmpdir}/${query_count}-results.out"
    batch_file="${tmpdir}/${query_count}-log-batch.json"

    echo "[osquery-export] Downloading results for ${adhoc_query_id}"
    oci cloud-guard adhoc-query-result-collection get-adhoc-query-result-content \
        --adhoc-query-id "${adhoc_query_id}" \
        --file "${result_file}" >/dev/null

    count="$(normalize_results "${adhoc_query_id}" "${result_file}" "${batch_file}")"
    entry_count=$((entry_count + count))

    if [[ "${DRY_RUN}" == "true" ]]; then
        echo "[DRY RUN] Would push ${count} normalized OSQuery log entries to ${OCI_LOG_ID}"
        sed -n '1,120p' "${batch_file}"
    elif [[ "${count}" -gt 0 ]]; then
        oci logging-ingestion put-logs \
            --log-id "${OCI_LOG_ID}" \
            --specversion "1.0" \
            --log-entry-batches "file://${batch_file}" >/dev/null
        echo "[osquery-export] Pushed ${count} entries for ${adhoc_query_id}"
    else
        echo "[osquery-export] No result entries found for ${adhoc_query_id}"
    fi
done < <(discover_query_ids)

if [[ "${query_count}" -eq 0 ]]; then
    echo "[osquery-export] No ad-hoc queries found. Provide ADHOC_QUERY_ID or wait for Cloud Guard results." >&2
    exit 1
fi

echo "[osquery-export] Complete: queries=${query_count}, entries=${entry_count}, dry_run=${DRY_RUN}"
