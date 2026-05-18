#!/usr/bin/env bash
# Deploy the Auto-Remediation OCI Function.
#
# Usage:
#   export COMPARTMENT_ID=ocid1.compartment...
#   export VCN_ID=ocid1.vcn...
#   export SUBNET_ID=ocid1.subnet...
#   export QUARANTINE_NSG_ID=ocid1.networksecuritygroup...
#   export OCIR_REPO=fra.ocir.io/tenancy/octo-auto-remediator
#   ./deploy/oci/deploy_auto_remediator.sh

set -euo pipefail

show_help() {
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUNC_DIR="${SCRIPT_DIR}/../../services/auto-remediator"

: "${COMPARTMENT_ID:?COMPARTMENT_ID is required}"
: "${VCN_ID:?VCN_ID is required}"
: "${SUBNET_ID:?SUBNET_ID is required}"
: "${QUARANTINE_NSG_ID:?QUARANTINE_NSG_ID is required}"
: "${OCIR_REPO:?OCIR_REPO is required}"
: "${OCI_GENAI_ENDPOINT:?OCI_GENAI_ENDPOINT is required}"
: "${OCI_GENAI_MODEL_ID:?OCI_GENAI_MODEL_ID is required}"
: "${CRM_BASE_URL:?CRM_BASE_URL is required}"

echo "Deploying Auto-Remediation Function..."

# Initialize Fn Project context if not exists
fn list contexts | grep -q "octo-apm" || fn create context octo-apm --provider oracle
fn use context octo-apm
fn update context oracle.compartment-id "${COMPARTMENT_ID}"
fn update context api-url "https://functions.${OCI_REGION:-eu-frankfurt-1}.oraclecloud.com"
fn update context registry "${OCIR_REPO}"

cd "${FUNC_DIR}"

# Create or update the application
fn create app octo-security-automation --annotation oracle.com/oci/subnetIds="[\"${SUBNET_ID}\"]" || true

# Deploy the function
fn deploy --app octo-security-automation

# Update Function Configuration
fn config function octo-security-automation auto-remediator OCI_COMPARTMENT_ID "${COMPARTMENT_ID}"
fn config function octo-security-automation auto-remediator QUARANTINE_NSG_ID "${QUARANTINE_NSG_ID}"
fn config function octo-security-automation auto-remediator OCI_GENAI_ENDPOINT "${OCI_GENAI_ENDPOINT}"
fn config function octo-security-automation auto-remediator OCI_GENAI_MODEL_ID "${OCI_GENAI_MODEL_ID}"
fn config function octo-security-automation auto-remediator CRM_BASE_URL "${CRM_BASE_URL}"
fn config function octo-security-automation auto-remediator OTEL_SERVICE_NAME "${OTEL_SERVICE_NAME:-octo-auto-remediator}"
if [[ -n "${OCI_APM_ENDPOINT:-}" ]]; then
  fn config function octo-security-automation auto-remediator OCI_APM_ENDPOINT "${OCI_APM_ENDPOINT}"
fi
if [[ -n "${OCI_APM_PRIVATE_DATAKEY:-}" ]]; then
  fn config function octo-security-automation auto-remediator OCI_APM_PRIVATE_DATAKEY "${OCI_APM_PRIVATE_DATAKEY}"
fi

echo "Auto-Remediation Function Deployed Successfully."
