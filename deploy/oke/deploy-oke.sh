#!/usr/bin/env bash
# Apply the OKE manifests for octo-apm-demo.
#
# Order matters:
#   1. Namespaces
#   2. Secrets (bootstrapped by deploy/init-tenancy.sh into each ns)
#   3. SecretProviderClass (if OCI Vault CSI is installed)
#   4. Java payment gateway/app-server and workflow gateway Deployments
#   5. Shop/CRM Deployments + Services + LB + HPA + PDB
#   6. NetworkPolicies (last — otherwise they race with Service creation)
#
# Usage:
#   DNS_DOMAIN=example.test \
#   OCIR_REGION=eu-frankfurt-1 \
#   OCIR_TENANCY=<namespace> \
#   IMAGE_TAG=<immutable-image-tag> \
#   ./deploy/oke/deploy-oke.sh

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OKE_DIR="${REPO_ROOT}/k8s/oke"

: "${DNS_DOMAIN:?Set DNS_DOMAIN (for DEFAULT/<OCI_PROFILE> use example.test)}"
: "${OCIR_REGION:?Set OCIR_REGION}"
: "${OCI_REGION:=${OCI_CLI_REGION:-${OCI_REGION_ID:-us-phoenix-1}}}"
: "${OCIR_TENANCY:?Set OCIR_TENANCY}"
: "${IMAGE_TAG:?Set IMAGE_TAG to an immutable tag, for example oke-$(date -u +%Y%m%d%H%M%S)}"
: "${K8S_NAMESPACE_SHOP:=octo-drone-shop}"
: "${K8S_NAMESPACE_CRM:=enterprise-crm}"
: "${OKE_CLUSTER_NAME:=octo-apm-demo-oke}"
: "${OKE_EXTERNAL_INGRESS_CIDR:=10.42.0.0/16}"
: "${ALLOW_LATEST_IMAGE_TAG:=false}"
: "${ALLOW_MISSING_SECRETS:=false}"
: "${SKIP_CONTEXT_CHECK:=false}"
: "${SERVER_DRY_RUN:=true}"
: "${APPLY:=true}"

export DNS_DOMAIN OCIR_REGION OCIR_TENANCY IMAGE_TAG \
    K8S_NAMESPACE_SHOP K8S_NAMESPACE_CRM OKE_CLUSTER_NAME \
    OKE_EXTERNAL_INGRESS_CIDR OCI_REGION

require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}

require_tool kubectl
require_tool envsubst

if [[ "${IMAGE_TAG}" == "latest" && "${ALLOW_LATEST_IMAGE_TAG}" != "true" ]]; then
    echo "Refusing to deploy mutable image tag 'latest'. Set IMAGE_TAG to the tested immutable tag, or ALLOW_LATEST_IMAGE_TAG=true for a manual exception." >&2
    exit 1
fi

if [[ "${SKIP_CONTEXT_CHECK}" != "true" ]]; then
    current_context="$(kubectl config current-context 2>/dev/null || true)"
    if [[ "${current_context}" != "${OKE_CLUSTER_NAME}" ]]; then
        echo "Current kubectl context is '${current_context:-unset}', expected '${OKE_CLUSTER_NAME}'." >&2
        echo "Run deploy/oke/create-emdemo-small-cluster.sh or set SKIP_CONTEXT_CHECK=true after verifying the target cluster." >&2
        exit 1
    fi
fi

apply_manifest() {
    local manifest="$1"
    if [[ "${SERVER_DRY_RUN}" == "true" ]]; then
        envsubst < "${manifest}" | kubectl apply --dry-run=server -f - >/dev/null
    fi
    if [[ "${APPLY}" != "true" ]]; then
        echo "  DRY RUN only: ${manifest}"
        return
    fi
    envsubst < "${manifest}" | kubectl apply -f -
}

require_secret() {
    local namespace="$1"
    local secret="$2"
    if kubectl get secret "${secret}" -n "${namespace}" >/dev/null 2>&1; then
        echo "  ${namespace}/${secret} OK"
        return 0
    fi
    echo "  Missing required Secret ${secret} in ${namespace}" >&2
    return 1
}

optional_secret() {
    local namespace="$1"
    local secret="$2"
    if kubectl get secret "${secret}" -n "${namespace}" >/dev/null 2>&1; then
        echo "  ${namespace}/${secret} OK"
    else
        echo "  Optional Secret ${secret} not found in ${namespace}"
    fi
}

has_secret_provider_inputs() {
    local required=(
        OCI_VAULT_OCID OCI_REGION
        VAULT_SECRET_OCID_AUTH_TOKEN
        VAULT_SECRET_OCID_INTERNAL_SERVICE_KEY
        VAULT_SECRET_OCID_APP_SECRET_KEY
        VAULT_SECRET_OCID_BOOTSTRAP_ADMIN
        VAULT_SECRET_OCID_ORACLE_DSN
        VAULT_SECRET_OCID_ORACLE_USERNAME
        VAULT_SECRET_OCID_ORACLE_PASSWORD
        VAULT_SECRET_OCID_ORACLE_WALLET_PASSWORD
        VAULT_SECRET_OCID_IDCS_CLIENT_SECRET
        VAULT_SECRET_OCID_APM_PRIVATE_DATAKEY
        VAULT_SECRET_OCID_APM_PUBLIC_DATAKEY
    )
    local name
    for name in "${required[@]}"; do
        if [[ -z "${!name:-}" ]]; then
            return 1
        fi
    done
    return 0
}

echo "================================================================"
echo " OKE deploy — octo-apm-demo"
echo "   DNS_DOMAIN:          ${DNS_DOMAIN}"
echo "   Shop namespace:      ${K8S_NAMESPACE_SHOP}"
echo "   CRM namespace:       ${K8S_NAMESPACE_CRM}"
echo "   OKE cluster:         ${OKE_CLUSTER_NAME}"
echo "   External ingress:    ${OKE_EXTERNAL_INGRESS_CIDR}"
echo "   Shop URL:            https://drones.${DNS_DOMAIN}"
echo "   CRM URL:             https://admin.${DNS_DOMAIN}"
echo "   OCIR:                ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}"
echo "   OCI region:          ${OCI_REGION}"
echo "   IMAGE_TAG:           ${IMAGE_TAG}"
echo "   APPLY:               ${APPLY}"
echo "================================================================"

echo
echo "[1/6] Applying namespaces..."
apply_manifest "${OKE_DIR}/common/namespaces.yaml"

echo
echo "[2/6] Checking bootstrap Secrets..."
missing_required_secret=false
for ns in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
    for sec in octo-auth octo-atp octo-atp-wallet octo-oci-config octo-apm octo-logging ocir-pull-secret; do
        require_secret "${ns}" "${sec}" || missing_required_secret=true
    done
    optional_secret "${ns}" octo-sso
    optional_secret "${ns}" octo-llmetry
done
if [[ "${missing_required_secret}" == "true" && "${ALLOW_MISSING_SECRETS}" != "true" ]]; then
    echo "Required Secrets are missing. Run deploy/oke/bootstrap-emdemo-secrets.sh, then retry." >&2
    echo "Set ALLOW_MISSING_SECRETS=true only for manifest-only validation." >&2
    exit 1
fi

echo
echo "[3/6] Applying SecretProviderClass (optional; needs OCI Vault CSI driver and Vault OCIDs)..."
if kubectl get crd secretproviderclasses.secrets-store.csi.x-k8s.io >/dev/null 2>&1; then
    if has_secret_provider_inputs; then
        for ns in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
            export NAMESPACE="${ns}"
            apply_manifest "${OKE_DIR}/common/secret-provider-class.yaml"
        done
        unset NAMESPACE
    else
        echo "  ⊘ Secrets Store CSI CRD exists, but Vault OCID env vars are incomplete. Keeping Kubernetes Secrets as the active source."
    fi
else
    echo "  ⊘ OCI Secrets Store CSI driver not installed — skipping. Using Kubernetes Secrets instead."
fi

echo
echo "[4/6] Applying Java payment gateway/app-server and workflow gateway..."
apply_manifest "${OKE_DIR}/apm-java-demo/deployment.yaml"
apply_manifest "${OKE_DIR}/workflow-gateway/deployment.yaml"

echo
echo "[5/6] Applying Shop/CRM Deployments + Services + HPA + PDB..."
apply_manifest "${OKE_DIR}/shop/deployment.yaml"
apply_manifest "${OKE_DIR}/crm/deployment.yaml"

echo
echo "[6/6] Applying NetworkPolicies..."
apply_manifest "${OKE_DIR}/common/network-policies.yaml"

echo
echo "Waiting for rollouts..."
if [[ "${APPLY}" == "true" ]]; then
    kubectl rollout status deployment/octo-apm-java-demo     -n "${K8S_NAMESPACE_SHOP}" --timeout=240s
    kubectl rollout status deployment/octo-workflow-gateway  -n "${K8S_NAMESPACE_SHOP}" --timeout=240s
    kubectl rollout status deployment/octo-drone-shop        -n "${K8S_NAMESPACE_SHOP}" --timeout=240s
    kubectl rollout status deployment/enterprise-crm-portal  -n "${K8S_NAMESPACE_CRM}"  --timeout=240s
else
    echo "  Skipped because APPLY=false"
fi

echo
echo "NodePort services for existing OCI LB backends:"
if [[ "${APPLY}" == "true" ]]; then
    kubectl get svc octo-drone-shop-lb        -n "${K8S_NAMESPACE_SHOP}"
    kubectl get svc enterprise-crm-portal-lb  -n "${K8S_NAMESPACE_CRM}"
else
    echo "  Skipped because APPLY=false"
fi
echo
echo "Internal Java payment gateway service:"
if [[ "${APPLY}" == "true" ]]; then
    kubectl get svc octo-apm-java-demo         -n "${K8S_NAMESPACE_SHOP}"
else
    echo "  Skipped because APPLY=false"
fi
echo
echo "Internal workflow gateway service:"
if [[ "${APPLY}" == "true" ]]; then
    kubectl get svc octo-workflow-gateway      -n "${K8S_NAMESPACE_SHOP}"
else
    echo "  Skipped because APPLY=false"
fi

echo
echo "================================================================"
echo " Done. The existing public OCI LB is not changed by this script."
echo " Prepare OKE backend sets with:"
echo "   ./deploy/oke/wire-existing-lb-backends.sh --apply"
echo
echo "Validate:"
echo "   kubectl port-forward -n ${K8S_NAMESPACE_SHOP} svc/octo-drone-shop 18080:8080"
echo "   kubectl port-forward -n ${K8S_NAMESPACE_CRM} svc/enterprise-crm-portal 18081:8080"
echo "================================================================"
