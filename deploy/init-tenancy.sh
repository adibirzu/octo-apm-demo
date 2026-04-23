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

get_secret_value() {
    local namespace="$1"
    local name="$2"
    local key="$3"
    kubectl get secret "${name}" -n "${namespace}" -o json 2>/dev/null | \
        python3 -c '
import base64, json, sys
try:
    data = json.load(sys.stdin).get("data", {})
    value = data.get(sys.argv[1], "")
    print(base64.b64decode(value).decode("utf-8") if value else "", end="")
except Exception:
    pass
' "${key}" 2>/dev/null || true
}

first_nonempty_secret_value() {
    local name="$1"
    local key="$2"
    local namespace
    local value
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        value="$(get_secret_value "${namespace}" "${name}" "${key}")"
        if [[ -n "${value}" ]]; then
            printf '%s' "${value}"
            return 0
        fi
    done
    return 1
}

first_nonempty_secret_value_or_blank() {
    first_nonempty_secret_value "$@" || true
}

apply_literal_secret() {
    local namespace="$1"
    local name="$2"
    shift 2
    local -a args=()
    local pair key value
    for pair in "$@"; do
        key="${pair%%=*}"
        value="${pair#*=}"
        [[ -n "${value}" ]] || continue
        args+=(--from-literal="${key}=${value}")
    done
    if [[ "${#args[@]}" -eq 0 ]]; then
        echo "      ${namespace}/${name} — skipped (no non-empty values)"
        return
    fi
    kubectl -n "${namespace}" create secret generic "${name}" "${args[@]}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    echo "      ${namespace}/${name} — applied"
}

apply_literal_secret_all_namespaces() {
    local name="$1"
    shift
    local namespace
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        apply_literal_secret "${namespace}" "${name}" "$@"
    done
}

resolve_ocir_pull_credentials() {
    if [[ -n "${OCIR_USERNAME:-}" && -n "${OCIR_AUTH_TOKEN:-}" ]]; then
        return 0
    fi
    [[ -f "${HOME}/.docker/config.json" ]] || return 1
    local parsed
    parsed="$(
        OCIR_REGION="${OCIR_REGION}" python3 - <<'PYEOF'
import base64
import json
import os
import pathlib
import sys

path = pathlib.Path.home() / ".docker" / "config.json"
data = json.loads(path.read_text())
server = f"{os.environ['OCIR_REGION']}.ocir.io"
entry = (data.get("auths") or {}).get(server) or {}
auth = entry.get("auth")
if not auth:
    sys.exit(1)
username, password = base64.b64decode(auth).decode().split(":", 1)
print(f"{username}\t{password}")
PYEOF
    )" || return 1
    IFS=$'\t' read -r OCIR_USERNAME OCIR_AUTH_TOKEN <<< "${parsed}"
    export OCIR_USERNAME OCIR_AUTH_TOKEN
    return 0
}

apply_ocir_pull_secret() {
    local namespace="$1"
    kubectl -n "${namespace}" create secret docker-registry ocir-pull-secret \
        --docker-server="${OCIR_REGION}.ocir.io" \
        --docker-username="${OCIR_USERNAME}" \
        --docker-password="${OCIR_AUTH_TOKEN}" \
        --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    echo "      ${namespace}/ocir-pull-secret — applied"
}

sync_secret_from_first_existing() {
    local name="$1"
    local source_namespace=""
    local namespace
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        if kubectl get secret "${name}" -n "${namespace}" >/dev/null 2>&1; then
            source_namespace="${namespace}"
            break
        fi
    done
    [[ -n "${source_namespace}" ]] || return 1

    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        kubectl get secret "${name}" -n "${source_namespace}" -o json | \
            python3 -c '
import json
import sys
import yaml

doc = json.load(sys.stdin)
doc["metadata"] = {
    "name": doc["metadata"]["name"],
    "namespace": sys.argv[1],
}
print(yaml.safe_dump(doc, sort_keys=False))
' "${namespace}" | kubectl apply -f - >/dev/null
        echo "      ${namespace}/${name} — synced from ${source_namespace}"
    done
}

resolve_wallet_dir() {
    if [[ -n "${ORACLE_WALLET_DIR:-}" ]]; then
        [[ -d "${ORACLE_WALLET_DIR}" ]] || {
            echo "ORACLE_WALLET_DIR does not exist: ${ORACLE_WALLET_DIR}" >&2
            return 1
        }
        printf '%s' "${ORACLE_WALLET_DIR}"
        return 0
    fi

    local temp_dir wallet_zip
    temp_dir="$(mktemp -d)"
    if [[ -n "${ORACLE_WALLET_ZIP:-}" ]]; then
        [[ -f "${ORACLE_WALLET_ZIP}" ]] || {
            echo "ORACLE_WALLET_ZIP does not exist: ${ORACLE_WALLET_ZIP}" >&2
            rm -rf "${temp_dir}"
            return 1
        }
        wallet_zip="${ORACLE_WALLET_ZIP}"
    elif [[ -n "${ORACLE_WALLET_ZIP_B64:-}" ]]; then
        wallet_zip="${temp_dir}/wallet.zip"
        printf '%s' "${ORACLE_WALLET_ZIP_B64}" | python3 -c "import base64,sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))" > "${wallet_zip}"
    else
        rm -rf "${temp_dir}"
        return 1
    fi

    unzip -q "${wallet_zip}" -d "${temp_dir}"
    printf '%s' "${temp_dir}"
}

apply_wallet_secret_all_namespaces() {
    local wallet_dir="$1"
    local namespace
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        kubectl -n "${namespace}" create secret generic octo-atp-wallet \
            --from-file="${wallet_dir}" \
            --dry-run=client -o yaml | kubectl apply -f - >/dev/null
        echo "      ${namespace}/octo-atp-wallet — applied"
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

AUTH_TOKEN_SECRET="${AUTH_TOKEN_SECRET:-$(first_nonempty_secret_value_or_blank octo-auth token-secret)}"
INTERNAL_SERVICE_KEY="${INTERNAL_SERVICE_KEY:-$(first_nonempty_secret_value_or_blank octo-auth internal-service-key)}"
APP_SECRET_KEY="${APP_SECRET_KEY:-$(first_nonempty_secret_value_or_blank octo-auth app-secret-key)}"
BOOTSTRAP_ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-$(first_nonempty_secret_value_or_blank octo-auth bootstrap-admin-password)}"
[[ -n "${AUTH_TOKEN_SECRET}" ]] || AUTH_TOKEN_SECRET="$(gen_secret)"
[[ -n "${INTERNAL_SERVICE_KEY}" ]] || INTERNAL_SERVICE_KEY="$(gen_secret)"
[[ -n "${APP_SECRET_KEY}" ]] || APP_SECRET_KEY="$(gen_secret)"
[[ -n "${BOOTSTRAP_ADMIN_PASSWORD}" ]] || BOOTSTRAP_ADMIN_PASSWORD="$(gen_secret)"

if resolve_ocir_pull_credentials; then
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        apply_ocir_pull_secret "${namespace}"
    done
else
    echo "      ocir-pull-secret — skipped (set OCIR_USERNAME/OCIR_AUTH_TOKEN or docker login ${OCIR_REGION}.ocir.io first)"
fi

apply_literal_secret_all_namespaces "octo-auth" \
    "token-secret=${AUTH_TOKEN_SECRET}" \
    "internal-service-key=${INTERNAL_SERVICE_KEY}" \
    "app-secret-key=${APP_SECRET_KEY}" \
    "bootstrap-admin-password=${BOOTSTRAP_ADMIN_PASSWORD}"

ORACLE_DSN="${ORACLE_DSN:-$(first_nonempty_secret_value_or_blank octo-atp dsn)}"
ORACLE_USER="${ORACLE_USER:-$(first_nonempty_secret_value_or_blank octo-atp username)}"
ORACLE_PASSWORD="${ORACLE_PASSWORD:-$(first_nonempty_secret_value_or_blank octo-atp password)}"
ORACLE_WALLET_PASSWORD="${ORACLE_WALLET_PASSWORD:-$(first_nonempty_secret_value_or_blank octo-atp wallet-password)}"
if [[ -n "${ORACLE_DSN:-}" && -n "${ORACLE_PASSWORD:-}" ]]; then
    apply_literal_secret_all_namespaces "octo-atp" \
        "dsn=${ORACLE_DSN}" \
        "username=${ORACLE_USER:-ADMIN}" \
        "password=${ORACLE_PASSWORD}" \
        "wallet-password=${ORACLE_WALLET_PASSWORD:-}"
else
    echo "      octo-atp — skipped in both namespaces (ORACLE_DSN/ORACLE_PASSWORD not set)"
fi

wallet_dir=""
if wallet_dir="$(resolve_wallet_dir)"; then
    apply_wallet_secret_all_namespaces "${wallet_dir}"
    if [[ "${wallet_dir}" != "${ORACLE_WALLET_DIR:-}" ]]; then
        rm -rf "${wallet_dir}"
    fi
elif sync_secret_from_first_existing octo-atp-wallet; then
    :
else
    echo "      octo-atp-wallet — skipped in both namespaces (set ORACLE_WALLET_DIR, ORACLE_WALLET_ZIP, or ORACLE_WALLET_ZIP_B64)"
fi

OCI_APM_PRIVATE_DATAKEY="${OCI_APM_PRIVATE_DATAKEY:-$(first_nonempty_secret_value_or_blank octo-apm private-key)}"
OCI_APM_PUBLIC_DATAKEY="${OCI_APM_PUBLIC_DATAKEY:-$(first_nonempty_secret_value_or_blank octo-apm public-key)}"
OCI_APM_ENDPOINT="${OCI_APM_ENDPOINT:-$(first_nonempty_secret_value_or_blank octo-apm endpoint)}"
OCI_APM_RUM_ENDPOINT="${OCI_APM_RUM_ENDPOINT:-$(first_nonempty_secret_value_or_blank octo-apm rum-endpoint)}"
OCI_APM_RUM_WEB_APPLICATION_OCID="${OCI_APM_RUM_WEB_APPLICATION_OCID:-$(first_nonempty_secret_value_or_blank octo-apm rum-web-application-ocid)}"
apply_literal_secret_all_namespaces "octo-apm" \
    "private-key=${OCI_APM_PRIVATE_DATAKEY:-}" \
    "public-key=${OCI_APM_PUBLIC_DATAKEY:-}" \
    "endpoint=${OCI_APM_ENDPOINT:-}" \
    "rum-endpoint=${OCI_APM_RUM_ENDPOINT:-}" \
    "rum-web-application-ocid=${OCI_APM_RUM_WEB_APPLICATION_OCID:-}"

OCI_LOG_GROUP_ID="${OCI_LOG_GROUP_ID:-$(first_nonempty_secret_value_or_blank octo-logging log-group-id)}"
OCI_LOG_ID="${OCI_LOG_ID:-$(first_nonempty_secret_value_or_blank octo-logging log-id)}"
OCI_LOG_CHAOS_AUDIT_ID="${OCI_LOG_CHAOS_AUDIT_ID:-${OCI_LOG_GROUP_CHAOS_AUDIT:-$(first_nonempty_secret_value_or_blank octo-logging log-chaos-audit-id)}}"
OCI_LOG_SECURITY_ID="${OCI_LOG_SECURITY_ID:-${OCI_LOG_SECURITY:-$(first_nonempty_secret_value_or_blank octo-logging log-security-id)}}"
SPLUNK_HEC_URL="${SPLUNK_HEC_URL:-$(first_nonempty_secret_value_or_blank octo-logging splunk-hec-url)}"
SPLUNK_HEC_TOKEN="${SPLUNK_HEC_TOKEN:-$(first_nonempty_secret_value_or_blank octo-logging splunk-hec-token)}"
apply_literal_secret_all_namespaces "octo-logging" \
    "log-group-id=${OCI_LOG_GROUP_ID:-}" \
    "log-id=${OCI_LOG_ID:-}" \
    "log-chaos-audit-id=${OCI_LOG_CHAOS_AUDIT_ID:-}" \
    "log-security-id=${OCI_LOG_SECURITY_ID:-}" \
    "splunk-hec-url=${SPLUNK_HEC_URL:-}" \
    "splunk-hec-token=${SPLUNK_HEC_TOKEN:-}"

if [[ -n "${IDCS_CLIENT_ID:-}" && -n "${IDCS_CLIENT_SECRET:-}" ]]; then
    apply_literal_secret "${K8S_NAMESPACE_SHOP}" "octo-sso" \
        "idcs-client-id=${IDCS_CLIENT_ID}" \
        "idcs-client-secret=${IDCS_CLIENT_SECRET}" \
        "idcs-domain-url=${IDCS_DOMAIN_URL:-}" \
        "idcs-redirect-uri=${SHOP_IDCS_REDIRECT_URI:-https://shop.${DNS_DOMAIN}/api/auth/sso/callback}" \
        "idcs-post-logout-redirect=${SHOP_IDCS_POST_LOGOUT_REDIRECT:-https://shop.${DNS_DOMAIN}/login}"
    apply_literal_secret "${K8S_NAMESPACE_CRM}" "octo-sso" \
        "idcs-client-id=${IDCS_CLIENT_ID}" \
        "idcs-client-secret=${IDCS_CLIENT_SECRET}" \
        "idcs-domain-url=${IDCS_DOMAIN_URL:-}" \
        "idcs-redirect-uri=${CRM_IDCS_REDIRECT_URI:-https://crm.${DNS_DOMAIN}/api/auth/sso/callback}" \
        "idcs-post-logout-redirect=${CRM_IDCS_POST_LOGOUT_REDIRECT:-https://crm.${DNS_DOMAIN}/login}"
else
    echo "      octo-sso — skipped in both namespaces (IDCS_CLIENT_ID/SECRET not set)"
fi

OCI_GENAI_ENDPOINT="${OCI_GENAI_ENDPOINT:-$(first_nonempty_secret_value_or_blank octo-genai endpoint)}"
OCI_GENAI_COMPARTMENT_ID="${OCI_GENAI_COMPARTMENT_ID:-$(first_nonempty_secret_value_or_blank octo-genai compartment-id)}"
OCI_GENAI_MODEL_ID="${OCI_GENAI_MODEL_ID:-$(first_nonempty_secret_value_or_blank octo-genai model-id)}"
SELECTAI_PROFILE_NAME="${SELECTAI_PROFILE_NAME:-$(first_nonempty_secret_value_or_blank octo-genai selectai-profile-name)}"
apply_literal_secret_all_namespaces "octo-genai" \
    "endpoint=${OCI_GENAI_ENDPOINT:-}" \
    "compartment-id=${OCI_GENAI_COMPARTMENT_ID:-${OCI_COMPARTMENT_ID}}" \
    "model-id=${OCI_GENAI_MODEL_ID:-}" \
    "selectai-profile-name=${SELECTAI_PROFILE_NAME:-}"

apply_literal_secret_all_namespaces "octo-oci-config" \
    "compartment-id=${OCI_COMPARTMENT_ID}" \
    "genai-endpoint=${OCI_GENAI_ENDPOINT:-}" \
    "genai-model-id=${OCI_GENAI_MODEL_ID:-}"

WORKFLOW_API_BASE_URL="${WORKFLOW_API_BASE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations workflow-api-base-url)}"
WORKFLOW_PUBLIC_API_BASE_URL="${WORKFLOW_PUBLIC_API_BASE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations workflow-public-api-base-url)}"
APM_CONSOLE_URL="${APM_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations apm-console-url)}"
OPSI_CONSOLE_URL="${OPSI_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations opsi-console-url)}"
DB_MANAGEMENT_CONSOLE_URL="${DB_MANAGEMENT_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations db-management-console-url)}"
LOG_ANALYTICS_CONSOLE_URL="${LOG_ANALYTICS_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations log-analytics-console-url)}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-$(first_nonempty_secret_value_or_blank octo-integrations slack-webhook-url)}"
STRIPE_API_KEY="${STRIPE_API_KEY:-$(first_nonempty_secret_value_or_blank octo-integrations stripe-api-key)}"
STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-$(first_nonempty_secret_value_or_blank octo-integrations stripe-webhook-secret)}"
PAYPAL_CLIENT_ID="${PAYPAL_CLIENT_ID:-$(first_nonempty_secret_value_or_blank octo-integrations paypal-client-id)}"
PAYPAL_CLIENT_SECRET="${PAYPAL_CLIENT_SECRET:-$(first_nonempty_secret_value_or_blank octo-integrations paypal-client-secret)}"
apply_literal_secret_all_namespaces "octo-integrations" \
    "crm-url=${CRM_PUBLIC_URL:-https://crm.${DNS_DOMAIN}}" \
    "shop-url=${SHOP_PUBLIC_URL:-https://shop.${DNS_DOMAIN}}" \
    "workflow-api-base-url=${WORKFLOW_API_BASE_URL:-}" \
    "workflow-public-api-base-url=${WORKFLOW_PUBLIC_API_BASE_URL:-}" \
    "apm-console-url=${APM_CONSOLE_URL:-}" \
    "opsi-console-url=${OPSI_CONSOLE_URL:-}" \
    "db-management-console-url=${DB_MANAGEMENT_CONSOLE_URL:-}" \
    "log-analytics-console-url=${LOG_ANALYTICS_CONSOLE_URL:-}" \
    "slack-webhook-url=${SLACK_WEBHOOK_URL:-}" \
    "stripe-api-key=${STRIPE_API_KEY:-}" \
    "stripe-webhook-secret=${STRIPE_WEBHOOK_SECRET:-}" \
    "paypal-client-id=${PAYPAL_CLIENT_ID:-}" \
    "paypal-client-secret=${PAYPAL_CLIENT_SECRET:-}"

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
