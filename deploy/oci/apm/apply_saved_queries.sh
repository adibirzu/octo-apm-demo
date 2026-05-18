#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=true
case "${1:-}" in
  -h|--help)
    echo "Usage: $0 [--dry-run|--apply]"
    exit 0
    ;;
  --apply) DRY_RUN=false ;;
  --dry-run|"") DRY_RUN=true ;;
  *)
    echo "Usage: $0 [--dry-run|--apply]" >&2
    exit 2
    ;;
esac

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
QUERY_DIR="${ROOT_DIR}/deploy/oci/apm/saved-queries"

OCI_PROFILE="${OCI_CLI_PROFILE:-${OCI_PROFILE:-DEFAULT}}"
COMPARTMENT_ID="${COMPARTMENT_ID:-}"
APM_DOMAIN_ID="${APM_DOMAIN_ID:-}"
PROVIDER_ID="${APM_SAVED_QUERY_PROVIDER_ID:-apm-traces}"
PROVIDER_NAME="${APM_SAVED_QUERY_PROVIDER_NAME:-Application Performance Monitoring}"

if [[ -z "${COMPARTMENT_ID}" ]]; then
  echo "COMPARTMENT_ID is required" >&2
  exit 2
fi

tmp_payload="$(mktemp)"
cleanup() {
  rm -f "${tmp_payload}"
}
trap cleanup EXIT

for query_file in "${QUERY_DIR}"/*.json; do
  [[ "$(basename "${query_file}")" == "README.md" ]] && continue
  display_name="$(jq -r '.displayName' "${query_file}")"
  query_name="$(jq -r '.name' "${query_file}")"

  jq -n \
    --slurpfile query "${query_file}" \
    --arg compartment_id "${COMPARTMENT_ID}" \
    --arg apm_domain_id "${APM_DOMAIN_ID}" \
    --arg provider_id "${PROVIDER_ID}" \
    --arg provider_name "${PROVIDER_NAME}" \
    '{
      compartmentId: $compartment_id,
      displayName: $query[0].displayName,
      description: $query[0].description,
      providerId: $provider_id,
      providerName: $provider_name,
      providerVersion: "3.0.0",
      metadataVersion: "2.0",
      type: "SEARCH_DONT_SHOW_IN_DASHBOARD",
      isOobSavedSearch: false,
      nls: {},
      dataConfig: [],
      screenImage: " ",
      widgetTemplate: "js/dashboardPage/views/noWidgetTemplate.html",
      widgetVM: "js/dashboardPage/viewModels/noWidget",
      parametersConfig: ($query[0].parameters // []),
      featuresConfig: {
        crossService: {
          shared: false
        }
      },
      drilldownConfig: ($query[0].logAnalyticsPivots // []),
      uiConfig: {
        enableWidgetInApp: true,
        queryString: $query[0].queryText,
        apmDomainId: $apm_domain_id,
        timeSelection: {
          timePeriod: ($query[0].scope.defaultLookback // "l24h")
        },
        visualizationType: "trace_explorer",
        vizType: "apmTraceExplorerSavedQuery",
        serviceScope: ($query[0].scope.services // []),
        troubleshootingFields: ($query[0].troubleshootingFields // [])
      },
      freeformTags: {
        platform: "octo-apm-demo",
        managed_by: "deploy/oci/apm/apply_saved_queries.sh",
        query_name: $query[0].name,
        log_analytics_pivots: (($query[0].logAnalyticsPivots // []) | map(.savedSearch) | unique | join(","))
      }
    }' > "${tmp_payload}"

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "DRY RUN: ${display_name} (${query_name})"
    jq '{displayName, providerId, providerName, type, uiConfig:{queryString:.uiConfig.queryString, timeSelection:.uiConfig.timeSelection, serviceScope:.uiConfig.serviceScope}, drilldownConfig, freeformTags}' "${tmp_payload}"
    continue
  fi

  existing_id="$(
    oci management-dashboard saved-search list \
      --profile "${OCI_PROFILE}" \
      --compartment-id "${COMPARTMENT_ID}" \
      --display-name "${display_name}" \
      --all \
      --output json |
      jq -r '.data.items[0].id // empty'
  )"

  if [[ -n "${existing_id}" ]]; then
    echo "Updating ${display_name}"
    oci management-dashboard saved-search update \
      --profile "${OCI_PROFILE}" \
      --management-saved-search-id "${existing_id}" \
      --from-json "file://${tmp_payload}" \
      --force >/dev/null
  else
    echo "Creating ${display_name}"
    oci management-dashboard saved-search create \
      --profile "${OCI_PROFILE}" \
      --from-json "file://${tmp_payload}" >/dev/null
  fi
done
