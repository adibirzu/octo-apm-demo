#!/usr/bin/env bash
# Apply the Phase 7 APM saved queries to the OCTO APM domain.
#
# Dry-run by default — set APPLY=true to mutate. Even with APPLY=true,
# the script requires an interactive confirm prompt before any OCI CLI
# call mutates the APM domain. Scoped to the OCTO compartment.
#
# Usage (dry-run):
#   COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
#     ./tools/apm-saved-queries/apply.sh
#
# Usage (apply):
#   APPLY=true \
#   COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
#   APM_DOMAIN_ID="<OCTO_APM_DOMAIN_OCID>" \
#     ./tools/apm-saved-queries/apply.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'USAGE'
Apply Phase 7 APM saved queries to the OCTO APM domain.

Environment:
  COMPARTMENT_ID    (required)  OCTO compartment OCID
  APM_DOMAIN_ID     (required when APPLY=true) Target APM domain OCID
  OCI_PROFILE       (optional, default: emdemo)
  APPLY             (optional, default: false) — set to "true" to mutate

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

require_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: required tool '$1' not found on PATH" >&2
        exit 1
    fi
}

require_tool python3
require_tool oci
require_tool jq

echo "Phase 7 APM saved-query apply"
echo "  profile         : ${OCI_PROFILE}"
echo "  compartment     : ${COMPARTMENT_ID:0:24}…"
echo "  apm domain      : ${APM_DOMAIN_ID:-<unset — required for APPLY=true>}"
echo "  mode            : $( [[ "${APPLY}" == "true" ]] && echo APPLY || echo DRY-RUN )"
echo

# List the saved queries that would be applied.
files=()
while IFS= read -r f; do
    files+=("$f")
done < <(find "${SCRIPT_DIR}" -maxdepth 1 -name '*.json' -type f | sort)

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No saved-query JSON files found in ${SCRIPT_DIR}" >&2
    exit 1
fi

echo "Saved queries to apply:"
for f in "${files[@]}"; do
    name=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('name','?'))" "$f")
    display=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('displayName','?'))" "$f")
    echo "  • ${name}  —  ${display}"
done
echo

if [[ "${APPLY}" != "true" ]]; then
    echo "DRY-RUN complete. Re-run with APPLY=true (and APM_DOMAIN_ID set)"
    echo "to mutate APM."
    exit 0
fi

: "${APM_DOMAIN_ID:?APM_DOMAIN_ID is required when APPLY=true}"

echo "About to MUTATE APM domain ${APM_DOMAIN_ID:0:24}… in compartment ${COMPARTMENT_ID:0:24}…"
read -r -p "Type 'APPLY' to confirm: " confirm
if [[ "${confirm}" != "APPLY" ]]; then
    echo "Aborted — confirm phrase did not match."
    exit 1
fi

echo
for f in "${files[@]}"; do
    name=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['name'])" "$f")
    echo "• Applying ${name}"
    # The OCI APM CLI subcommand for saved-query mutation varies across
    # CLI versions. The intended call is along the lines of:
    #
    #   oci apm-traces saved-search create-or-update \
    #     --profile "${OCI_PROFILE}" \
    #     --apm-domain-id "${APM_DOMAIN_ID}" \
    #     --compartment-id "${COMPARTMENT_ID}" \
    #     --from-json "file://${f}"
    #
    # If the subcommand is unknown on this CLI version, fall back to the
    # manual import flow documented in tools/apm-saved-queries/README.md.
    if ! oci apm-traces saved-search create-or-update \
            --profile "${OCI_PROFILE}" \
            --apm-domain-id "${APM_DOMAIN_ID}" \
            --compartment-id "${COMPARTMENT_ID}" \
            --from-json "file://${f}" 2>&1 | head -10; then
        echo "  WARN: 'oci apm-traces saved-search create-or-update' failed —" >&2
        echo "        check OCI CLI version or fall back to manual import." >&2
    fi
done

echo
echo "Done. Verify each saved query in OCI Console → APM → Trace Explorer."
echo "Then wire each widget drilldown to the external_drilldowns[*] URLs"
echo "from the corresponding JSON file (lm/phoenix/openlit/grafana .octodemo.cloud)."
