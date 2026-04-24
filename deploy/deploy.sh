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
TENANCY_CACHE="${SCRIPT_DIR}/.last-tenancy.env"

usage() {
    sed -n '2,16p' "$0"
}

RUN_SHOP=true
RUN_CRM=true
BUILD_ONLY=false
forward_args=()

for arg in "$@"; do
    case "$arg" in
        --shop-only)
            RUN_CRM=false
            ;;
        --crm-only)
            RUN_SHOP=false
            ;;
        --build-only)
            BUILD_ONLY=true
            forward_args+=("$arg")
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

if [[ ! " ${forward_args[*]-} " =~ [[:space:]]--build-only[[:space:]] ]]; then
    : "${DNS_DOMAIN:?Set DNS_DOMAIN for rollout or pass --build-only}"
    SHOP_PUBLIC_URL="${SHOP_PUBLIC_URL:-https://shop.${DNS_DOMAIN}}"
    CRM_PUBLIC_URL="${CRM_PUBLIC_URL:-https://crm.${DNS_DOMAIN}}"
fi

SHOP_OCIR_REPO="${SHOP_OCIR_REPO:-${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop}"
CRM_OCIR_REPO="${CRM_OCIR_REPO:-${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal}"

cached_env_value() {
    local key="$1"
    [[ -f "${TENANCY_CACHE}" ]] || return 1
    sed -n "s/^export ${key}=//p" "${TENANCY_CACHE}" | tail -1
}

discover_atp_ocid() {
    local compartment_id profile atp_id
    if [[ -n "${ATP_OCID:-}" ]]; then
        printf '%s' "${ATP_OCID}"
        return 0
    fi
    if [[ -n "${AUTONOMOUS_DATABASE_ID:-}" ]]; then
        printf '%s' "${AUTONOMOUS_DATABASE_ID}"
        return 0
    fi
    compartment_id="${OCI_COMPARTMENT_ID:-$(cached_env_value OCI_COMPARTMENT_ID || true)}"
    profile="${OCI_PROFILE:-$(cached_env_value OCI_PROFILE || true)}"
    [[ -n "${compartment_id}" ]] || return 1
    profile="${profile:-DEFAULT}"
    atp_id="$(
        oci db autonomous-database list \
            --profile "${profile}" \
            --compartment-id "${compartment_id}" \
            --all \
            --query "data[?\"display-name\"=='${ATP_DISPLAY_NAME:-octo-apm-demo-atp}'].id | [0]" \
            --raw-output 2>/dev/null || true
    )"
    [[ -n "${atp_id}" && "${atp_id}" != "null" ]] || return 1
    printf '%s' "${atp_id}"
}

ensure_atp_available() {
    command -v oci >/dev/null 2>&1 || return 0
    local atp_id profile state
    atp_id="$(discover_atp_ocid || true)"
    [[ -n "${atp_id}" ]] || return 0
    profile="${OCI_PROFILE:-$(cached_env_value OCI_PROFILE || true)}"
    profile="${profile:-DEFAULT}"
    state="$(
        oci db autonomous-database get \
            --profile "${profile}" \
            --autonomous-database-id "${atp_id}" \
            --query 'data."lifecycle-state"' \
            --raw-output 2>/dev/null || true
    )"
    case "${state}" in
        AVAILABLE)
            echo "ATP ready: ${atp_id}"
            ;;
        STOPPED)
            echo "ATP is STOPPED — starting ${atp_id}..."
            oci db autonomous-database start \
                --profile "${profile}" \
                --autonomous-database-id "${atp_id}" >/dev/null
            oci db autonomous-database get \
                --profile "${profile}" \
                --autonomous-database-id "${atp_id}" \
                --wait-for-state AVAILABLE >/dev/null
            echo "ATP ready: ${atp_id}"
            ;;
        STARTING|STOPPING|PROVISIONING)
            echo "Waiting for ATP ${atp_id} to become AVAILABLE (current state: ${state})..."
            oci db autonomous-database get \
                --profile "${profile}" \
                --autonomous-database-id "${atp_id}" \
                --wait-for-state AVAILABLE >/dev/null
            echo "ATP ready: ${atp_id}"
            ;;
        "")
            echo "ATP state check skipped — unable to resolve lifecycle state for ${atp_id}" >&2
            ;;
        *)
            echo "ATP is in unexpected state ${state} (${atp_id}). Continuing, but rollout may fail." >&2
            ;;
    esac
}

ingress_controller_service_name() {
    local candidate
    for candidate in ingress-nginx-controller nginx-ingress-ingress-nginx-controller; do
        if kubectl -n ingress-nginx get svc "${candidate}" >/dev/null 2>&1; then
            printf '%s' "${candidate}"
            return 0
        fi
    done
    return 1
}

assert_shared_ingress_ready() {
    local ingress_service available endpoints
    ingress_service="$(ingress_controller_service_name || true)"
    [[ -n "${ingress_service}" ]] || return 0
    available="$(
        kubectl -n ingress-nginx get deployment \
            -l app.kubernetes.io/component=controller,app.kubernetes.io/name=ingress-nginx \
            -o jsonpath='{.items[0].status.availableReplicas}' 2>/dev/null || echo 0
    )"
    endpoints="$(kubectl -n ingress-nginx get endpoints "${ingress_service}" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || true)"
    if [[ "${available:-0}" -lt 1 || -z "${endpoints// }" ]]; then
        echo "Shared ingress is not healthy. Recover the managed ingress nodes before rollout." >&2
        kubectl get nodes -o wide >&2 || true
        kubectl -n ingress-nginx get deploy,pods,svc,endpoints -o wide >&2 || true
        return 1
    fi
}

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

    if ((${#forward_args[@]})); then
        OCIR_REPO="${repo}" \
        OCIR_REGION="${OCIR_REGION}" \
        OCIR_TENANCY="${OCIR_TENANCY}" \
        DNS_DOMAIN="${DNS_DOMAIN:-}" \
        SHOP_PUBLIC_URL="${SHOP_PUBLIC_URL:-}" \
        CRM_PUBLIC_URL="${CRM_PUBLIC_URL:-}" \
        K8S_NAMESPACE_SHOP="${K8S_NAMESPACE_SHOP}" \
        K8S_NAMESPACE_CRM="${K8S_NAMESPACE_CRM}" \
        REMOTE_HOST="${REMOTE_HOST}" \
        K8S_NAMESPACE="${namespace}" \
        K8S_DEPLOYMENT="${deployment}" \
        K8S_CONTAINER="${container}" \
        bash "${SCRIPT_DIR}/${script}" "${forward_args[@]}"
    else
        OCIR_REPO="${repo}" \
        OCIR_REGION="${OCIR_REGION}" \
        OCIR_TENANCY="${OCIR_TENANCY}" \
        DNS_DOMAIN="${DNS_DOMAIN:-}" \
        SHOP_PUBLIC_URL="${SHOP_PUBLIC_URL:-}" \
        CRM_PUBLIC_URL="${CRM_PUBLIC_URL:-}" \
        K8S_NAMESPACE_SHOP="${K8S_NAMESPACE_SHOP}" \
        K8S_NAMESPACE_CRM="${K8S_NAMESPACE_CRM}" \
        REMOTE_HOST="${REMOTE_HOST}" \
        K8S_NAMESPACE="${namespace}" \
        K8S_DEPLOYMENT="${deployment}" \
        K8S_CONTAINER="${container}" \
        bash "${SCRIPT_DIR}/${script}"
    fi
}

if ! $BUILD_ONLY; then
    ensure_atp_available
    assert_shared_ingress_ready
fi

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
        "app" \
        "deploy-crm.sh"
fi

echo
echo "Unified deploy finished."
