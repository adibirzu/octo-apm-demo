#!/usr/bin/env bash
# Create/reuse a dedicated private OKE worker subnet in the existing emdemo VCN.
#
# The VM deployment keeps using the app private subnet. This subnet is for OKE
# workers only, so OKE node bootstrap/security rules do not loosen VM ingress.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy/oke/ensure-emdemo-worker-subnet.sh

Creates or reuses the dedicated private OKE worker subnet in the existing
emdemo VCN. It also scopes security-list rules for worker bootstrap and the
existing OCI Load Balancer NodePort path.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUTS_FILE="${OUTPUTS_FILE:-${REPO_ROOT}/credentials/emdemo/outputs.json}"

: "${OCI_PROFILE:=emdemo}"
: "${OCI_REGION:=us-phoenix-1}"
: "${OKE_WORKER_SUBNET_NAME:=octo-emdemo-oke-workers-private-subnet}"
: "${OKE_WORKER_SUBNET_CIDR:=10.42.40.0/24}"
: "${OKE_WORKER_SECURITY_LIST_NAME:=octo-emdemo-oke-workers-private-sl}"
: "${OKE_SHOP_NODEPORT:=30080}"
: "${OKE_CRM_NODEPORT:=30081}"

require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}

oci_json() {
    oci "$@" --profile "${OCI_PROFILE}" --output json
}

oci_plain() {
    oci "$@" --profile "${OCI_PROFILE}"
}

json_value() {
    jq -r "$1" "${OUTPUTS_FILE}"
}

security_list_id_by_name() {
    local name="$1"
    oci_json network security-list list \
        --compartment-id "${COMPARTMENT_ID}" \
        --vcn-id "${VCN_ID}" \
        --all |
        jq -r --arg name "${name}" '.data[] | select(."display-name" == $name and ."lifecycle-state" == "AVAILABLE") | .id' |
        head -1
}

subnet_id_by_name() {
    local name="$1"
    oci_json network subnet list \
        --compartment-id "${COMPARTMENT_ID}" \
        --vcn-id "${VCN_ID}" \
        --all |
        jq -r --arg name "${name}" '.data[] | select(."display-name" == $name and ."lifecycle-state" == "AVAILABLE") | .id' |
        head -1
}

security_list_rule_exists() {
    local security_list_id="$1"
    local direction="$2"
    local peer="$3"
    local min_port="${4:-}"
    local max_port="${5:-}"
    if [[ "${direction}" == "INGRESS" ]]; then
        if [[ -z "${min_port}" ]]; then
            oci_json network security-list get --security-list-id "${security_list_id}" |
                jq -e --arg source "${peer}" '
                    .data."ingress-security-rules"[]
                    | select(.protocol == "all")
                    | select(.source == $source)
                ' >/dev/null
        else
            oci_json network security-list get --security-list-id "${security_list_id}" |
                jq -e --arg source "${peer}" --argjson min "${min_port}" --argjson max "${max_port}" '
                    .data."ingress-security-rules"[]
                    | select(.protocol == "6")
                    | select(.source == $source)
                    | select(."tcp-options"."destination-port-range".min == $min)
                    | select(."tcp-options"."destination-port-range".max == $max)
                ' >/dev/null
        fi
    else
        oci_json network security-list get --security-list-id "${security_list_id}" |
            jq -e --arg destination "${peer}" --argjson min "${min_port}" --argjson max "${max_port}" '
                .data."egress-security-rules"[]
                | select(.protocol == "6")
                | select(.destination == $destination)
                | select(."tcp-options"."destination-port-range".min == $min)
                | select(."tcp-options"."destination-port-range".max == $max)
            ' >/dev/null
    fi
}

update_security_list_rules() {
    local security_list_id="$1"
    local direction="$2"
    local rules_file="$3"
    if [[ "${direction}" == "INGRESS" ]]; then
        oci_plain network security-list update \
            --security-list-id "${security_list_id}" \
            --ingress-security-rules "file://${rules_file}" \
            --force >/dev/null
    else
        oci_plain network security-list update \
            --security-list-id "${security_list_id}" \
            --egress-security-rules "file://${rules_file}" \
            --force >/dev/null
    fi
}

add_security_list_ingress_all() {
    local security_list_id="$1"
    local source="$2"
    local description="$3"
    if security_list_rule_exists "${security_list_id}" INGRESS "${source}"; then
        echo "  Security-list rule exists: ${description}"
        return
    fi
    local tmp
    tmp="$(mktemp)"
    oci_json network security-list get --security-list-id "${security_list_id}" |
        jq --arg source "${source}" --arg description "${description}" '
            .data."ingress-security-rules"
            + [{
                "protocol": "all",
                "source": $source,
                "source-type": "CIDR_BLOCK",
                "is-stateless": false,
                "description": $description
            }]
        ' > "${tmp}"
    update_security_list_rules "${security_list_id}" INGRESS "${tmp}"
    rm -f "${tmp}"
    echo "  Added security-list rule: ${description}"
}

add_security_list_tcp() {
    local security_list_id="$1"
    local direction="$2"
    local peer="$3"
    local min_port="$4"
    local max_port="$5"
    local description="$6"
    if security_list_rule_exists "${security_list_id}" "${direction}" "${peer}" "${min_port}" "${max_port}"; then
        echo "  Security-list rule exists: ${description}"
        return
    fi
    local tmp
    tmp="$(mktemp)"
    if [[ "${direction}" == "INGRESS" ]]; then
        oci_json network security-list get --security-list-id "${security_list_id}" |
            jq --arg source "${peer}" --arg description "${description}" --argjson min "${min_port}" --argjson max "${max_port}" '
                .data."ingress-security-rules"
                + [{
                    "protocol": "6",
                    "source": $source,
                    "source-type": "CIDR_BLOCK",
                    "is-stateless": false,
                    "description": $description,
                    "tcp-options": {"destination-port-range": {"min": $min, "max": $max}}
                }]
            ' > "${tmp}"
        update_security_list_rules "${security_list_id}" INGRESS "${tmp}"
    else
        oci_json network security-list get --security-list-id "${security_list_id}" |
            jq --arg destination "${peer}" --arg description "${description}" --argjson min "${min_port}" --argjson max "${max_port}" '
                .data."egress-security-rules"
                + [{
                    "protocol": "6",
                    "destination": $destination,
                    "destination-type": "CIDR_BLOCK",
                    "is-stateless": false,
                    "description": $description,
                    "tcp-options": {"destination-port-range": {"min": $min, "max": $max}}
                }]
            ' > "${tmp}"
        update_security_list_rules "${security_list_id}" EGRESS "${tmp}"
    fi
    rm -f "${tmp}"
    echo "  Added security-list rule: ${description}"
}

require_tool oci
require_tool jq

if [[ ! -f "${OUTPUTS_FILE}" ]]; then
    echo "Missing outputs file: ${OUTPUTS_FILE}" >&2
    exit 1
fi

COMPARTMENT_ID="$(json_value '.deployment_compartment_id.value')"
VCN_ID="$(json_value '.network.value.vcn_id')"
APP_SUBNET_ID="$(json_value '.network.value.app_subnet_id')"
LB_SUBNET_ID="$(json_value '.network.value.lb_subnet_id')"

APP_SUBNET="$(oci_json network subnet get --subnet-id "${APP_SUBNET_ID}")"
LB_SUBNET="$(oci_json network subnet get --subnet-id "${LB_SUBNET_ID}")"
APP_ROUTE_TABLE_ID="$(jq -r '.data."route-table-id"' <<<"${APP_SUBNET}")"
APP_DHCP_OPTIONS_ID="$(jq -r '.data."dhcp-options-id"' <<<"${APP_SUBNET}")"
LB_SUBNET_CIDR="$(jq -r '.data."cidr-block"' <<<"${LB_SUBNET}")"
LB_SECURITY_LIST_ID="$(jq -r '.data."security-list-ids"[0]' <<<"${LB_SUBNET}")"

echo "Ensuring dedicated OKE worker security list..."
WORKER_SECURITY_LIST_ID="$(security_list_id_by_name "${OKE_WORKER_SECURITY_LIST_NAME}")"
if [[ -z "${WORKER_SECURITY_LIST_ID}" ]]; then
    WORKER_SECURITY_LIST_ID="$(oci_json network security-list create \
        --compartment-id "${COMPARTMENT_ID}" \
        --vcn-id "${VCN_ID}" \
        --display-name "${OKE_WORKER_SECURITY_LIST_NAME}" \
        --ingress-security-rules "[]" \
        --egress-security-rules '[{"protocol":"all","destination":"0.0.0.0/0","destinationType":"CIDR_BLOCK","isStateless":false,"description":"OKE worker egress through NAT and Service Gateway routes."}]' \
        --freeform-tags '{"project":"octo-apm-demo","environment":"emdemo","managed_by":"deploy/oke/ensure-emdemo-worker-subnet.sh"}' |
        jq -r '.data.id')"
    echo "  Created ${OKE_WORKER_SECURITY_LIST_NAME}"
else
    echo "  Reusing ${OKE_WORKER_SECURITY_LIST_NAME}"
fi

add_security_list_ingress_all "${WORKER_SECURITY_LIST_ID}" "${OKE_WORKER_SUBNET_CIDR}" "OKE worker-to-worker traffic"
add_security_list_tcp "${WORKER_SECURITY_LIST_ID}" INGRESS "${LB_SUBNET_CIDR}" 1 65535 "OKE API endpoint to workers for flannel"
add_security_list_tcp "${WORKER_SECURITY_LIST_ID}" INGRESS "${LB_SUBNET_CIDR}" "${OKE_SHOP_NODEPORT}" "${OKE_SHOP_NODEPORT}" "Existing OCI LB to OKE shop NodePort"
add_security_list_tcp "${WORKER_SECURITY_LIST_ID}" INGRESS "${LB_SUBNET_CIDR}" "${OKE_CRM_NODEPORT}" "${OKE_CRM_NODEPORT}" "Existing OCI LB to OKE admin NodePort"

echo "Ensuring OKE endpoint/LB subnet security-list rules for worker subnet..."
add_security_list_tcp "${LB_SECURITY_LIST_ID}" INGRESS "${OKE_WORKER_SUBNET_CIDR}" 6443 6443 "OKE workers to Kubernetes API endpoint"
add_security_list_tcp "${LB_SECURITY_LIST_ID}" INGRESS "${OKE_WORKER_SUBNET_CIDR}" 12250 12250 "OKE workers to Kubernetes API endpoint tunnel"
add_security_list_tcp "${LB_SECURITY_LIST_ID}" EGRESS "${OKE_WORKER_SUBNET_CIDR}" 1 65535 "OKE API endpoint to workers for flannel"
add_security_list_tcp "${LB_SECURITY_LIST_ID}" EGRESS "${OKE_WORKER_SUBNET_CIDR}" "${OKE_SHOP_NODEPORT}" "${OKE_SHOP_NODEPORT}" "Existing OCI LB egress to OKE shop NodePort"
add_security_list_tcp "${LB_SECURITY_LIST_ID}" EGRESS "${OKE_WORKER_SUBNET_CIDR}" "${OKE_CRM_NODEPORT}" "${OKE_CRM_NODEPORT}" "Existing OCI LB egress to OKE admin NodePort"

echo "Ensuring dedicated OKE worker subnet..."
WORKER_SUBNET_ID="$(subnet_id_by_name "${OKE_WORKER_SUBNET_NAME}")"
if [[ -z "${WORKER_SUBNET_ID}" ]]; then
    WORKER_SUBNET_ID="$(oci_json network subnet create \
        --compartment-id "${COMPARTMENT_ID}" \
        --vcn-id "${VCN_ID}" \
        --display-name "${OKE_WORKER_SUBNET_NAME}" \
        --cidr-block "${OKE_WORKER_SUBNET_CIDR}" \
        --prohibit-public-ip-on-vnic true \
        --route-table-id "${APP_ROUTE_TABLE_ID}" \
        --dhcp-options-id "${APP_DHCP_OPTIONS_ID}" \
        --security-list-ids "[\"${WORKER_SECURITY_LIST_ID}\"]" \
        --dns-label "octooke" \
        --freeform-tags '{"project":"octo-apm-demo","environment":"emdemo","managed_by":"deploy/oke/ensure-emdemo-worker-subnet.sh"}' |
        jq -r '.data.id')"
    echo "  Created ${OKE_WORKER_SUBNET_NAME}"
else
    echo "  Reusing ${OKE_WORKER_SUBNET_NAME}"
fi

cat <<EOF

Dedicated OKE worker subnet is ready:
  subnet_id=${WORKER_SUBNET_ID}
  cidr=${OKE_WORKER_SUBNET_CIDR}

Use it with:
  OKE_WORKER_SUBNET_ID=${WORKER_SUBNET_ID} \\
  OKE_NODE_POOL_NAME=octo-apm-demo-oke-pool-private \\
  ./deploy/oke/create-emdemo-small-cluster.sh
EOF
