#!/usr/bin/env bash
# Deploy OCTO Drone Shop to OKE via a remote build host.
#
# Builds on the remote x86_64 VM (no QEMU), pushes to OCIR,
# and rolls out on OKE with zero-downtime rolling update.
#
# Usage:
#   ./deploy/deploy.sh                  # Build + push + rollout
#   ./deploy/deploy.sh --build-only     # Build + push, no rollout
#   ./deploy/deploy.sh --rollout-only   # Rollout existing latest tag
#
# Prerequisites:
#   - SSH access to the remote build host
#   - OCIR login configured on the VM
#   - kubectl context set to OKE cluster

set -euo pipefail

OCIR_REPO="${OCIR_REPO:?Set OCIR_REPO (e.g. <region>.ocir.io/<namespace>/octo-drone-shop)}"
REMOTE_HOST="${REMOTE_HOST:-remote-builder}"
REMOTE_DIR="/tmp/octo-apm-demo-shop"
NAMESPACE="${K8S_NAMESPACE:-octo-drone-shop}"
DEPLOYMENT="${K8S_DEPLOYMENT:-octo-drone-shop}"
CONTAINER="${K8S_CONTAINER:-app}"
TAG=$(date +%Y%m%d%H%M%S)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUILD=true
ROLLOUT=true
for arg in "$@"; do
    case "$arg" in
        --build-only)  ROLLOUT=false ;;
        --rollout-only) BUILD=false ;;
    esac
done

# DNS_DOMAIN is only needed when rolling out (deriving SHOP/CRM URLs); a
# pure build can skip it. No example.cloud fallback — a wrong DNS default
# has historically caused CRM/shop URLs to publish placeholder hostnames in
# production, so we refuse to guess.
if $ROLLOUT; then
    DNS_DOMAIN="${DNS_DOMAIN:?Set DNS_DOMAIN (e.g. tenant-a.example.invalid) for SHOP/CRM URL derivation, or pass --build-only.}"
    SHOP_PUBLIC_URL="${SHOP_PUBLIC_URL:-https://drone.${DNS_DOMAIN}}"
    CRM_PUBLIC_URL="${CRM_PUBLIC_URL:-https://backend.${DNS_DOMAIN}}"
    VERIFY_URL="${VERIFY_URL:-${SHOP_PUBLIC_URL}/ready}"
fi

echo "================================================"
echo " OCTO Drone Shop Deploy"
echo " OCIR:  ${OCIR_REPO}"
echo " Tag:   ${TAG}"
echo " Build: ${BUILD}"
echo " Roll:  ${ROLLOUT}"
echo "================================================"

if $BUILD; then
    # ── 1. Sync code to the remote build host ──────────
    # Shop Dockerfile requires REPO ROOT context (needs sibling services/cache/client
    # and services/async-worker for editable installs). Sync shop/ + services/ together.
    echo ""
    echo "[1/4] Syncing code to ${REMOTE_HOST}:${REMOTE_DIR}..."
    rsync -az --delete \
        --exclude '.git' \
        --exclude '__pycache__' \
        --exclude '.env' \
        --exclude '.env.*' \
        --exclude 'node_modules' \
        --exclude 'tests' \
        --exclude 'k6' \
        --exclude 'docs' \
        --exclude '.pytest_cache' \
        --exclude 'playwright-report' \
        --exclude 'test-results' \
        --exclude '.claude' \
        --exclude '*.log' \
        --include 'shop/***' \
        --include 'services/cache/***' \
        --include 'services/async-worker/***' \
        --include 'services/' \
        --exclude '*' \
        "${REPO_ROOT}/" "${REMOTE_HOST}:${REMOTE_DIR}/"

    echo "[1/4] Sync complete"

    # ── 2. Build on VM (native x86_64) ─────────────────
    echo ""
    echo "[2/4] Building Docker image on ${REMOTE_HOST}..."
    ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker build -f shop/Dockerfile -t ${OCIR_REPO}:${TAG} -t ${OCIR_REPO}:latest ."
    echo "[2/4] Build complete: ${OCIR_REPO}:${TAG}"

    # ── 3. Push to OCIR ────────────────────────────────
    echo ""
    echo "[3/4] Pushing to OCIR..."
    ssh "${REMOTE_HOST}" "docker push ${OCIR_REPO}:${TAG} && docker push ${OCIR_REPO}:latest"
    echo "[3/4] Push complete"

    # ── Cleanup old images on VM (keep last 3) ─────────
    ssh "${REMOTE_HOST}" "docker images ${OCIR_REPO} --format '{{.Tag}} {{.ID}}' | \
        grep -v latest | sort -r | tail -n +4 | awk '{print \$2}' | \
        xargs -r docker rmi 2>/dev/null" || true
fi

if $ROLLOUT; then
    # ── 4. Rolling update on OKE ───────────────────────
    IMAGE="${OCIR_REPO}:${TAG}"
    if ! $BUILD; then
        IMAGE="${OCIR_REPO}:latest"
    fi

    # First-time apply: if the Deployment doesn't exist yet, render the
    # manifest with envsubst and create it. Otherwise fall through to the
    # faster `set image` + `set env` path.
    if ! kubectl get "deployment/${DEPLOYMENT}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        echo "[4/4] Deployment missing — first-time apply with envsubst..."
        : "${OCIR_REGION:?Set OCIR_REGION for first-time apply (e.g. eu-frankfurt-1)}"
        : "${OCIR_TENANCY:?Set OCIR_TENANCY for first-time apply (object storage namespace)}"
        export OCIR_REGION OCIR_TENANCY DNS_DOMAIN CRM_PUBLIC_URL
        export IMAGE_TAG="${TAG}"
        manifest_dir="${REPO_ROOT}/deploy/k8s/oke/shop"
        if [[ ! -d "${manifest_dir}" ]]; then
            manifest_dir="${REPO_ROOT}/deploy/k8s/shop"
        fi
        command -v envsubst >/dev/null 2>&1 || {
            echo "envsubst not found — install gettext (brew install gettext / apt-get install gettext-base)" >&2
            exit 1
        }
        for f in "${manifest_dir}"/*.yaml; do
            envsubst < "$f" | kubectl apply -n "${NAMESPACE}" -f -
        done
    fi

    echo ""
    echo "[4/4] Rolling out ${DEPLOYMENT} → ${IMAGE}..."
    echo "[4/4] Setting CRM_PUBLIC_URL=${CRM_PUBLIC_URL}"
    kubectl set env "deployment/${DEPLOYMENT}" \
        "CRM_PUBLIC_URL=${CRM_PUBLIC_URL}" \
        -n "${NAMESPACE}" >/dev/null
    kubectl set image "deployment/${DEPLOYMENT}" \
        "${CONTAINER}=${IMAGE}" \
        -n "${NAMESPACE}"

    echo "[4/4] Waiting for rollout..."
    kubectl rollout status "deployment/${DEPLOYMENT}" \
        -n "${NAMESPACE}" \
        --timeout=180s

    echo ""
    echo "Verifying pod health..."
    kubectl get pods -n "${NAMESPACE}" -l "app=${DEPLOYMENT}" \
        -o wide --no-headers

    echo ""
    echo "Checking /ready endpoint..."
    sleep 5
    READY=$(curl -s --max-time 10 "${VERIFY_URL}" 2>/dev/null || echo '{"ready": false}')
    echo "$READY" | python3 -m json.tool 2>/dev/null || echo "$READY"
fi

echo ""
echo "================================================"
echo " Deploy complete!"
echo " Image: ${OCIR_REPO}:${TAG}"
if $ROLLOUT; then
    echo " Verify: ${SHOP_PUBLIC_URL}/api/observability/360"
fi
echo "================================================"
