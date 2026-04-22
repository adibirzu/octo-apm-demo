#!/usr/bin/env bash
# Register the Autonomous Database (ATP) as a MonitoredResource in OCI
# Stack Monitoring so the database is included in the topology + health
# views alongside the OKE pods.
#
# Why shell instead of Terraform: as of writing, OCI Stack Monitoring
# resource onboarding requires the OCI CLI `stack-monitoring monitored-resource
# create` flow plus the associated DB credential, which is simpler to drive
# from bash than via the terraform-provider-oci `oci_stack_monitoring_*`
# resources (several of which are still marked preview).
#
# Idempotent: checks for an existing monitored resource of the same name
# before creating a new one.
#
# Usage:
#   COMPARTMENT_ID=ocid1.compartment... \
#   AUTONOMOUS_DATABASE_ID=ocid1.autonomousdatabase... \
#   SM_RESOURCE_NAME=octo-atp \
#   ./deploy/oci/ensure_stack_monitoring.sh

set -euo pipefail

: "${COMPARTMENT_ID:?Set COMPARTMENT_ID}"
: "${AUTONOMOUS_DATABASE_ID:?Set AUTONOMOUS_DATABASE_ID (ATP OCID)}"
SM_RESOURCE_NAME="${SM_RESOURCE_NAME:-octo-atp}"
SM_RESOURCE_TYPE="${SM_RESOURCE_TYPE:-oracle_database_autonomous_transaction_processing}"
DRY_RUN="${DRY_RUN:-true}"

echo "================================================================"
echo " Stack Monitoring bootstrap"
echo "   Compartment:     ${COMPARTMENT_ID:0:24}..."
echo "   ATP OCID:        ${AUTONOMOUS_DATABASE_ID:0:24}..."
echo "   Resource name:   ${SM_RESOURCE_NAME}"
echo "   Resource type:   ${SM_RESOURCE_TYPE}"
echo "   Dry run:         ${DRY_RUN}"
echo "================================================================"

# ── 1. Check whether a MonitoredResource with this name already exists ──
existing=$(oci stack-monitoring monitored-resource list \
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
  oci stack-monitoring monitored-resource create \\
      --compartment-id "${COMPARTMENT_ID}" \\
      --name "${SM_RESOURCE_NAME}" \\
      --type "${SM_RESOURCE_TYPE}" \\
      --display-name "OCTO Autonomous DB" \\
      --resource-id "${AUTONOMOUS_DATABASE_ID}"
EOF
    echo "Re-run with DRY_RUN=false to apply."
    exit 0
fi

oci stack-monitoring monitored-resource create \
    --compartment-id "${COMPARTMENT_ID}" \
    --name "${SM_RESOURCE_NAME}" \
    --type "${SM_RESOURCE_TYPE}" \
    --display-name "OCTO Autonomous DB" \
    --resource-id "${AUTONOMOUS_DATABASE_ID}" \
    --wait-for-state SUCCEEDED

echo "MonitoredResource registered. Check OCI Console → Observability → Stack Monitoring."
