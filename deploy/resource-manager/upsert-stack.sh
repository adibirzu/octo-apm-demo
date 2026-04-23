#!/usr/bin/env bash
# Package and create/update the unified OCI Resource Manager stack.
#
# Usage:
#   OCI_PROFILE=DEFAULT \
#   OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
#   ./deploy/resource-manager/upsert-stack.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ZIP="${SCRIPT_DIR}/build/octo-stack.zip"

: "${OCI_PROFILE:=DEFAULT}"
: "${OCI_COMPARTMENT_ID:?Set OCI_COMPARTMENT_ID}"
: "${STACK_DISPLAY_NAME:=octo-apm-demo-unified-stack}"
: "${STACK_DESCRIPTION:=Unified OCI Resource Manager stack for the OCTO APM Demo deploy surface.}"
: "${TERRAFORM_VERSION:=}"

usage() {
    sed -n '2,8p' "$0"
}

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            usage
            exit 0
            ;;
    esac
done

echo "[stack] Packaging Resource Manager zip..."
bash "${SCRIPT_DIR}/stack-package.sh" >/dev/null

if [[ ! -f "${BUILD_ZIP}" ]]; then
    echo "Stack package missing: ${BUILD_ZIP}" >&2
    exit 1
fi

existing_stack_id="$(
    oci --profile "${OCI_PROFILE}" resource-manager stack list \
        --compartment-id "${OCI_COMPARTMENT_ID}" \
        --all --output json |
        jq -r --arg name "${STACK_DISPLAY_NAME}" '
            .data[]
            | select(.[ "display-name" ] == $name)
            | .id
        ' | head -1
)"

freeform_tags='{"project":"octo-apm-demo","managed-by":"upsert-stack.sh","source":"github"}'

if [[ -n "${existing_stack_id}" ]]; then
    echo "[stack] Updating ${STACK_DISPLAY_NAME} (${existing_stack_id})..."
    update_cmd=(
        oci --profile "${OCI_PROFILE}" resource-manager stack update
        --stack-id "${existing_stack_id}"
        --display-name "${STACK_DISPLAY_NAME}"
        --description "${STACK_DESCRIPTION}"
        --config-source "${BUILD_ZIP}"
        --working-directory "."
        --freeform-tags "${freeform_tags}"
        --force
        --wait-for-state ACTIVE
    )
    if [[ -n "${TERRAFORM_VERSION}" ]]; then
        update_cmd+=(--terraform-version "${TERRAFORM_VERSION}")
    fi
    "${update_cmd[@]}" >/dev/null
    stack_id="${existing_stack_id}"
    action="updated"
else
    echo "[stack] Creating ${STACK_DISPLAY_NAME}..."
    create_cmd=(
        oci --profile "${OCI_PROFILE}" resource-manager stack create
        --compartment-id "${OCI_COMPARTMENT_ID}"
        --display-name "${STACK_DISPLAY_NAME}"
        --description "${STACK_DESCRIPTION}"
        --config-source "${BUILD_ZIP}"
        --working-directory "."
        --freeform-tags "${freeform_tags}"
        --wait-for-state ACTIVE
        --query 'data.id'
        --raw-output
    )
    if [[ -n "${TERRAFORM_VERSION}" ]]; then
        create_cmd+=(--terraform-version "${TERRAFORM_VERSION}")
    fi
    stack_id="$("${create_cmd[@]}")"
    action="created"
fi

echo
echo "Resource Manager stack ${action}:"
echo "  display-name: ${STACK_DISPLAY_NAME}"
echo "  stack-id:     ${stack_id}"
echo "  compartment:  ${OCI_COMPARTMENT_ID}"
