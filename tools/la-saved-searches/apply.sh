#!/usr/bin/env bash
# Apply the Log Analytics saved searches that power the APM↔LA
# round-trip dashboard. Idempotent — upserts by name.
#
# Usage:
#   LA_NAMESPACE=<oci-tenancy-la-namespace> \
#   LA_LOG_GROUP_ID=ocid1.loganalyticsloggroup.oc1..xxx \
#   ./tools/la-saved-searches/apply.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${LA_NAMESPACE:?Set LA_NAMESPACE (from: oci log-analytics namespace list)}"
: "${LA_LOG_GROUP_ID:?Set LA_LOG_GROUP_ID (ocid1.loganalyticsloggroup.oc1...)}"

echo "Applying saved searches to namespace=${LA_NAMESPACE} log-group=${LA_LOG_GROUP_ID:0:24}..."

for f in "${SCRIPT_DIR}"/*.json; do
    [[ "$(basename "$f")" == "apply.sh.json" ]] && continue
    name=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['name'])" "$f")
    echo
    echo "• ${name}"
    oci log-analytics saved-search create-or-update \
        --namespace-name "${LA_NAMESPACE}" \
        --log-analytics-saved-search-id "${name}" \
        --from-json "file://$f" 2>&1 | head -10 || {
            echo "  (check the OCI CLI version — saved-search upsert requires ≥ 3.40)"
            exit 1
        }
done

echo
echo "Done. In APM, configure widget drilldowns to:"
echo "  https://cloud.oracle.com/loganalytics/search?region=\${OCI_REGION}&savedSearch=octo-trace-to-logs&param.trace_id=\${TRACE_ID}"
