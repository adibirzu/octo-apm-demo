#!/usr/bin/env bash
# Build + push + roll out the Enterprise CRM Portal image in octo-apm-demo.
#
# Symmetric to deploy-shop.sh; keeps the two service rollouts independent
# so a fix in one does not force a redeploy of the other.
#
# Usage:
#   ./deploy/deploy-crm.sh                  # build + push + rollout
#   ./deploy/deploy-crm.sh --build-only
#   ./deploy/deploy-crm.sh --rollout-only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OCIR_REPO="${OCIR_REPO:?Set OCIR_REPO (e.g. <region>.ocir.io/<namespace>/enterprise-crm-portal)}"
REMOTE_HOST="${REMOTE_HOST:-remote-builder}"
REMOTE_DIR="${REMOTE_DIR:-/tmp/octo-apm-demo-crm}"
NAMESPACE="${K8S_NAMESPACE:-enterprise-crm}"
DEPLOYMENT="${K8S_DEPLOYMENT:-enterprise-crm-portal}"
CONTAINER="${K8S_CONTAINER:-app}"
K8S_NAMESPACE_SHOP="${K8S_NAMESPACE_SHOP:-octo-drone-shop}"
K8S_NAMESPACE_CRM="${K8S_NAMESPACE_CRM:-${NAMESPACE}}"
PUBLISH_VIA_INGRESS="${PUBLISH_VIA_INGRESS:-true}"
TAG=$(date +%Y%m%d%H%M%S)

BUILD=true
ROLLOUT=true
for arg in "$@"; do
    case "$arg" in
        --build-only)  ROLLOUT=false ;;
        --rollout-only) BUILD=false ;;
    esac
done

if $ROLLOUT; then
    DNS_DOMAIN="${DNS_DOMAIN:?Set DNS_DOMAIN (for DEFAULT/oci4cca use cyber-sec.ro) for backend URL derivation, or pass --build-only.}"
    CRM_PUBLIC_URL="${CRM_PUBLIC_URL:-https://crm.${DNS_DOMAIN}}"
    SHOP_PUBLIC_URL="${SHOP_PUBLIC_URL:-https://shop.${DNS_DOMAIN}}"
    SERVICE_SHOP_URL="${SERVICE_SHOP_URL:-http://octo-drone-shop.${K8S_NAMESPACE_SHOP}.svc.cluster.local:8080}"
    VERIFY_URL="${VERIFY_URL:-${CRM_PUBLIC_URL}/ready}"
fi

apply_manifest_dir() {
    local manifest_dir="$1"
    local rendered
    local manifest
    for manifest in "${manifest_dir}"/*.yaml; do
        rendered="$(mktemp)"
        envsubst < "${manifest}" > "${rendered}"
        if [[ "${PUBLISH_VIA_INGRESS}" == "true" ]]; then
            python3 - "${rendered}" <<'PYEOF' | kubectl apply -n "${NAMESPACE}" -f -
import sys
import yaml

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    docs = list(yaml.safe_load_all(handle))

for doc in docs:
    if not doc:
        continue
    if doc.get("kind") == "Service" and doc.get("spec", {}).get("type") == "LoadBalancer":
        continue
    print("---")
    sys.stdout.write(yaml.safe_dump(doc, sort_keys=False))
PYEOF
        else
            kubectl apply -n "${NAMESPACE}" -f "${rendered}"
        fi
        rm -f "${rendered}"
    done
}

echo "================================================"
echo " Enterprise CRM Portal Deploy (octo-apm-demo)"
echo " OCIR:  ${OCIR_REPO}"
echo " Tag:   ${TAG}"
echo " Build: ${BUILD}"
echo " Roll:  ${ROLLOUT}"
echo "================================================"

if $BUILD; then
    echo
    echo "[1/4] Syncing crm/ + services/cache/ to ${REMOTE_HOST}:${REMOTE_DIR}..."
    rsync -az --delete \
        --exclude '.git' \
        --exclude '__pycache__' \
        --exclude '.env' \
        --exclude '.env.*' \
        --exclude 'node_modules' \
        --exclude 'tests' \
        --exclude 'k6' \
        --exclude '.pytest_cache' \
        --exclude 'build' \
        --exclude '.claude' \
        --exclude '*.log' \
        --include 'crm/***' \
        --include 'services/cache/***' \
        --include 'services/' \
        --exclude '*' \
        "${REPO_ROOT}/" "${REMOTE_HOST}:${REMOTE_DIR}/"
    echo "[1/4] Sync complete"

    echo
    echo "[2/4] Building on ${REMOTE_HOST}..."
    ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker build -f crm/Dockerfile -t ${OCIR_REPO}:${TAG} -t ${OCIR_REPO}:latest ."

    echo
    echo "[3/4] Pushing to OCIR..."
    ssh "${REMOTE_HOST}" "docker push ${OCIR_REPO}:${TAG} && docker push ${OCIR_REPO}:latest"
fi

if $ROLLOUT; then
    IMAGE="${OCIR_REPO}:${TAG}"
    if ! $BUILD; then
        IMAGE="${OCIR_REPO}:latest"
    fi

    # First-time apply branch — render manifest via envsubst.
    if ! kubectl get "deployment/${DEPLOYMENT}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        echo
        echo "[4/4] Deployment missing — first-time apply with envsubst..."
        : "${OCIR_REGION:?Set OCIR_REGION for first-time apply}"
        : "${OCIR_TENANCY:?Set OCIR_TENANCY for first-time apply}"
        export OCIR_REGION OCIR_TENANCY DNS_DOMAIN SHOP_PUBLIC_URL CRM_PUBLIC_URL
        export IMAGE_TAG="${TAG}"
        manifest_dir="${REPO_ROOT}/deploy/k8s/oke/crm"
        if [[ ! -d "${manifest_dir}" ]]; then
            manifest_dir="${REPO_ROOT}/deploy/k8s/crm"
        fi
        command -v envsubst >/dev/null 2>&1 || {
            echo "envsubst not found — install gettext (brew install gettext / apt-get install gettext-base)" >&2
            exit 1
        }
        export OCIR_REGION OCIR_TENANCY DNS_DOMAIN SHOP_PUBLIC_URL CRM_PUBLIC_URL K8S_NAMESPACE_SHOP K8S_NAMESPACE_CRM
        apply_manifest_dir "${manifest_dir}"
    fi

    echo
    echo "[4/4] Rolling out ${DEPLOYMENT} → ${IMAGE}..."
    kubectl set env "deployment/${DEPLOYMENT}" \
        "SERVICE_SHOP_URL=${SERVICE_SHOP_URL}" \
        "CRM_BASE_URL=${CRM_PUBLIC_URL}" \
        -n "${NAMESPACE}" >/dev/null
    kubectl set image "deployment/${DEPLOYMENT}" "${CONTAINER}=${IMAGE}" -n "${NAMESPACE}"
    kubectl rollout status "deployment/${DEPLOYMENT}" -n "${NAMESPACE}" --timeout=180s
fi

echo
echo "================================================"
echo " CRM deploy complete — verify: ${VERIFY_URL:-(build-only)}"
echo "================================================"
