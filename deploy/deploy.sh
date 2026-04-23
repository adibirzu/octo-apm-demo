#!/usr/bin/env bash
# Unified build + push + rollout wrapper for the OCTO Drone Shop + CRM.
#
# Usage:
#   OCIR_REGION=eu-frankfurt-1 OCIR_TENANCY=<namespace> DNS_DOMAIN=cyber-sec.ro \
#   ./deploy/deploy.sh
#
#   ./deploy/deploy.sh --build-only
#   ./deploy/deploy.sh --rollout-only
#   ./deploy/deploy.sh --shop-only
#   ./deploy/deploy.sh --crm-only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    sed -n '2,16p' "$0"
}

RUN_SHOP=true
RUN_CRM=true
forward_args=()

for arg in "$@"; do
    case "$arg" in
        --shop-only)
            RUN_CRM=false
            ;;
        --crm-only)
            RUN_SHOP=false
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            forward_args+=("$arg")
            ;;
    esac
done

if ! $RUN_SHOP && ! $RUN_CRM; then
    echo "Nothing selected. Use the default, --shop-only, or --crm-only." >&2
    exit 1
fi

: "${OCIR_REGION:?Set OCIR_REGION (for example eu-frankfurt-1)}"
: "${OCIR_TENANCY:=${OCIR_NAMESPACE:-}}"
: "${OCIR_TENANCY:?Set OCIR_TENANCY or OCIR_NAMESPACE (object storage namespace)}"

REMOTE_HOST="${REMOTE_HOST:-${REMOTE_BUILD_HOST:-remote-builder}}"
K8S_NAMESPACE_SHOP="${K8S_NAMESPACE_SHOP:-octo-drone-shop}"
K8S_NAMESPACE_CRM="${K8S_NAMESPACE_CRM:-enterprise-crm}"

if [[ ! " ${forward_args[*]} " =~ [[:space:]]--build-only[[:space:]] ]]; then
    : "${DNS_DOMAIN:?Set DNS_DOMAIN for rollout or pass --build-only}"
    SHOP_PUBLIC_URL="${SHOP_PUBLIC_URL:-https://shop.${DNS_DOMAIN}}"
    CRM_PUBLIC_URL="${CRM_PUBLIC_URL:-https://crm.${DNS_DOMAIN}}"
fi

SHOP_OCIR_REPO="${SHOP_OCIR_REPO:-${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop}"
CRM_OCIR_REPO="${CRM_OCIR_REPO:-${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal}"

run_service() {
    local name="$1"
    local repo="$2"
    local namespace="$3"
    local deployment="$4"
    local container="$5"
    local script="$6"

    echo
    echo "================================================"
    echo " ${name}"
    echo " Repo: ${repo}"
    echo " Ns:   ${namespace}"
    echo "================================================"

    OCIR_REPO="${repo}" \
    OCIR_REGION="${OCIR_REGION}" \
    OCIR_TENANCY="${OCIR_TENANCY}" \
    DNS_DOMAIN="${DNS_DOMAIN:-}" \
    SHOP_PUBLIC_URL="${SHOP_PUBLIC_URL:-}" \
    CRM_PUBLIC_URL="${CRM_PUBLIC_URL:-}" \
    REMOTE_HOST="${REMOTE_HOST}" \
    K8S_NAMESPACE="${namespace}" \
    K8S_DEPLOYMENT="${deployment}" \
    K8S_CONTAINER="${container}" \
    bash "${SCRIPT_DIR}/${script}" "${forward_args[@]}"
}

if $RUN_SHOP; then
    run_service \
        "Drone Shop" \
        "${SHOP_OCIR_REPO}" \
        "${K8S_NAMESPACE_SHOP}" \
        "octo-drone-shop" \
        "app" \
        "deploy-shop.sh"
fi

if $RUN_CRM; then
    run_service \
        "Enterprise CRM" \
        "${CRM_OCIR_REPO}" \
        "${K8S_NAMESPACE_CRM}" \
        "enterprise-crm-portal" \
        "crm" \
        "deploy-crm.sh"
fi

echo
echo "Unified deploy finished."
