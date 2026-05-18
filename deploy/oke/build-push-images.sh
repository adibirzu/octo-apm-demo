#!/usr/bin/env bash
# Build and push the OKE images used by octo-apm-demo.
#
# Uses docker buildx for linux/amd64 by default so ARM workstations can publish
# images runnable on OKE worker nodes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

usage() {
    cat <<'EOF'
Usage: deploy/oke/build-push-images.sh

Builds and pushes the four OKE images. Set IMAGE_TAG to the immutable tag that
will be deployed. PUSH_LATEST=false by default to avoid mutable production
deployments; set PUSH_LATEST=true only when intentionally refreshing the
convenience latest tag.

Safety checks:
  VERIFY_RUNTIME_UID=true     # run each pushed image and require UID 10001
  EXPECTED_RUNTIME_UID=10001
  ALLOW_LATEST_IMAGE_TAG=true # manual exception for IMAGE_TAG=latest
EOF
}

case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
    "")
        ;;
    *)
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 2
        ;;
esac

: "${OCI_PROFILE:=emdemo}"
: "${OCIR_REGION:=us-phoenix-1}"
: "${OCIR_TENANCY:=$(oci os ns get --profile "${OCI_PROFILE}" --query data --raw-output)}"
: "${IMAGE_TAG:=$(date -u +%Y%m%d%H%M%S)}"
: "${PLATFORM:=linux/amd64}"
: "${PUSH_LATEST:=false}"
: "${BUILDER:=docker}"
: "${OUTPUTS_FILE:=${REPO_ROOT}/credentials/emdemo/outputs.json}"
: "${VERIFY_RUNTIME_UID:=true}"
: "${EXPECTED_RUNTIME_UID:=10001}"
: "${ALLOW_LATEST_IMAGE_TAG:=false}"

require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}

ensure_repo() {
    local repo="$1"
    local compartment_id="$2"
    if oci artifacts container repository list \
        --profile "${OCI_PROFILE}" \
        --compartment-id "${compartment_id}" \
        --display-name "${repo}" \
        --all \
        --query 'data.items[0].id' \
        --raw-output 2>/dev/null | grep -q '^ocid1.'; then
        echo "  OCIR repo exists: ${repo}"
        return
    fi
    oci artifacts container repository create \
        --profile "${OCI_PROFILE}" \
        --compartment-id "${compartment_id}" \
        --display-name "${repo}" \
        --is-public false \
        --freeform-tags '{"project":"octo-apm-demo","managed_by":"deploy/oke/build-push-images.sh"}' >/dev/null
    echo "  OCIR repo created: ${repo}"
}

build_push() {
    local repo="$1"
    local dockerfile="$2"
    local context="$3"
    local image="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/${repo}:${IMAGE_TAG}"
    local latest="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/${repo}:latest"
    local tags=(-t "${image}")
    if [[ "${PUSH_LATEST}" == "true" ]]; then
        tags+=(-t "${latest}")
    fi
    echo "Building ${repo} (${PLATFORM})..."
    if [[ "${BUILDER}" == "docker" ]]; then
        docker buildx build --platform "${PLATFORM}" -f "${dockerfile}" "${tags[@]}" --push "${context}"
    else
        podman build --platform "${PLATFORM}" -f "${dockerfile}" "${tags[@]}" "${context}"
        podman push "${image}"
        if [[ "${PUSH_LATEST}" == "true" ]]; then
            podman push "${latest}"
        fi
    fi
}

verify_runtime_uid() {
    local repo="$1"
    local image="$2"
    local runtime_uid
    local run_output

    if [[ "${VERIFY_RUNTIME_UID}" != "true" ]]; then
        return
    fi

    echo "Verifying ${repo} runtime UID..."
    if [[ "${BUILDER}" == "docker" ]]; then
        if run_output="$(docker run --rm --platform "${PLATFORM}" --entrypoint id "${image}" -u 2>/dev/null)"; then
            runtime_uid="${run_output}"
        else
            runtime_uid="$(docker image inspect "${image}" --format '{{.Config.User}}' 2>/dev/null | cut -d: -f1)"
        fi
    else
        if run_output="$(podman run --rm --platform "${PLATFORM}" --entrypoint id "${image}" -u 2>/dev/null)"; then
            runtime_uid="${run_output}"
        else
            runtime_uid="$(podman image inspect "${image}" --format '{{.Config.User}}' 2>/dev/null | cut -d: -f1)"
        fi
    fi

    if [[ "${runtime_uid}" != "${EXPECTED_RUNTIME_UID}" ]]; then
        echo "Image ${image} runs as UID ${runtime_uid}, expected ${EXPECTED_RUNTIME_UID}." >&2
        echo "Do not deploy this tag with the OKE pod securityContext." >&2
        exit 1
    fi
    echo "  ${repo} runtime UID ${runtime_uid} OK"
}

require_tool oci
require_tool jq
require_tool "${BUILDER}"

if [[ ! -f "${OUTPUTS_FILE}" ]]; then
    echo "Missing outputs file: ${OUTPUTS_FILE}" >&2
    exit 1
fi

COMPARTMENT_ID="$(jq -r '.deployment_compartment_id.value' "${OUTPUTS_FILE}")"
if [[ -z "${COMPARTMENT_ID}" || "${COMPARTMENT_ID}" == "null" ]]; then
    echo "Could not read deployment compartment id from ${OUTPUTS_FILE}" >&2
    exit 1
fi

if [[ "${IMAGE_TAG}" == "latest" && "${ALLOW_LATEST_IMAGE_TAG}" != "true" ]]; then
    echo "Refusing to publish mutable image tag 'latest'. Set IMAGE_TAG to an immutable tag." >&2
    exit 1
fi

echo "================================================================"
echo " OKE image build/push"
echo "   Registry: ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}"
echo "   Tag:      ${IMAGE_TAG}"
echo "   Platform: ${PLATFORM}"
echo "================================================================"

for repo in octo-drone-shop enterprise-crm-portal octo-apm-java-demo octo-workflow-gateway; do
    ensure_repo "${repo}" "${COMPARTMENT_ID}"
done

build_push octo-drone-shop "${REPO_ROOT}/shop/Dockerfile" "${REPO_ROOT}"
verify_runtime_uid octo-drone-shop "${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${IMAGE_TAG}"
build_push enterprise-crm-portal "${REPO_ROOT}/crm/Dockerfile" "${REPO_ROOT}"
verify_runtime_uid enterprise-crm-portal "${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal:${IMAGE_TAG}"
build_push octo-apm-java-demo "${REPO_ROOT}/services/apm-java-demo/Dockerfile" "${REPO_ROOT}"
verify_runtime_uid octo-apm-java-demo "${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-apm-java-demo:${IMAGE_TAG}"
build_push octo-workflow-gateway "${REPO_ROOT}/shop/services/workflow-gateway/Dockerfile" "${REPO_ROOT}/shop/services/workflow-gateway"
verify_runtime_uid octo-workflow-gateway "${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-workflow-gateway:${IMAGE_TAG}"

cat <<EOF

Images pushed:
  ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${IMAGE_TAG}
  ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal:${IMAGE_TAG}
  ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-apm-java-demo:${IMAGE_TAG}
  ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-workflow-gateway:${IMAGE_TAG}

Deploy with:
  DNS_DOMAIN=octodemo.cloud OCIR_REGION=${OCIR_REGION} OCIR_TENANCY=${OCIR_TENANCY} IMAGE_TAG=${IMAGE_TAG} ./deploy/oke/deploy-oke.sh
EOF
