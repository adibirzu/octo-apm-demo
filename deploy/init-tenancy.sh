#!/usr/bin/env bash
# Bootstrap a new OCI tenancy for the unified OCTO Drone Shop + CRM stack.
#
# This script is idempotent: re-running is safe and will skip resources that
# already exist. It creates:
#   1. OCIR repositories for shop + CRM (+ optional java demo)
#   2. Kubernetes namespaces for both services
#   3. Initial shared Kubernetes secrets in both namespaces
#   4. Optional Terraform init for the unified root stack
#
# Designed to be run ONCE per tenancy. After this succeeds, use
# ./deploy/deploy.sh for ongoing rollouts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${DNS_DOMAIN:?Set DNS_DOMAIN (for DEFAULT/oci4cca use cyber-sec.ro)}"
: "${OCIR_REGION:?Set OCIR_REGION (for example eu-frankfurt-1)}"
: "${OCIR_TENANCY:?Set OCIR_TENANCY (object storage namespace)}"
: "${OCI_COMPARTMENT_ID:?Set OCI_COMPARTMENT_ID}"
: "${K8S_NAMESPACE_SHOP:=octo-drone-shop}"
: "${K8S_NAMESPACE_CRM:=enterprise-crm}"

SHOP_OCIR_REPO="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop"
CRM_OCIR_REPO="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal"

# Keep the older pre-flight contract working while this script exposes
# the unified env surface.
export OCIR_REPO="${OCIR_REPO:-${SHOP_OCIR_REPO}}"
export K8S_NAMESPACE="${K8S_NAMESPACE:-${K8S_NAMESPACE_SHOP}}"

# ── 0. Pre-flight ─────────────────────────────────────────────────────────
"${SCRIPT_DIR}/pre-flight-check.sh" || {
    echo "Pre-flight failed. Fix the errors above before initialization." >&2
    exit 1
}

echo "================================================================"
echo " Unified Tenancy Bootstrap — OCTO APM Demo"
echo " DNS_DOMAIN:           ${DNS_DOMAIN}"
echo " Shop OCIR repo:       ${SHOP_OCIR_REPO}"
echo " CRM OCIR repo:        ${CRM_OCIR_REPO}"
echo " OCI_COMPARTMENT_ID:   ${OCI_COMPARTMENT_ID:0:20}..."
echo " Shop namespace:       ${K8S_NAMESPACE_SHOP}"
echo " CRM namespace:        ${K8S_NAMESPACE_CRM}"
echo "================================================================"
echo

ensure_repo() {
    local repo_name="$1"
    local create_output
    if create_output="$(
        oci artifacts container repository create \
            --compartment-id "${OCI_COMPARTMENT_ID}" \
            --display-name "${repo_name}" \
            --is-public false 2>&1
    )"; then
        echo "      ${repo_name} — created"
        return
    fi

    if echo "${create_output}" | grep -Eq 'NAMESPACE_CONFLICT|Repository already exists'; then
        echo "      ${repo_name} — exists, skipping"
        return
    fi

    echo "${create_output}" >&2
    return 1
}

create_secret_if_missing() {
    local namespace="$1"
    local name="$2"
    shift 2
    if kubectl get secret "${name}" -n "${namespace}" >/dev/null 2>&1; then
        echo "      ${namespace}/${name} — exists, skipping"
        return
    fi
    kubectl create secret generic "${name}" -n "${namespace}" "$@" >/dev/null
    echo "      ${namespace}/${name} — created"
}

apply_secret_to_all_namespaces() {
    local name="$1"
    shift
    local namespace
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        create_secret_if_missing "${namespace}" "${name}" "$@"
    done
}

gen_secret() {
    python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
}

# ── 1. Ensure OCIR repositories ───────────────────────────────────────────
echo "[1/4] Ensuring OCIR repositories exist..."
for repo in octo-drone-shop enterprise-crm-portal octo-apm-java-demo; do
    ensure_repo "${repo}"
done

# ── 2. Ensure Kubernetes namespaces ───────────────────────────────────────
echo "[2/4] Ensuring Kubernetes namespaces exist..."
for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
    kubectl get namespace "${namespace}" >/dev/null 2>&1 || kubectl create namespace "${namespace}"
done

# ── 3. Seed shared Kubernetes secrets ─────────────────────────────────────
echo "[3/4] Seeding shared Kubernetes secrets..."

AUTH_TOKEN_SECRET="${AUTH_TOKEN_SECRET:-$(gen_secret)}"
INTERNAL_SERVICE_KEY="${INTERNAL_SERVICE_KEY:-$(gen_secret)}"
APP_SECRET_KEY="${APP_SECRET_KEY:-$(gen_secret)}"
BOOTSTRAP_ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-$(gen_secret)}"

apply_secret_to_all_namespaces "octo-auth" \
    "--from-literal=token-secret=${AUTH_TOKEN_SECRET}" \
    "--from-literal=internal-service-key=${INTERNAL_SERVICE_KEY}" \
    "--from-literal=app-secret-key=${APP_SECRET_KEY}" \
    "--from-literal=bootstrap-admin-password=${BOOTSTRAP_ADMIN_PASSWORD}"

if [[ -n "${ORACLE_DSN:-}" && -n "${ORACLE_PASSWORD:-}" ]]; then
    apply_secret_to_all_namespaces "octo-atp" \
        "--from-literal=dsn=${ORACLE_DSN}" \
        "--from-literal=username=${ORACLE_USER:-ADMIN}" \
        "--from-literal=password=${ORACLE_PASSWORD}" \
        "--from-literal=wallet-password=${ORACLE_WALLET_PASSWORD:-}"
else
    echo "      octo-atp — skipped in both namespaces (ORACLE_DSN/ORACLE_PASSWORD not set)"
fi

apply_secret_to_all_namespaces "octo-apm" \
    "--from-literal=private-key=${OCI_APM_PRIVATE_DATAKEY:-}" \
    "--from-literal=public-key=${OCI_APM_PUBLIC_DATAKEY:-}" \
    "--from-literal=endpoint=${OCI_APM_ENDPOINT:-}" \
    "--from-literal=rum-endpoint=${OCI_APM_RUM_ENDPOINT:-}" \
    "--from-literal=rum-web-application-ocid=${OCI_APM_RUM_WEB_APPLICATION_OCID:-}"

apply_secret_to_all_namespaces "octo-logging" \
    "--from-literal=log-group-id=${OCI_LOG_GROUP_ID:-}" \
    "--from-literal=log-id=${OCI_LOG_ID:-}" \
    "--from-literal=log-chaos-audit-id=${OCI_LOG_GROUP_CHAOS_AUDIT:-}" \
    "--from-literal=log-security-id=${OCI_LOG_SECURITY:-}"

if [[ -n "${IDCS_CLIENT_ID:-}" && -n "${IDCS_CLIENT_SECRET:-}" ]]; then
    create_secret_if_missing "${K8S_NAMESPACE_SHOP}" "octo-sso" \
        "--from-literal=idcs-client-id=${IDCS_CLIENT_ID}" \
        "--from-literal=idcs-client-secret=${IDCS_CLIENT_SECRET}" \
        "--from-literal=idcs-domain-url=${IDCS_DOMAIN_URL:-}" \
        "--from-literal=idcs-redirect-uri=${SHOP_IDCS_REDIRECT_URI:-https://shop.${DNS_DOMAIN}/api/auth/sso/callback}" \
        "--from-literal=idcs-post-logout-redirect=${SHOP_IDCS_POST_LOGOUT_REDIRECT:-https://shop.${DNS_DOMAIN}/login}"
    create_secret_if_missing "${K8S_NAMESPACE_CRM}" "octo-sso" \
        "--from-literal=idcs-client-id=${IDCS_CLIENT_ID}" \
        "--from-literal=idcs-client-secret=${IDCS_CLIENT_SECRET}" \
        "--from-literal=idcs-domain-url=${IDCS_DOMAIN_URL:-}" \
        "--from-literal=idcs-redirect-uri=${CRM_IDCS_REDIRECT_URI:-https://crm.${DNS_DOMAIN}/api/auth/sso/callback}" \
        "--from-literal=idcs-post-logout-redirect=${CRM_IDCS_POST_LOGOUT_REDIRECT:-https://crm.${DNS_DOMAIN}/login}"
else
    echo "      octo-sso — skipped in both namespaces (IDCS_CLIENT_ID/SECRET not set)"
fi

apply_secret_to_all_namespaces "octo-genai" \
    "--from-literal=endpoint=${OCI_GENAI_ENDPOINT:-}" \
    "--from-literal=compartment-id=${OCI_GENAI_COMPARTMENT_ID:-${OCI_COMPARTMENT_ID}}" \
    "--from-literal=model-id=${OCI_GENAI_MODEL_ID:-}" \
    "--from-literal=selectai-profile-name=${SELECTAI_PROFILE_NAME:-}"

apply_secret_to_all_namespaces "octo-oci-config" \
    "--from-literal=compartment-id=${OCI_COMPARTMENT_ID}" \
    "--from-literal=genai-endpoint=${OCI_GENAI_ENDPOINT:-}" \
    "--from-literal=genai-model-id=${OCI_GENAI_MODEL_ID:-}"

apply_secret_to_all_namespaces "octo-integrations" \
    "--from-literal=crm-url=${CRM_PUBLIC_URL:-https://crm.${DNS_DOMAIN}}" \
    "--from-literal=shop-url=${SHOP_PUBLIC_URL:-https://shop.${DNS_DOMAIN}}" \
    "--from-literal=workflow-api-base-url=${WORKFLOW_API_BASE_URL:-}" \
    "--from-literal=workflow-public-api-base-url=${WORKFLOW_PUBLIC_API_BASE_URL:-}" \
    "--from-literal=apm-console-url=${APM_CONSOLE_URL:-}" \
    "--from-literal=opsi-console-url=${OPSI_CONSOLE_URL:-}" \
    "--from-literal=db-management-console-url=${DB_MANAGEMENT_CONSOLE_URL:-}" \
    "--from-literal=log-analytics-console-url=${LOG_ANALYTICS_CONSOLE_URL:-}" \
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
echo "   1. Fill or refresh optional secrets (octo-apm, octo-sso, octo-integrations)"
echo "   2. Run:"
echo "      OCIR_REGION=${OCIR_REGION} OCIR_TENANCY=${OCIR_TENANCY} DNS_DOMAIN=${DNS_DOMAIN} \\"
echo "      ./deploy/deploy.sh"
echo "================================================================"
