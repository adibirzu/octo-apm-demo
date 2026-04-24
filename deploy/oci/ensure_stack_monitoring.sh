#!/usr/bin/env bash
# Register the Autonomous Database (ATP) as a MonitoredResource in OCI
# Stack Monitoring so the database is included in the topology + health
# views alongside the OKE pods.
#
# Why shell instead of Terraform: as of writing, OCI Stack Monitoring
# resource onboarding requires the OCI CLI `stack-monitoring resource
# create` flow plus the associated DB credential / management-agent
# inputs, which is simpler to drive
# from bash than via the terraform-provider-oci `oci_stack_monitoring_*`
# resources (several of which are still marked preview).
#
# Idempotent: checks for an existing monitored resource of the same name
# before creating a new one.
#
# Usage:
#   COMPARTMENT_ID=ocid1.compartment... \
#   AUTONOMOUS_DATABASE_ID=ocid1.autonomousdatabase... \
#   MANAGEMENT_AGENT_ID=ocid1.managementagent... \
#   SM_RESOURCE_NAME=octo-atp \
#   ./deploy/oci/ensure_stack_monitoring.sh

set -euo pipefail

: "${COMPARTMENT_ID:?Set COMPARTMENT_ID}"
: "${AUTONOMOUS_DATABASE_ID:?Set AUTONOMOUS_DATABASE_ID (ATP OCID)}"
SM_RESOURCE_NAME="${SM_RESOURCE_NAME:-octo-atp}"
SM_RESOURCE_TYPE="${SM_RESOURCE_TYPE:-oci_oracle_db}"
MANAGEMENT_AGENT_ID="${MANAGEMENT_AGENT_ID:-}"
DB_CONNECTION_DETAILS_JSON="${DB_CONNECTION_DETAILS_JSON:-}"
DRY_RUN="${DRY_RUN:-true}"

echo "================================================================"
echo " Stack Monitoring bootstrap"
echo "   Compartment:     ${COMPARTMENT_ID:0:24}..."
echo "   ATP OCID:        ${AUTONOMOUS_DATABASE_ID:0:24}..."
echo "   Resource name:   ${SM_RESOURCE_NAME}"
echo "   Resource type:   ${SM_RESOURCE_TYPE}"
echo "   Mgmt agent:      ${MANAGEMENT_AGENT_ID:-<unset>}"
echo "   Dry run:         ${DRY_RUN}"
echo "================================================================"

# ── 1. Check whether a MonitoredResource with this name already exists ──
existing=$(oci stack-monitoring resource list \
    --compartment-id "${COMPARTMENT_ID}" \
    --name "${SM_RESOURCE_NAME}" \
    --all 2>/dev/null \
    | python3 -c 'import json,sys;d=json.load(sys.stdin).get("data",{});items=d.get("items",[]);print(items[0].get("id","")) if items else print("")' \
    2>/dev/null || echo "")

if [[ -n "${existing}" ]]; then
    echo "Existing MonitoredResource found: ${existing} — nothing to do."
    exit 0
fi

# ── 2. Create the MonitoredResource ─────────────────────────────────────
if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[DRY RUN] Would create MonitoredResource:"
    cat <<EOF
  oci stack-monitoring resource create \\
      --compartment-id "${COMPARTMENT_ID}" \\
      --name "${SM_RESOURCE_NAME}" \\
      --type "${SM_RESOURCE_TYPE}" \\
      --display-name "OCTO Autonomous DB" \\
      --external-resource-id "${AUTONOMOUS_DATABASE_ID}" \\
      --management-agent-id "<required>" \\
      ${DB_CONNECTION_DETAILS_JSON:+--db-connection-details file://<json>}
EOF
    echo "Re-run with DRY_RUN=false to apply."
    exit 0
fi

if [[ -z "${MANAGEMENT_AGENT_ID}" ]]; then
    echo "MANAGEMENT_AGENT_ID is required by the current OCI Stack Monitoring create flow." >&2
    echo "Find an active Management Agent first, then rerun with MANAGEMENT_AGENT_ID set." >&2
    exit 1
fi

create_cmd=(
    oci stack-monitoring resource create
    --compartment-id "${COMPARTMENT_ID}"
    --name "${SM_RESOURCE_NAME}"
    --type "${SM_RESOURCE_TYPE}"
    --display-name "OCTO Autonomous DB"
    --external-resource-id "${AUTONOMOUS_DATABASE_ID}"
    --management-agent-id "${MANAGEMENT_AGENT_ID}"
    --wait-for-state SUCCEEDED
)

if [[ -n "${DB_CONNECTION_DETAILS_JSON}" ]]; then
    create_cmd+=(--db-connection-details "file://${DB_CONNECTION_DETAILS_JSON}")
fi

"${create_cmd[@]}"

echo "MonitoredResource registered. Check OCI Console → Observability → Stack Monitoring."
