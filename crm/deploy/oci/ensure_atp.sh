#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Enterprise CRM Portal — Ensure Oracle ATP Exists
#
# Checks for an existing Autonomous Transaction Processing database.
# Creates one if it doesn't exist. Downloads the wallet for mTLS.
#
# Required env vars:
#   COMPARTMENT_ID      — OCI compartment OCID
#
# Optional env vars (with defaults):
#   DISPLAY_NAME        — ATP display name (default: enterprise-crm-atp)
#   DB_NAME             — ATP database name (default: crmportal)
#   DB_WORKLOAD         — OLTP or DW (default: OLTP)
#   CPU_CORE_COUNT      — ECPU count (default: 1)
#   DATA_STORAGE_SIZE_IN_TBS — storage in TB (default: 1)
#   LICENSE_MODEL       — LICENSE_INCLUDED or BYOL (default: LICENSE_INCLUDED)
#   ADMIN_PASSWORD      — required only if creating a new ATP
#   WAIT_FOR_AVAILABLE  — wait for AVAILABLE state (default: true)
#   WALLET_DIR          — download wallet to this dir (default: /tmp/crm-wallet)
#   WALLET_PASSWORD     — wallet password (default: same as ADMIN_PASSWORD)
# ─────────────────────────────────────────────────────────────────────────────

if ! command -v oci >/dev/null 2>&1; then
  echo "ERROR: OCI CLI is required." >&2
  exit 1
fi

COMPARTMENT_ID="${COMPARTMENT_ID:-}"
DISPLAY_NAME="${DISPLAY_NAME:-enterprise-crm-atp}"
DB_NAME="${DB_NAME:-crmportal}"
DB_WORKLOAD="${DB_WORKLOAD:-OLTP}"
CPU_CORE_COUNT="${CPU_CORE_COUNT:-1}"
DATA_STORAGE_SIZE_IN_TBS="${DATA_STORAGE_SIZE_IN_TBS:-1}"
LICENSE_MODEL="${LICENSE_MODEL:-LICENSE_INCLUDED}"
WAIT_FOR_AVAILABLE="${WAIT_FOR_AVAILABLE:-true}"
WALLET_DIR="${WALLET_DIR:-/tmp/crm-wallet}"

if [[ -z "${COMPARTMENT_ID}" ]]; then
  echo "ERROR: set COMPARTMENT_ID" >&2
  exit 1
fi

# ── Helper: download wallet ───────────────────────────────────────
download_wallet() {
  local atp_id="$1"
  local wp="${WALLET_PASSWORD:-${ADMIN_PASSWORD:-}}"

  if [[ -z "${wp}" ]]; then
    echo "WARN: Skipping wallet download (WALLET_PASSWORD / ADMIN_PASSWORD not set)." >&2
    return 0
  fi

  mkdir -p "${WALLET_DIR}"
  local wallet_zip="${WALLET_DIR}/wallet.zip"

  echo "Downloading wallet to ${WALLET_DIR}..."
  if oci db autonomous-database generate-wallet \
    --autonomous-database-id "${atp_id}" \
    --password "${wp}" \
    --file "${wallet_zip}" \
    --generate-type SINGLE 2>/dev/null; then
    unzip -o -q "${wallet_zip}" -d "${WALLET_DIR}"
    rm -f "${wallet_zip}"
    echo "Wallet extracted to ${WALLET_DIR}"
  else
    echo "WARN: Wallet download failed. Download manually from OCI Console." >&2
  fi
}

# ── Check for existing ATP ────────────────────────────────────────
echo "Checking ATP in compartment ${COMPARTMENT_ID} with display name '${DISPLAY_NAME}'..."
EXISTING_ID="$(oci db autonomous-database list \
  --compartment-id "${COMPARTMENT_ID}" \
  --all \
  --query "data[?\"display-name\"=='${DISPLAY_NAME}' && \"lifecycle-state\"!='TERMINATED'].id | [0]" \
  --raw-output 2>/dev/null || true)"

if [[ -n "${EXISTING_ID}" && "${EXISTING_ID}" != "null" ]]; then
  echo "ATP already exists: ${EXISTING_ID}"
  oci db autonomous-database get --autonomous-database-id "${EXISTING_ID}" \
    --query 'data.{id:id,display_name:"display-name",db_name:"db-name",state:"lifecycle-state",connection_strings:"connection-strings"."all-connection-strings"}' \
    --output json

  download_wallet "${EXISTING_ID}"

  echo ""
  echo "Export these for the CRM deployment:"
  echo "  export ATP_OCID=${EXISTING_ID}"
  echo "  export ORACLE_WALLET_DIR=${WALLET_DIR}"
  exit 0
fi

# ── Create new ATP ────────────────────────────────────────────────
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
if [[ -z "${ADMIN_PASSWORD}" ]]; then
  echo "ERROR: ATP not found and ADMIN_PASSWORD is not set for creation." >&2
  exit 1
fi

WALLET_PASSWORD="${WALLET_PASSWORD:-${ADMIN_PASSWORD}}"

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
  echo "Waiting for ATP to become AVAILABLE (this may take 2-5 minutes)..."
  oci db autonomous-database get \
    --autonomous-database-id "${NEW_ID}" \
    --wait-for-state AVAILABLE >/dev/null
  echo "ATP is AVAILABLE."
fi

oci db autonomous-database get --autonomous-database-id "${NEW_ID}" \
  --query 'data.{id:id,display_name:"display-name",db_name:"db-name",state:"lifecycle-state",connection_strings:"connection-strings"."all-connection-strings"}' \
  --output json

download_wallet "${NEW_ID}"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  ATP Ready                                                      ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  OCID:       ${NEW_ID}"
echo "║  DB Name:    ${DB_NAME}"
echo "║  Wallet Dir: ${WALLET_DIR}"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "Export these for the CRM deployment:"
echo "  export ATP_OCID=${NEW_ID}"
echo "  export ORACLE_DSN=${DB_NAME}_low"
echo "  export ORACLE_WALLET_DIR=${WALLET_DIR}"
