#!/usr/bin/env bash
set -euo pipefail

# Ensures a dedicated ATP exists for this component.
# If the requested ATP already exists, it is reused.
# If missing, a new ATP is created.

if ! command -v oci >/dev/null 2>&1; then
  echo "ERROR: OCI CLI is required." >&2
  exit 1
fi

COMPARTMENT_ID="${COMPARTMENT_ID:-}"
DISPLAY_NAME="${DISPLAY_NAME:-shared-atp}"
DB_NAME="${DB_NAME:-sharedatp}"
DB_WORKLOAD="${DB_WORKLOAD:-OLTP}"
CPU_CORE_COUNT="${CPU_CORE_COUNT:-1}"
DATA_STORAGE_SIZE_IN_TBS="${DATA_STORAGE_SIZE_IN_TBS:-1}"
LICENSE_MODEL="${LICENSE_MODEL:-LICENSE_INCLUDED}"
WAIT_FOR_AVAILABLE="${WAIT_FOR_AVAILABLE:-true}"

if [[ -z "${COMPARTMENT_ID}" ]]; then
  echo "ERROR: set COMPARTMENT_ID" >&2
  exit 1
fi

echo "Checking ATP in compartment ${COMPARTMENT_ID} with display name '${DISPLAY_NAME}'..."
EXISTING_ID="$(oci db autonomous-database list \
  --compartment-id "${COMPARTMENT_ID}" \
  --all \
  --query "data[?\"display-name\"=='${DISPLAY_NAME}'].id | [0]" \
  --raw-output)"

if [[ -n "${EXISTING_ID}" && "${EXISTING_ID}" != "null" ]]; then
  echo "ATP already exists: ${EXISTING_ID}"
  EXISTING_STATE="$(oci db autonomous-database get \
    --autonomous-database-id "${EXISTING_ID}" \
    --query 'data."lifecycle-state"' \
    --raw-output)"
  if [[ "${EXISTING_STATE}" == "STOPPED" ]]; then
    echo "ATP is STOPPED — starting ${EXISTING_ID}..."
    oci db autonomous-database start --autonomous-database-id "${EXISTING_ID}" >/dev/null
    if [[ "${WAIT_FOR_AVAILABLE}" == "true" ]]; then
      oci db autonomous-database get \
        --autonomous-database-id "${EXISTING_ID}" \
        --wait-for-state AVAILABLE >/dev/null
    fi
  elif [[ "${EXISTING_STATE}" != "AVAILABLE" && "${WAIT_FOR_AVAILABLE}" == "true" ]]; then
    echo "Waiting for existing ATP to become AVAILABLE (current state: ${EXISTING_STATE})..."
    oci db autonomous-database get \
      --autonomous-database-id "${EXISTING_ID}" \
      --wait-for-state AVAILABLE >/dev/null
  fi
  oci db autonomous-database get --autonomous-database-id "${EXISTING_ID}" \
    --query 'data.{id:id,display_name:"display-name",db_name:"db-name",state:"lifecycle-state",connection_strings:"connection-strings"."all-connection-strings"}' \
    --output json
  exit 0
fi

ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
if [[ -z "${ADMIN_PASSWORD}" ]]; then
  echo "ERROR: ATP not found and ADMIN_PASSWORD is not set for creation." >&2
  exit 1
fi

echo "Creating ATP '${DISPLAY_NAME}' (${DB_NAME})..."
CREATE_OUT="$(mktemp)"
oci db autonomous-database create \
  --compartment-id "${COMPARTMENT_ID}" \
  --display-name "${DISPLAY_NAME}" \
  --db-name "${DB_NAME}" \
  --db-workload "${DB_WORKLOAD}" \
  --is-auto-scaling-enabled true \
  --compute-model ECPU \
  --compute-count "${CPU_CORE_COUNT}" \
  --data-storage-size-in-tbs "${DATA_STORAGE_SIZE_IN_TBS}" \
  --admin-password "${ADMIN_PASSWORD}" \
  --license-model "${LICENSE_MODEL}" \
  --wait-for-state PROVISIONING \
  > "${CREATE_OUT}"

NEW_ID="$(jq -r '.data.id' "${CREATE_OUT}")"
rm -f "${CREATE_OUT}"

echo "ATP create request accepted: ${NEW_ID}"
if [[ "${WAIT_FOR_AVAILABLE}" == "true" ]]; then
  echo "Waiting for ATP to become AVAILABLE..."
  oci db autonomous-database get \
    --autonomous-database-id "${NEW_ID}" \
    --wait-for-state AVAILABLE >/dev/null
fi

oci db autonomous-database get --autonomous-database-id "${NEW_ID}" \
  --query 'data.{id:id,display_name:"display-name",db_name:"db-name",state:"lifecycle-state",connection_strings:"connection-strings"."all-connection-strings"}' \
  --output json
