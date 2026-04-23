#!/usr/bin/env bash
# Build + push + roll out octo-apm-java-demo — the tiny Spring Boot
# service whose only job is to populate the OCI APM "App Servers" view
# (Apdex, Active Servers, Young/Old GC time, Process CPU load). See
# site/observability/demo-drilldown.md §App servers.
#
# Usage:
#   ./deploy/deploy-apm-java-demo.sh                # build + push + rollout
#   ./deploy/deploy-apm-java-demo.sh --build-only
#   ./deploy/deploy-apm-java-demo.sh --rollout-only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OCIR_REPO="${OCIR_REPO:?Set OCIR_REPO (e.g. <region>.ocir.io/<ns>/octo-apm-java-demo)}"
REMOTE_HOST="${REMOTE_HOST:-remote-builder}"
REMOTE_DIR="/tmp/octo-apm-java-demo"
NAMESPACE="${K8S_NAMESPACE:-octo-drone-shop}"
DEPLOYMENT="${K8S_DEPLOYMENT:-octo-apm-java-demo}"
CONTAINER="${K8S_CONTAINER:-app}"
TAG=$(date +%Y%m%d%H%M%S)

BUILD=true
ROLLOUT=true
for arg in "$@"; do
    case "$arg" in
        --build-only)   ROLLOUT=false ;;
        --rollout-only) BUILD=false ;;
    esac
done

echo "================================================"
echo " octo-apm-java-demo deploy"
echo " OCIR:  ${OCIR_REPO}"
echo " Tag:   ${TAG}"
echo " Build: ${BUILD}"
echo " Roll:  ${ROLLOUT}"
echo "================================================"

if $BUILD; then
    echo
    echo "[1/3] Bundling OCI APM Java agent (if available locally)..."
    AGENT_STAGE="${REPO_ROOT}/services/apm-java-demo/agent-bundle"
    mkdir -p "${AGENT_STAGE}"
    # Operator places the OCI APM Java agent zip at one of these paths:
    #   services/apm-java-demo/agent-bundle/apm-java-agent.zip
    #   $OCI_APM_AGENT_ZIP (env override)
    # If found, unpack into agent-bundle/ so the Dockerfile COPYs it in.
    agent_src="${OCI_APM_AGENT_ZIP:-${AGENT_STAGE}/apm-java-agent.zip}"
    if [[ -f "${agent_src}" ]]; then
        unzip -qo "${agent_src}" -d "${AGENT_STAGE}" && echo "      agent unpacked to ${AGENT_STAGE}"
    else
        echo "      NO agent zip at ${agent_src} — image will build without it."
        echo "      Download once from Console (APM → Java Agent → Download), place at:"
        echo "         ${AGENT_STAGE}/apm-java-agent.zip"
        echo "      or export OCI_APM_AGENT_ZIP=/path/to/zip"
    fi

    echo
    echo "[2/3] Syncing to ${REMOTE_HOST}:${REMOTE_DIR}..."
    rsync -az --delete \
        --exclude '.git' \
        --exclude 'target' \
        --exclude '*.log' \
        --include 'services/apm-java-demo/***' \
        --include 'services/' \
        --exclude '*' \
        "${REPO_ROOT}/" "${REMOTE_HOST}:${REMOTE_DIR}/"

    echo
    echo "[3/3] Building on ${REMOTE_HOST}..."
    ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker build -f services/apm-java-demo/Dockerfile -t ${OCIR_REPO}:${TAG} -t ${OCIR_REPO}:latest ."

    echo
    echo "[4/4] Pushing to OCIR..."
    ssh "${REMOTE_HOST}" "docker push ${OCIR_REPO}:${TAG} && docker push ${OCIR_REPO}:latest"
fi

if $ROLLOUT; then
    IMAGE="${OCIR_REPO}:${TAG}"
    if ! $BUILD; then
        IMAGE="${OCIR_REPO}:latest"
    fi

    # First-time apply — render manifest + kubectl apply.
    if ! kubectl get "deployment/${DEPLOYMENT}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        echo
        echo "[rollout] Deployment missing — first-time apply with envsubst..."
        : "${OCIR_REGION:?Set OCIR_REGION (e.g. eu-frankfurt-1)}"
        : "${OCIR_TENANCY:?Set OCIR_TENANCY}"
        export OCIR_REGION OCIR_TENANCY
        export IMAGE_TAG="${TAG}"
        command -v envsubst >/dev/null || { echo "envsubst required"; exit 1; }
        envsubst < "${REPO_ROOT}/deploy/k8s/oke/apm-java-demo/deployment.yaml" \
            | kubectl apply -n "${NAMESPACE}" -f -
    fi

    echo
    echo "[rollout] Rolling out ${DEPLOYMENT} → ${IMAGE}..."
    kubectl set image "deployment/${DEPLOYMENT}" "${CONTAINER}=${IMAGE}" -n "${NAMESPACE}"
    kubectl rollout status "deployment/${DEPLOYMENT}" -n "${NAMESPACE}" --timeout=240s

    echo
    echo "[rollout] Pod health:"
    kubectl get pods -n "${NAMESPACE}" -l "app=${DEPLOYMENT}" --no-headers
fi

echo
echo "================================================"
echo " octo-apm-java-demo deploy complete"
if $ROLLOUT; then
    echo " Verify: kubectl port-forward -n ${NAMESPACE} svc/${DEPLOYMENT} 8080:80"
    echo "         curl http://localhost:8080/"
fi
echo "================================================"
