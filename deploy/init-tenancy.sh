#!/usr/bin/env bash
# Bootstrap a new OCI tenancy for OCTO Drone Shop + Enterprise CRM.
#
# This script is idempotent: re-running is safe and will skip resources that
# already exist. It creates:
#   1. OCIR repository (if missing)
#   2. Kubernetes namespace + imagePullSecret
#   3. Initial Kubernetes Secrets (octo-auth, octo-atp, octo-sso, octo-apm)
#      populated from env vars or prompts
#   4. (Optional) Terraform init for provisioning modules
#
# Designed to be run ONCE per new tenancy. After this succeeds, use
# ./deploy/deploy.sh for ongoing rollouts.
#
# Usage:
#   DNS_DOMAIN=tenant-a.customer.example \
#   OCIR_REGION=eu-frankfurt-1 \
#   OCIR_TENANCY=<ns> \
#   OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
#   K8S_NAMESPACE=octo-drone-shop \
#   ./deploy/init-tenancy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 0. Pre-flight ─────────────────────────────────────────────────────────
"${SCRIPT_DIR}/pre-flight-check.sh" || {
    echo "Pre-flight failed. Fix the errors above before initialization." >&2
    exit 1
}

: "${DNS_DOMAIN:?}"
: "${OCIR_REGION:?Set OCIR_REGION (e.g. eu-frankfurt-1)}"
: "${OCIR_TENANCY:?Set OCIR_TENANCY (object storage namespace)}"
: "${OCI_COMPARTMENT_ID:?Set OCI_COMPARTMENT_ID}"
: "${K8S_NAMESPACE:=octo-drone-shop}"

OCIR_REPO="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop"

echo "================================================================"
echo " New Tenancy Bootstrap — OCTO Drone Shop"
echo " DNS_DOMAIN:          ${DNS_DOMAIN}"
echo " OCIR_REPO:           ${OCIR_REPO}"
echo " OCI_COMPARTMENT_ID:  ${OCI_COMPARTMENT_ID:0:20}..."
echo " K8S_NAMESPACE:       ${K8S_NAMESPACE}"
echo "================================================================"
echo

# ── 1. Ensure OCIR repository ─────────────────────────────────────────────
echo "[1/4] Ensuring OCIR repository exists..."
if oci artifacts container repository list \
        --compartment-id "${OCI_COMPARTMENT_ID}" \
        --query "data.items[?\"display-name\"=='octo-drone-shop']" \
        --raw-output 2>/dev/null | grep -q 'octo-drone-shop'; then
    echo "      exists — skipping"
else
    oci artifacts container repository create \
        --compartment-id "${OCI_COMPARTMENT_ID}" \
        --display-name "octo-drone-shop" \
        --is-public false >/dev/null
    echo "      created"
fi

# ── 2. Ensure Kubernetes namespace ────────────────────────────────────────
echo "[2/4] Ensuring Kubernetes namespace ${K8S_NAMESPACE}..."
kubectl get namespace "${K8S_NAMESPACE}" >/dev/null 2>&1 \
    || kubectl create namespace "${K8S_NAMESPACE}"

# ── 3. Seed Kubernetes Secrets (from env or stdin) ────────────────────────
echo "[3/4] Seeding Kubernetes Secrets..."

create_secret_if_missing() {
    local name="$1"; shift
    if kubectl get secret "${name}" -n "${K8S_NAMESPACE}" >/dev/null 2>&1; then
        echo "      ${name} — exists, skipping"
        return
    fi
    kubectl create secret generic "${name}" -n "${K8S_NAMESPACE}" "$@" >/dev/null
    echo "      ${name} — created"
}

gen_secret() {
    python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
}

AUTH_TOKEN_SECRET="${AUTH_TOKEN_SECRET:-$(gen_secret)}"
INTERNAL_SERVICE_KEY="${INTERNAL_SERVICE_KEY:-$(gen_secret)}"
APP_SECRET_KEY="${APP_SECRET_KEY:-$(gen_secret)}"
BOOTSTRAP_ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-$(gen_secret)}"

create_secret_if_missing "octo-auth" \
    "--from-literal=token-secret=${AUTH_TOKEN_SECRET}" \
    "--from-literal=internal-service-key=${INTERNAL_SERVICE_KEY}" \
    "--from-literal=app-secret-key=${APP_SECRET_KEY}" \
    "--from-literal=bootstrap-admin-password=${BOOTSTRAP_ADMIN_PASSWORD}"

# ATP credentials — required for both shop + crm. Skip only if operator
# explicitly defers them.
if [[ -n "${ORACLE_DSN:-}" && -n "${ORACLE_PASSWORD:-}" ]]; then
    create_secret_if_missing "octo-atp" \
        "--from-literal=dsn=${ORACLE_DSN}" \
        "--from-literal=username=${ORACLE_USER:-ADMIN}" \
        "--from-literal=password=${ORACLE_PASSWORD}" \
        "--from-literal=wallet-password=${ORACLE_WALLET_PASSWORD:-}"
else
    echo "      octo-atp — skipped (ORACLE_DSN/ORACLE_PASSWORD not set)"
fi

# APM + RUM datakeys — collected via `terraform output` once the APM
# module provisions. Leaves empty values on first run; deploy-shop.sh
# tolerates missing keys (OTel exporter becomes a no-op).
create_secret_if_missing "octo-apm" \
    "--from-literal=apm-private-datakey=${OCI_APM_PRIVATE_DATAKEY:-}" \
    "--from-literal=apm-public-datakey=${OCI_APM_PUBLIC_DATAKEY:-}" \
    "--from-literal=apm-endpoint=${OCI_APM_ENDPOINT:-}" \
    "--from-literal=rum-endpoint=${OCI_APM_RUM_ENDPOINT:-}" \
    "--from-literal=rum-web-application-ocid=${OCI_APM_RUM_WEB_APPLICATION_OCID:-}"

# OCI Logging ingestion — log group + custom log OCIDs.
create_secret_if_missing "octo-logging" \
    "--from-literal=log-group-id=${OCI_LOG_GROUP_ID:-}" \
    "--from-literal=log-id=${OCI_LOG_ID:-}" \
    "--from-literal=log-chaos-audit-id=${OCI_LOG_GROUP_CHAOS_AUDIT:-}" \
    "--from-literal=log-security-id=${OCI_LOG_SECURITY:-}"

# IDCS / SSO — skip if tenancy hasn't configured IDCS yet.
if [[ -n "${IDCS_CLIENT_ID:-}" && -n "${IDCS_CLIENT_SECRET:-}" ]]; then
    create_secret_if_missing "octo-sso" \
        "--from-literal=idcs-client-id=${IDCS_CLIENT_ID}" \
        "--from-literal=idcs-client-secret=${IDCS_CLIENT_SECRET}" \
        "--from-literal=idcs-domain-url=${IDCS_DOMAIN_URL:-}"
else
    echo "      octo-sso — skipped (IDCS_CLIENT_ID/SECRET not set)"
fi

# GenAI endpoint + auth — optional.
create_secret_if_missing "octo-genai" \
    "--from-literal=endpoint=${OCI_GENAI_ENDPOINT:-}" \
    "--from-literal=compartment-id=${OCI_GENAI_COMPARTMENT_ID:-${OCI_COMPARTMENT_ID}}" \
    "--from-literal=model-id=${OCI_GENAI_MODEL_ID:-}"

# Integrations — Slack, Stripe, PayPal. All optional.
create_secret_if_missing "octo-integrations" \
    "--from-literal=slack-webhook-url=${SLACK_WEBHOOK_URL:-}" \
    "--from-literal=stripe-api-key=${STRIPE_API_KEY:-}" \
    "--from-literal=stripe-webhook-secret=${STRIPE_WEBHOOK_SECRET:-}" \
    "--from-literal=paypal-client-id=${PAYPAL_CLIENT_ID:-}" \
    "--from-literal=paypal-client-secret=${PAYPAL_CLIENT_SECRET:-}"

# ── 4. Terraform init (optional) ──────────────────────────────────────────
echo "[4/4] Terraform init..."
if [[ -d "${SCRIPT_DIR}/terraform" ]] && command -v terraform >/dev/null 2>&1; then
    (cd "${SCRIPT_DIR}/terraform" && terraform init -input=false)
    echo "      terraform initialized"
else
    echo "      skipped (no terraform dir or terraform CLI missing)"
fi

echo
echo "================================================================"
echo " Bootstrap complete. Next:"
echo "   1. Review/fill remaining secrets (octo-atp, octo-sso, octo-apm)"
echo "   2. Run: DNS_DOMAIN=${DNS_DOMAIN} OCIR_REPO=${OCIR_REPO} \\"
echo "          ./deploy/deploy.sh"
echo "================================================================"
