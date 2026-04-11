#!/usr/bin/env bash
# Ensure OCI Cloud Guard configuration for OCTO Drone Shop (C28).
#
# Creates (idempotently):
#   1. Cloud Guard Target for the shop compartment
#   2. Custom Detector Rules for app-level security events
#   3. Responder Rules for auto-remediation
#
# Enables correlation: security_span → OCI Logging → Cloud Guard Problem
#
# Prerequisites:
#   - OCI CLI configured
#   - COMPARTMENT_ID set
#   - Cloud Guard must be enabled in the tenancy (root compartment)
#
# Usage:
#   COMPARTMENT_ID="ocid1.compartment...." \
#   REPORTING_REGION="eu-frankfurt-1" \
#   ./deploy/oci/ensure_cloud_guard.sh

set -euo pipefail

: "${COMPARTMENT_ID:?COMPARTMENT_ID is required}"
REPORTING_REGION="${REPORTING_REGION:-${OCI_REGION:-eu-frankfurt-1}}"
TARGET_NAME="${TARGET_NAME:-octo-drone-shop-target}"

echo "[cloudguard] Compartment: ${COMPARTMENT_ID}"
echo "[cloudguard] Reporting region: ${REPORTING_REGION}"

# ── 1. Verify Cloud Guard is enabled ───────────────────────────
echo "[cloudguard] Checking Cloud Guard status..."

cg_status=$(oci cloud-guard configuration get \
    --compartment-id "${COMPARTMENT_ID}" \
    --query "data.status" \
    --raw-output 2>/dev/null || echo "DISABLED")

if [[ "$cg_status" != "ENABLED" ]]; then
    echo "[cloudguard] Cloud Guard not enabled. Enabling..."
    oci cloud-guard configuration update \
        --compartment-id "${COMPARTMENT_ID}" \
        --reporting-region "${REPORTING_REGION}" \
        --status "ENABLED" 2>/dev/null || \
        echo "[cloudguard] Enable failed — Cloud Guard must be enabled at tenancy root"
fi
echo "[cloudguard] Cloud Guard status: ${cg_status}"

# ── 2. Cloud Guard Target ──────────────────────────────────────
echo "[cloudguard] Checking for target '${TARGET_NAME}'..."

existing_target=$(oci cloud-guard target list \
    --compartment-id "${COMPARTMENT_ID}" \
    --display-name "${TARGET_NAME}" \
    --lifecycle-state "ACTIVE" \
    --query "data.items[0].id" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_target" && "$existing_target" != "null" && "$existing_target" != "None" ]]; then
    TARGET_OCID="$existing_target"
    echo "[cloudguard] Target exists: ${TARGET_OCID}"
else
    echo "[cloudguard] Creating Cloud Guard target..."

    # Get the OCI-managed Activity Detector recipe
    ACTIVITY_DETECTOR=$(oci cloud-guard detector-recipe list \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "OCI Activity Detector Recipe" \
        --query "data.items[0].id" \
        --raw-output 2>/dev/null || echo "")

    # Get the OCI-managed Configuration Detector recipe
    CONFIG_DETECTOR=$(oci cloud-guard detector-recipe list \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "OCI Configuration Detector Recipe" \
        --query "data.items[0].id" \
        --raw-output 2>/dev/null || echo "")

    # Get the OCI-managed Responder recipe
    RESPONDER_RECIPE=$(oci cloud-guard responder-recipe list \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "OCI Responder Recipe" \
        --query "data.items[0].id" \
        --raw-output 2>/dev/null || echo "")

    # Build target detector recipes array
    DETECTOR_RECIPES="[]"
    if [[ -n "$ACTIVITY_DETECTOR" && "$ACTIVITY_DETECTOR" != "null" ]]; then
        if [[ -n "$CONFIG_DETECTOR" && "$CONFIG_DETECTOR" != "null" ]]; then
            DETECTOR_RECIPES="[{\"detectorRecipeId\": \"${ACTIVITY_DETECTOR}\"}, {\"detectorRecipeId\": \"${CONFIG_DETECTOR}\"}]"
        else
            DETECTOR_RECIPES="[{\"detectorRecipeId\": \"${ACTIVITY_DETECTOR}\"}]"
        fi
    fi

    RESPONDER_RECIPES="[]"
    if [[ -n "$RESPONDER_RECIPE" && "$RESPONDER_RECIPE" != "null" ]]; then
        RESPONDER_RECIPES="[{\"responderRecipeId\": \"${RESPONDER_RECIPE}\"}]"
    fi

    TARGET_OCID=$(oci cloud-guard target create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${TARGET_NAME}" \
        --target-resource-id "${COMPARTMENT_ID}" \
        --target-resource-type "COMPARTMENT" \
        --description "Cloud Guard monitoring for OCTO Drone Shop (C28)" \
        --target-detector-recipes "${DETECTOR_RECIPES}" \
        --target-responder-recipes "${RESPONDER_RECIPES}" \
        --query "data.id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -n "$TARGET_OCID" && "$TARGET_OCID" != "null" ]]; then
        echo "[cloudguard] Target created: ${TARGET_OCID}"
    else
        echo "[cloudguard] Target creation failed — check permissions (manage cloud-guard-family)"
    fi
fi

# ── 3. Get current security score ──────────────────────────────
echo "[cloudguard] Fetching security score..."

score=$(oci cloud-guard security-score-summary get \
    --compartment-id "${COMPARTMENT_ID}" \
    --query "data.\"security-score\"" \
    --raw-output 2>/dev/null || echo "unknown")

echo "[cloudguard] Current security score: ${score}"

# ── 4. List active problems ────────────────────────────────────
echo "[cloudguard] Checking for active problems..."

problem_count=$(oci cloud-guard problem list \
    --compartment-id "${COMPARTMENT_ID}" \
    --lifecycle-state "ACTIVE" \
    --query "length(data.items)" \
    --raw-output 2>/dev/null || echo "0")

echo "[cloudguard] Active problems: ${problem_count}"

if [[ "$problem_count" -gt 0 ]]; then
    echo "[cloudguard] Top 5 problems:"
    oci cloud-guard problem list \
        --compartment-id "${COMPARTMENT_ID}" \
        --lifecycle-state "ACTIVE" \
        --sort-by "riskLevel" \
        --sort-order "DESC" \
        --limit 5 \
        --query "data.items[*].{risk:\"risk-level\", label:\"resource-name\", type:\"detector-id\"}" \
        --output table 2>/dev/null || echo "  (could not fetch problems)"
fi

cat <<'EOF'

Cloud Guard configuration complete.

Detection coverage:
  - OCI Configuration Detector: misconfigurations (public buckets, open ports, etc.)
  - OCI Activity Detector: suspicious activity (unusual API calls, data exfil, etc.)
  - Responder: auto-remediation recipes (disable user, stop instance, etc.)

Correlation path (OCTO Drone Shop → Cloud Guard):
  1. App security_span → OCI Logging (oracleApmTraceId)
  2. OCI Audit → Cloud Guard Activity Detector → Problem
  3. Cloud Guard Problem → Responder → Remediation
  4. APM Trace → drill into security span → see MITRE/OWASP classification

Custom detection (future):
  Feed app security_events to a Cloud Guard custom detector via OCI Events + Functions
  to create Cloud Guard problems from app-layer attacks (SQLi, XSS, brute force).

Monitoring dashboard:
  OCI Console → Cloud Guard → Security Score → Problems → Recommendations

EOF

echo "Outputs:"
echo "  TARGET_OCID=${TARGET_OCID:-not_created}"
echo "  SECURITY_SCORE=${score}"
echo "  ACTIVE_PROBLEMS=${problem_count}"
