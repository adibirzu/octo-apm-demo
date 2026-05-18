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
FIELD_FILE="${ROOT_DIR}/deploy/oci/log_analytics/fields/octo-apm-correlation-fields.json"
OCI_PROFILE="${OCI_CLI_PROFILE:-${OCI_PROFILE:-DEFAULT}}"
LA_NAMESPACE="${LA_NAMESPACE:-${LOG_ANALYTICS_NAMESPACE:-}}"

if [[ -z "${LA_NAMESPACE}" ]]; then
  echo "LA_NAMESPACE or LOG_ANALYTICS_NAMESPACE is required" >&2
  exit 2
fi

existing_fields="$(mktemp)"
cleanup() {
  rm -f "${existing_fields}"
}
trap cleanup EXIT

oci log-analytics field list-fields \
  --profile "${OCI_PROFILE}" \
  --namespace-name "${LA_NAMESPACE}" \
  --all \
  --output json > "${existing_fields}"

jq -c 'if type == "array" then .[] else ((.fields // []) + (.optionalCustomFields // []))[] end' "${FIELD_FILE}" |
while read -r field; do
  semantic_name="$(jq -r '.semanticName // .displayName' <<<"${field}")"
  parser_field_name="$(jq -r '.parserFieldName // .existingDisplayName // .displayName // .semanticName' <<<"${field}")"
  expected_display_name="$(jq -r '.existingDisplayName // .parserFieldName // .displayName // .semanticName' <<<"${field}")"
  expected_field_name="$(jq -r '.existingFieldName // .name // ""' <<<"${field}")"
  create_if_missing="$(jq -r '.createIfMissing // false' <<<"${field}")"

  existing_match="$(
    jq -r \
      --arg expected_display_name "${expected_display_name}" \
      --arg parser_field_name "${parser_field_name}" \
      --arg expected_field_name "${expected_field_name}" \
      '.data.items[]?
       | select(
           ."display-name" == $expected_display_name
           or ."display-name" == $parser_field_name
           or (.name == $expected_field_name and $expected_field_name != "")
         )
       | [.name, ."display-name", ."data-type"] | @tsv' \
      "${existing_fields}" | head -1
  )"

  if [[ -n "${existing_match}" ]]; then
    actual_name="$(cut -f1 <<<"${existing_match}")"
    actual_display_name="$(cut -f2 <<<"${existing_match}")"
    actual_data_type="$(cut -f3 <<<"${existing_match}")"
    echo "REUSE existing field semanticName='${semantic_name}' parserFieldName='${actual_display_name}' name='${actual_name}' dataType='${actual_data_type}'"
    continue
  fi

  if [[ "${create_if_missing}" != "true" ]]; then
    echo "SKIP missing optional field semanticName='${semantic_name}' parserFieldName='${parser_field_name}' createIfMissing=false"
    continue
  fi

  create_display_name="$(jq -r '.create.displayName // .displayName // .semanticName' <<<"${field}")"
  data_type="$(jq -r '.create.dataType // .dataType // "STRING"' <<<"${field}")"
  description="$(jq -r '.create.description // .description // ("OCTO APM field for " + (.semanticName // .displayName))' <<<"${field}")"
  is_multi_valued="$(jq -r '.create.isMultiValued // .isMultiValued // false' <<<"${field}")"

  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "DRY RUN create field displayName='${create_display_name}' dataType='${data_type}' isMultiValued='${is_multi_valued}'"
    continue
  fi

  echo "Creating field displayName='${create_display_name}'"
  oci log-analytics field upsert-field \
    --profile "${OCI_PROFILE}" \
    --namespace-name "${LA_NAMESPACE}" \
    --display-name "${create_display_name}" \
    --data-type "${data_type}" \
    --description "${description}" \
    --is-multi-valued "${is_multi_valued}" >/dev/null
done
