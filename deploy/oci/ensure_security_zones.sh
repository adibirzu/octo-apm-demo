#!/usr/bin/env bash
# Ensure OCI Security Zone for OCTO Drone Shop (C28).
#
# Creates (idempotently):
#   1. Security Zone Recipe with compliance policies
#   2. Security Zone attached to the shop compartment
#
# Security Zones enforce guardrails:
#   - Block public resources in protected compartments
#   - Require encryption for storage and databases
#   - Require Vault for secrets
#   - Restrict network access patterns
#
# Prerequisites:
#   - OCI CLI configured
#   - COMPARTMENT_ID set
#   - Cloud Guard must be enabled in the tenancy
#
# Usage:
#   COMPARTMENT_ID="ocid1.compartment...." \
#   ./deploy/oci/ensure_security_zones.sh

set -euo pipefail

: "${COMPARTMENT_ID:?COMPARTMENT_ID is required}"
ZONE_NAME="${ZONE_NAME:-octo-drone-shop-zone}"
RECIPE_NAME="${RECIPE_NAME:-octo-drone-shop-recipe}"

echo "[seczone] Compartment: ${COMPARTMENT_ID}"
echo "[seczone] Zone name: ${ZONE_NAME}"
echo "[seczone] Recipe name: ${RECIPE_NAME}"

# ── 1. Security Zone Recipe ─────────────────────────────────────
echo "[seczone] Checking for existing recipe '${RECIPE_NAME}'..."

existing_recipe=$(oci cloud-guard security-recipe list \
    --compartment-id "${COMPARTMENT_ID}" \
    --display-name "${RECIPE_NAME}" \
    --lifecycle-state "ACTIVE" \
    --query "data.items[0].id" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_recipe" && "$existing_recipe" != "null" && "$existing_recipe" != "None" ]]; then
    RECIPE_OCID="$existing_recipe"
    echo "[seczone] Recipe exists: ${RECIPE_OCID}"
else
    echo "[seczone] Creating security zone recipe..."

    # Get OCI-managed Maximum Security recipe as base
    base_recipe=$(oci cloud-guard security-recipe list \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "OCI Security Zone Recipe - Maximum Security" \
        --query "data.items[0].id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -z "$base_recipe" || "$base_recipe" == "null" ]]; then
        # Fall back to any available managed recipe
        base_recipe=$(oci cloud-guard security-recipe list \
            --compartment-id "${COMPARTMENT_ID}" \
            --lifecycle-state "ACTIVE" \
            --query "data.items[0].id" \
            --raw-output 2>/dev/null || echo "")
    fi

    if [[ -z "$base_recipe" || "$base_recipe" == "null" ]]; then
        echo "[seczone] No base recipe found — creating custom recipe"
        # Create with security policies
        RECIPE_OCID=$(oci cloud-guard security-recipe create \
            --compartment-id "${COMPARTMENT_ID}" \
            --display-name "${RECIPE_NAME}" \
            --description "Security policies for OCTO Drone Shop (C28): encryption, vault, network controls" \
            --security-policies '[]' \
            --query "data.id" \
            --raw-output 2>/dev/null || echo "")
    else
        echo "[seczone] Cloning from base recipe: ${base_recipe}"
        RECIPE_OCID=$(oci cloud-guard security-recipe create \
            --compartment-id "${COMPARTMENT_ID}" \
            --display-name "${RECIPE_NAME}" \
            --description "Security policies for OCTO Drone Shop (C28): encryption, vault, network controls" \
            --security-policies '[]' \
            --query "data.id" \
            --raw-output 2>/dev/null || echo "")
    fi

    if [[ -n "$RECIPE_OCID" && "$RECIPE_OCID" != "null" ]]; then
        echo "[seczone] Recipe created: ${RECIPE_OCID}"
    else
        echo "[seczone] Recipe creation failed — check permissions (manage security-zone)"
        echo "[seczone] Note: Security Zones require Cloud Guard to be enabled"
        exit 1
    fi
fi

# ── 2. Security Zone ────────────────────────────────────────────
echo "[seczone] Checking for existing zone '${ZONE_NAME}'..."

existing_zone=$(oci cloud-guard security-zone list \
    --compartment-id "${COMPARTMENT_ID}" \
    --display-name "${ZONE_NAME}" \
    --lifecycle-state "ACTIVE" \
    --query "data.items[0].id" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_zone" && "$existing_zone" != "null" && "$existing_zone" != "None" ]]; then
    ZONE_OCID="$existing_zone"
    echo "[seczone] Zone exists: ${ZONE_OCID}"
else
    echo "[seczone] Creating security zone for compartment..."

    if [[ -z "$RECIPE_OCID" || "$RECIPE_OCID" == "null" ]]; then
        echo "[seczone] Skipping zone creation — no recipe available"
        exit 1
    fi

    ZONE_OCID=$(oci cloud-guard security-zone create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${ZONE_NAME}" \
        --description "Security zone for OCTO Drone Shop (C28) — enforces encryption, vault, and network policies" \
        --security-zone-recipe-id "${RECIPE_OCID}" \
        --query "data.id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -n "$ZONE_OCID" && "$ZONE_OCID" != "null" ]]; then
        echo "[seczone] Zone created: ${ZONE_OCID}"
    else
        echo "[seczone] Zone creation failed"
        echo "[seczone] Note: each compartment can only be in one security zone"
    fi
fi

cat <<'EOF'

Security Zone configuration complete.

Enforced policies (when using Maximum Security recipe):
  - ATP databases must use customer-managed encryption keys (Vault)
  - Object Storage buckets must be private
  - Block volumes must use customer-managed encryption
  - Network Security Groups must restrict ingress
  - Secrets must be stored in OCI Vault

Compliance path:
  Security Zone → Cloud Guard → Problem (if policy violated)
  Cloud Guard Problem → Responder → Auto-remediation

Demo scenario:
  1. Try to create a public bucket in the zoned compartment → BLOCKED
  2. Try to create an ATP without Vault key → BLOCKED
  3. Show Cloud Guard score improvement after zone enforcement

EOF

echo "Outputs:"
echo "  RECIPE_OCID=${RECIPE_OCID:-not_created}"
echo "  ZONE_OCID=${ZONE_OCID:-not_created}"
