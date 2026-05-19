#!/usr/bin/env bash
# Apply the Phase 7 OCI Monitoring alarms (D-18) to the OCTO compartment.
#
# Dry-run by default — set APPLY=true to mutate. Even with APPLY=true,
# the script requires an interactive confirm phrase before any OCI CLI
# call mutates the Monitoring service. Scoped to the OCTO compartment.
#
# Usage (dry-run):
#   COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
#   NOTIFICATION_TOPIC_OCID="<NOTIFICATIONS_TOPIC_OCID>" \
#     ./tools/monitoring-alarms/apply.sh
#
# Usage (apply):
#   APPLY=true \
#   COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
#   NOTIFICATION_TOPIC_OCID="<NOTIFICATIONS_TOPIC_OCID>" \
#     ./tools/monitoring-alarms/apply.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'USAGE'
Apply Phase 7 OCI Monitoring alarms to the OCTO compartment.

Environment:
  COMPARTMENT_ID            (required)  OCTO compartment OCID
  NOTIFICATION_TOPIC_OCID   (required)  OCI Notifications topic OCID
  OCI_PROFILE               (optional, default: emdemo)
  APPLY                     (optional, default: false) — set to "true" to mutate

The default flow is a dry-run that lists what would be applied. When
APPLY=true, the script ALSO requires an interactive confirm before any
mutation.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

: "${OCI_PROFILE:=emdemo}"
: "${APPLY:=false}"
: "${COMPARTMENT_ID:?COMPARTMENT_ID is required — set to the OCTO compartment OCID}"
: "${NOTIFICATION_TOPIC_OCID:?NOTIFICATION_TOPIC_OCID is required — set to the Notifications topic OCID}"

require_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: required tool '$1' not found on PATH" >&2
        exit 1
    fi
}

require_tool python3
require_tool oci
require_tool jq
require_tool envsubst

export COMPARTMENT_ID
export NOTIFICATION_TOPIC_OCID

echo "Phase 7 OCI Monitoring alarm apply"
echo "  profile         : ${OCI_PROFILE}"
echo "  compartment     : ${COMPARTMENT_ID:0:24}…"
echo "  notification    : ${NOTIFICATION_TOPIC_OCID:0:24}…"
echo "  mode            : $( [[ "${APPLY}" == "true" ]] && echo APPLY || echo DRY-RUN )"
echo

files=()
while IFS= read -r f; do
    files+=("$f")
done < <(find "${SCRIPT_DIR}" -maxdepth 1 -name '*.json' -type f | sort)

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No alarm JSON files found in ${SCRIPT_DIR}" >&2
    exit 1
fi

echo "Alarms to apply:"
for f in "${files[@]}"; do
    display=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('displayName','?'))" "$f")
    severity=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('severity','?'))" "$f")
    pending=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('pendingDuration','?'))" "$f")
    echo "  • [${severity}/${pending}] ${display}"
done
echo

TMPDIR_OUT="$(mktemp -d -t monitoring-alarms-XXXXXX)"
trap 'rm -rf "${TMPDIR_OUT}"' EXIT

# Resolve envsubst placeholders into a temp directory.
for f in "${files[@]}"; do
    base="$(basename "$f")"
    envsubst < "$f" > "${TMPDIR_OUT}/${base}"
    # Sanity-check: the substituted file must NOT contain remaining placeholders.
    if grep -q '\${[A-Z_]*}' "${TMPDIR_OUT}/${base}"; then
        echo "ERROR: unresolved envsubst placeholder in ${base} after substitution" >&2
        grep '\${[A-Z_]*}' "${TMPDIR_OUT}/${base}" >&2
        exit 1
    fi
done

if [[ "${APPLY}" != "true" ]]; then
    echo "DRY-RUN: would call 'oci monitoring alarm create' (or update) for each"
    echo "alarm above. Resolved payloads (placeholders substituted) are in:"
    echo "  ${TMPDIR_OUT}"
    echo
    echo "Re-run with APPLY=true to mutate."
    # Keep tmpdir for inspection in dry-run mode.
    trap - EXIT
    exit 0
fi

echo "About to MUTATE Monitoring in compartment ${COMPARTMENT_ID:0:24}…"
read -r -p "Type 'APPLY' to confirm: " confirm
if [[ "${confirm}" != "APPLY" ]]; then
    echo "Aborted — confirm phrase did not match."
    exit 1
fi

echo
for f in "${files[@]}"; do
    base="$(basename "$f")"
    tmp="${TMPDIR_OUT}/${base}"
    display=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['displayName'])" "$tmp")
    echo "• Applying ${display}"

    # Idempotent upsert: list-alarms by display-name, update if found,
    # create otherwise. Mirrors the Cluster Autoscaler install-script
    # pattern in deploy/oke/install-oci-kubernetes-monitoring.sh.
    existing_id=$(
        oci monitoring alarm list \
            --profile "${OCI_PROFILE}" \
            --compartment-id "${COMPARTMENT_ID}" \
            --display-name "${display}" \
            --all 2>/dev/null \
        | jq -r '.data[0].id // empty' 2>/dev/null || true
    )

    if [[ -n "${existing_id}" ]]; then
        echo "  (existing alarm found: ${existing_id:0:24}… — updating)"
        oci monitoring alarm update \
            --profile "${OCI_PROFILE}" \
            --alarm-id "${existing_id}" \
            --from-json "file://${tmp}" 2>&1 | head -10 || {
                echo "  WARN: 'oci monitoring alarm update' failed for ${display}" >&2
            }
    else
        echo "  (no existing alarm — creating)"
        oci monitoring alarm create \
            --profile "${OCI_PROFILE}" \
            --from-json "file://${tmp}" 2>&1 | head -10 || {
                echo "  WARN: 'oci monitoring alarm create' failed for ${display}" >&2
            }
    fi
done

echo
echo "Done. Verify in OCI Console → Monitoring → Alarm Definitions."
echo "During Phase 7 stress runs, 'OCTO — Shop CPU saturation high' is"
echo "expected to fire (alarm-path validation)."
