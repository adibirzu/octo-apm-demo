#!/usr/bin/env bash
# Create/reuse the small emdemo OKE cluster for octo-apm-demo.
#
# This intentionally reuses the existing emdemo VCN, ATP, APM domain, OCI
# Logging resources, and public OCI Load Balancer. It does not alter LB listener
# routing. Workloads are exposed as NodePort services so the existing LB can be
# switched later with deploy/oke/wire-existing-lb-backends.sh.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy/oke/create-emdemo-small-cluster.sh

Creates or reuses the small emdemo OKE cluster and node pool for
octo-apm-demo. The script reuses the existing VCN, public LB, APM domain,
Logging resources, and ATP database from credentials/emdemo/outputs.json.

Key overrides:
  OKE_WORKER_SUBNET_ID=<subnet-ocid>
  OKE_ADMIN_CIDR=<trusted-admin-cidr>
  OKE_NODE_POOL_SIZE=2 OKE_NODE_OCPUS=2 OKE_NODE_MEMORY_GBS=16
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
: "${OKE_CLUSTER_NAME:=octo-apm-demo-oke}"
: "${OKE_KUBERNETES_VERSION:=v1.34.1}"
: "${OKE_CLUSTER_TYPE:=ENHANCED_CLUSTER}"
: "${OKE_NODE_SHAPE:=VM.Standard.E5.Flex}"
: "${OKE_NODE_POOL_SIZE:=2}"
: "${OKE_NODE_OCPUS:=2}"
: "${OKE_NODE_MEMORY_GBS:=16}"
: "${OKE_NODE_BOOT_GBS:=93}"
: "${OKE_NODE_POOL_NAME:=${OKE_CLUSTER_NAME}-pool}"
: "${OKE_PUBLIC_API_ENDPOINT:=true}"
: "${OKE_ADMIN_CIDR:=}"
: "${OKE_SHOP_NODEPORT:=30080}"
: "${OKE_CRM_NODEPORT:=30081}"

require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}

json_value() {
    jq -r "$1" "${OUTPUTS_FILE}"
}

oci_json() {
    oci "$@" --profile "${OCI_PROFILE}" --output json
}

oci_plain() {
    oci "$@" --profile "${OCI_PROFILE}"
}

rule_exists() {
    local nsg_id="$1"
    local direction="$2"
    local protocol="$3"
    local peer="$4"
    local min_port="$5"
    local max_port="$6"
    oci_json network nsg rules list --nsg-id "${nsg_id}" --all |
        jq -e --arg direction "${direction}" \
              --arg protocol "${protocol}" \
              --arg peer "${peer}" \
              --argjson min "${min_port}" \
              --argjson max "${max_port}" '
            .data[] |
            select(.direction == $direction) |
            select(.protocol == $protocol) |
            select((.source // .destination) == $peer) |
            select(."tcp-options"."destination-port-range".min == $min) |
            select(."tcp-options"."destination-port-range".max == $max)
        ' >/dev/null
}

add_nsg_tcp_rule() {
    local nsg_id="$1"
    local direction="$2"
    local peer_type="$3"
    local peer="$4"
    local min_port="$5"
    local max_port="$6"
    local description="$7"
    if rule_exists "${nsg_id}" "${direction}" "6" "${peer}" "${min_port}" "${max_port}"; then
        echo "  NSG rule exists: ${description}"
        return
    fi
    if [[ "${direction}" == "INGRESS" ]]; then
        oci_plain network nsg rules add \
            --nsg-id "${nsg_id}" \
            --security-rules "[{\"direction\":\"INGRESS\",\"protocol\":\"6\",\"sourceType\":\"${peer_type}\",\"source\":\"${peer}\",\"tcpOptions\":{\"destinationPortRange\":{\"min\":${min_port},\"max\":${max_port}}},\"description\":\"${description}\"}]" >/dev/null
    else
        oci_plain network nsg rules add \
            --nsg-id "${nsg_id}" \
            --security-rules "[{\"direction\":\"EGRESS\",\"protocol\":\"6\",\"destinationType\":\"${peer_type}\",\"destination\":\"${peer}\",\"tcpOptions\":{\"destinationPortRange\":{\"min\":${min_port},\"max\":${max_port}}},\"description\":\"${description}\"}]" >/dev/null
    fi
    echo "  Added NSG rule: ${description}"
}

nsg_rule_exists_all() {
    local nsg_id="$1"
    local direction="$2"
    local protocol="$3"
    local peer="$4"
    oci_json network nsg rules list --nsg-id "${nsg_id}" --all |
        jq -e --arg direction "${direction}" \
              --arg protocol "${protocol}" \
              --arg peer "${peer}" '
            .data[] |
            select(.direction == $direction) |
            select(.protocol == $protocol) |
            select((.source // .destination) == $peer) |
            select(."tcp-options" == null)
        ' >/dev/null
}

add_nsg_all_rule() {
    local nsg_id="$1"
    local direction="$2"
    local peer_type="$3"
    local peer="$4"
    local description="$5"
    if nsg_rule_exists_all "${nsg_id}" "${direction}" "all" "${peer}"; then
        echo "  NSG rule exists: ${description}"
        return
    fi
    if [[ "${direction}" == "INGRESS" ]]; then
        oci_plain network nsg rules add \
            --nsg-id "${nsg_id}" \
            --security-rules "[{\"direction\":\"INGRESS\",\"protocol\":\"all\",\"sourceType\":\"${peer_type}\",\"source\":\"${peer}\",\"description\":\"${description}\"}]" >/dev/null
    else
        oci_plain network nsg rules add \
            --nsg-id "${nsg_id}" \
            --security-rules "[{\"direction\":\"EGRESS\",\"protocol\":\"all\",\"destinationType\":\"${peer_type}\",\"destination\":\"${peer}\",\"description\":\"${description}\"}]" >/dev/null
    fi
    echo "  Added NSG rule: ${description}"
}

security_list_rule_exists() {
    local security_list_id="$1"
    local source="$2"
    local min_port="$3"
    local max_port="$4"
    oci_json network security-list get --security-list-id "${security_list_id}" |
        jq -e --arg source "${source}" \
              --argjson min "${min_port}" \
              --argjson max "${max_port}" '
            .data."ingress-security-rules"[] |
            select(.protocol == "6") |
            select(.source == $source) |
            select(."tcp-options"."destination-port-range".min == $min) |
            select(."tcp-options"."destination-port-range".max == $max)
        ' >/dev/null
}

add_security_list_ingress_tcp() {
    local security_list_id="$1"
    local source="$2"
    local min_port="$3"
    local max_port="$4"
    local description="$5"
    if security_list_rule_exists "${security_list_id}" "${source}" "${min_port}" "${max_port}"; then
        echo "  Security-list rule exists: ${description}"
        return
    fi
    local tmp
    tmp="$(mktemp)"
    oci_json network security-list get --security-list-id "${security_list_id}" |
        jq --arg source "${source}" \
           --arg description "${description}" \
           --argjson min "${min_port}" \
           --argjson max "${max_port}" '
            .data."ingress-security-rules"
            + [{
                "protocol": "6",
                "source": $source,
                "source-type": "CIDR_BLOCK",
                "is-stateless": false,
                "description": $description,
                "tcp-options": {
                    "destination-port-range": {"min": $min, "max": $max}
                }
            }]
        ' > "${tmp}"
    oci_plain network security-list update \
        --security-list-id "${security_list_id}" \
        --ingress-security-rules "file://${tmp}" \
        --force >/dev/null
    rm -f "${tmp}"
    echo "  Added security-list rule: ${description}"
}

find_or_create_nsg() {
    local compartment_id="$1"
    local vcn_id="$2"
    local name="$3"
    local id
    id="$(oci_json network nsg list --compartment-id "${compartment_id}" --vcn-id "${vcn_id}" --all |
        jq -r --arg name "${name}" '.data[] | select(."display-name" == $name) | .id' | head -1)"
    if [[ -n "${id}" ]]; then
        echo "${id}"
        return
    fi
    oci_json network nsg create \
        --compartment-id "${compartment_id}" \
        --vcn-id "${vcn_id}" \
        --display-name "${name}" \
        --freeform-tags '{"project":"octo-apm-demo","managed_by":"deploy/oke/create-emdemo-small-cluster.sh"}' |
        jq -r '.data.id'
}

existing_cluster_id() {
    local compartment_id="$1"
    oci_json ce cluster list --compartment-id "${compartment_id}" --all |
        jq -r --arg name "${OKE_CLUSTER_NAME}" '.data[] | select(.name == $name and ."lifecycle-state" != "DELETED") | .id' | head -1
}

existing_node_pool_id() {
    local compartment_id="$1"
    local cluster_id="$2"
    oci_json ce node-pool list --compartment-id "${compartment_id}" --all |
        jq -r --arg name "${OKE_NODE_POOL_NAME}" --arg cluster "${cluster_id}" '.data[] | select(.name == $name and ."cluster-id" == $cluster and ."lifecycle-state" != "DELETED") | .id' | head -1
}

resolve_node_image_id() {
    if [[ -n "${OKE_NODE_IMAGE_ID:-}" ]]; then
        echo "${OKE_NODE_IMAGE_ID}"
        return
    fi
    local image_id
    image_id="$(oci_json ce node-pool list --compartment-id "${COMPARTMENT_ID}" --all |
        jq -r --arg version "${OKE_KUBERNETES_VERSION}" --arg shape "${OKE_NODE_SHAPE}" '
            .data[]
            | select(."kubernetes-version" == $version and ."node-shape" == $shape)
            | ."node-source-details"."image-id"
        ' | head -1)"
    if [[ -n "${image_id}" && "${image_id}" != "null" ]]; then
        echo "${image_id}"
        return
    fi
    image_id="$(oci_json ce node-pool-options get --node-pool-option-id all |
        jq -r --arg version "${OKE_KUBERNETES_VERSION#v}" '
            .data.sources[]
            | select(."source-name" | test($version))
            | ."image-id"
        ' | head -1)"
    if [[ -n "${image_id}" && "${image_id}" != "null" ]]; then
        echo "${image_id}"
        return
    fi
    echo "Could not resolve an OKE node image. Set OKE_NODE_IMAGE_ID and retry." >&2
    exit 1
}

require_tool oci
require_tool jq
require_tool curl
require_tool kubectl

if [[ ! -f "${OUTPUTS_FILE}" ]]; then
    echo "Missing outputs file: ${OUTPUTS_FILE}" >&2
    exit 1
fi

COMPARTMENT_ID="$(json_value '.deployment_compartment_id.value')"
VCN_ID="$(json_value '.network.value.vcn_id')"
WORKER_SUBNET_ID="${OKE_WORKER_SUBNET_ID:-$(json_value '.network.value.app_subnet_id')}"
ENDPOINT_SUBNET_ID="${OKE_ENDPOINT_SUBNET_ID:-$(json_value '.network.value.lb_subnet_id')}"
APP_NSG_ID="$(json_value '.network.value.app_nsg_id')"
LB_NSG_ID="$(json_value '.network.value.lb_nsg_id')"
LB_PUBLIC_SL_ID="$(oci_json network security-list list --compartment-id "${COMPARTMENT_ID}" --vcn-id "${VCN_ID}" --all |
    jq -r '.data[] | select(."display-name" == "octo-emdemo-lb-public-sl") | .id' | head -1)"
ADMIN_CIDR="${OKE_ADMIN_CIDR:-$(curl -fsS --max-time 10 https://ifconfig.me 2>/dev/null || true)/32}"
if [[ "${ADMIN_CIDR}" == "/32" ]]; then
    echo "Could not determine admin CIDR. Set OKE_ADMIN_CIDR." >&2
    exit 1
fi

echo "================================================================"
echo " OKE small cluster bootstrap — emdemo"
echo "   Cluster:        ${OKE_CLUSTER_NAME}"
echo "   Shape:          ${OKE_NODE_POOL_SIZE} x ${OKE_NODE_SHAPE} (${OKE_NODE_OCPUS} OCPU / ${OKE_NODE_MEMORY_GBS} GiB each)"
echo "   Total nodes:    $((OKE_NODE_POOL_SIZE * OKE_NODE_OCPUS)) OCPU / $((OKE_NODE_POOL_SIZE * OKE_NODE_MEMORY_GBS)) GiB"
echo "   VCN:            ${VCN_ID}"
echo "   Worker subnet:  ${WORKER_SUBNET_ID}"
echo "   Endpoint subnet:${ENDPOINT_SUBNET_ID}"
echo "   API CIDR:       ${ADMIN_CIDR}"
echo "================================================================"

OKE_WORKER_NSG_ID="$(find_or_create_nsg "${COMPARTMENT_ID}" "${VCN_ID}" "octo-emdemo-oke-workers-nsg")"
OKE_ENDPOINT_NSG_ID="$(find_or_create_nsg "${COMPARTMENT_ID}" "${VCN_ID}" "octo-emdemo-oke-endpoint-nsg")"

echo
echo "[1/5] Ensuring network rules..."
add_nsg_tcp_rule "${OKE_ENDPOINT_NSG_ID}" "INGRESS" "CIDR_BLOCK" "${ADMIN_CIDR}" 6443 6443 "Admin access to OKE API endpoint"
add_nsg_tcp_rule "${OKE_ENDPOINT_NSG_ID}" "INGRESS" "NETWORK_SECURITY_GROUP" "${OKE_WORKER_NSG_ID}" 6443 6443 "OKE workers to Kubernetes API endpoint"
add_nsg_tcp_rule "${OKE_ENDPOINT_NSG_ID}" "INGRESS" "NETWORK_SECURITY_GROUP" "${OKE_WORKER_NSG_ID}" 12250 12250 "OKE workers to Kubernetes API endpoint tunnel"
add_nsg_tcp_rule "${OKE_ENDPOINT_NSG_ID}" "EGRESS" "NETWORK_SECURITY_GROUP" "${OKE_WORKER_NSG_ID}" 1 65535 "OKE API endpoint to workers for flannel"
add_nsg_all_rule "${OKE_WORKER_NSG_ID}" "INGRESS" "NETWORK_SECURITY_GROUP" "${OKE_WORKER_NSG_ID}" "OKE worker-to-worker traffic"
add_nsg_tcp_rule "${OKE_WORKER_NSG_ID}" "INGRESS" "NETWORK_SECURITY_GROUP" "${OKE_ENDPOINT_NSG_ID}" 1 65535 "OKE API endpoint to workers for flannel"
add_nsg_tcp_rule "${OKE_WORKER_NSG_ID}" "INGRESS" "NETWORK_SECURITY_GROUP" "${LB_NSG_ID}" "${OKE_SHOP_NODEPORT}" "${OKE_SHOP_NODEPORT}" "Existing OCI LB to OKE shop NodePort"
add_nsg_tcp_rule "${OKE_WORKER_NSG_ID}" "INGRESS" "NETWORK_SECURITY_GROUP" "${LB_NSG_ID}" "${OKE_CRM_NODEPORT}" "${OKE_CRM_NODEPORT}" "Existing OCI LB to OKE admin NodePort"
add_nsg_tcp_rule "${LB_NSG_ID}" "EGRESS" "NETWORK_SECURITY_GROUP" "${OKE_WORKER_NSG_ID}" "${OKE_SHOP_NODEPORT}" "${OKE_SHOP_NODEPORT}" "Existing OCI LB egress to OKE shop NodePort"
add_nsg_tcp_rule "${LB_NSG_ID}" "EGRESS" "NETWORK_SECURITY_GROUP" "${OKE_WORKER_NSG_ID}" "${OKE_CRM_NODEPORT}" "${OKE_CRM_NODEPORT}" "Existing OCI LB egress to OKE admin NodePort"
if [[ "${OKE_PUBLIC_API_ENDPOINT}" == "true" && -n "${LB_PUBLIC_SL_ID}" ]]; then
    add_security_list_ingress_tcp "${LB_PUBLIC_SL_ID}" "${ADMIN_CIDR}" 6443 6443 "Admin access to OKE API endpoint"
fi

CLUSTER_ID="$(existing_cluster_id "${COMPARTMENT_ID}")"
if [[ -z "${CLUSTER_ID}" ]]; then
    echo
    echo "[2/5] Creating OKE cluster..."
    CLUSTER_ID="$(oci_json ce cluster create \
        --name "${OKE_CLUSTER_NAME}" \
        --compartment-id "${COMPARTMENT_ID}" \
        --vcn-id "${VCN_ID}" \
        --kubernetes-version "${OKE_KUBERNETES_VERSION}" \
        --type "${OKE_CLUSTER_TYPE}" \
        --cluster-pod-network-options '[{"cniType":"FLANNEL_OVERLAY"}]' \
        --endpoint-subnet-id "${ENDPOINT_SUBNET_ID}" \
        --endpoint-nsg-ids "[\"${OKE_ENDPOINT_NSG_ID}\"]" \
        --endpoint-public-ip-enabled "${OKE_PUBLIC_API_ENDPOINT}" \
        --service-lb-subnet-ids "[\"$(json_value '.network.value.lb_subnet_id')\"]" \
        --pods-cidr "10.244.0.0/16" \
        --services-cidr "10.96.0.0/16" \
        --freeform-tags '{"project":"octo-apm-demo","environment":"emdemo","managed_by":"deploy/oke/create-emdemo-small-cluster.sh"}' \
        --wait-for-state SUCCEEDED \
        --max-wait-seconds 1800 |
        jq -r '.data.resources[]? | select(."entity-type" == "cluster") | .identifier' | head -1)"
    if [[ -z "${CLUSTER_ID}" ]]; then
        CLUSTER_ID="$(existing_cluster_id "${COMPARTMENT_ID}")"
    fi
else
    echo
    echo "[2/5] Reusing OKE cluster: ${CLUSTER_ID}"
fi

if [[ -z "${CLUSTER_ID}" ]]; then
    echo "Cluster ID was not returned by OCI." >&2
    exit 1
fi

NODE_POOL_ID="$(existing_node_pool_id "${COMPARTMENT_ID}" "${CLUSTER_ID}")"
if [[ -z "${NODE_POOL_ID}" ]]; then
    echo
    echo "[3/5] Creating managed node pool..."
    NODE_IMAGE_ID="$(resolve_node_image_id)"
    AD_NAME="$(oci_json iam availability-domain list --compartment-id "${COMPARTMENT_ID}" |
        jq -r '.data[0].name')"
    NODE_POOL_ID="$(oci_json ce node-pool create \
        --cluster-id "${CLUSTER_ID}" \
        --compartment-id "${COMPARTMENT_ID}" \
        --name "${OKE_NODE_POOL_NAME}" \
        --kubernetes-version "${OKE_KUBERNETES_VERSION}" \
        --node-shape "${OKE_NODE_SHAPE}" \
        --node-shape-config "{\"ocpus\":${OKE_NODE_OCPUS},\"memoryInGBs\":${OKE_NODE_MEMORY_GBS}}" \
        --node-image-id "${NODE_IMAGE_ID}" \
        --node-boot-volume-size-in-gbs "${OKE_NODE_BOOT_GBS}" \
        --size "${OKE_NODE_POOL_SIZE}" \
        --placement-configs "[{\"availabilityDomain\":\"${AD_NAME}\",\"subnetId\":\"${WORKER_SUBNET_ID}\"}]" \
        --nsg-ids "[\"${APP_NSG_ID}\",\"${OKE_WORKER_NSG_ID}\"]" \
        --cni-type FLANNEL_OVERLAY \
        --node-freeform-tags '{"project":"octo-apm-demo","environment":"emdemo","role":"oke-worker"}' \
        --initial-node-labels '[{"key":"octo.oracle.com/pool","value":"small"},{"key":"octo.oracle.com/project","value":"octo-apm-demo"}]' \
        --wait-for-state SUCCEEDED \
        --max-wait-seconds 2400 |
        jq -r '.data.resources[]? | select(."entity-type" == "nodepool") | .identifier' | head -1)"
else
    echo
    echo "[3/5] Reusing node pool: ${NODE_POOL_ID}"
fi

echo
echo "[4/5] Writing kubeconfig context..."
KUBECONFIG_PATH="${KUBECONFIG_PATH:-${HOME}/.kube/config}"
if [[ "${OKE_PUBLIC_API_ENDPOINT}" == "true" ]]; then
    KUBE_ENDPOINT="PUBLIC_ENDPOINT"
else
    KUBE_ENDPOINT="PRIVATE_ENDPOINT"
fi
oci_plain ce cluster create-kubeconfig \
    --cluster-id "${CLUSTER_ID}" \
    --file "${KUBECONFIG_PATH}" \
    --region "${OCI_REGION}" \
    --token-version 2.0.0 \
    --kube-endpoint "${KUBE_ENDPOINT}" >/dev/null
kubectl config rename-context "$(kubectl config current-context)" "${OKE_CLUSTER_NAME}" >/dev/null 2>&1 || true
kubectl config use-context "${OKE_CLUSTER_NAME}" >/dev/null
KUBE_USER="$(kubectl config view --minify -o jsonpath='{.contexts[0].context.user}')"
kubectl config set-credentials "${KUBE_USER}" --exec-env="OCI_CLI_PROFILE=${OCI_PROFILE}" >/dev/null

echo
echo "[5/5] Cluster summary..."
kubectl get nodes -o wide || true
cat <<EOF

Cluster created/reused:
  cluster_id=${CLUSTER_ID}
  node_pool_id=${NODE_POOL_ID:-unknown}

Next:
  ./deploy/oke/bootstrap-emdemo-secrets.sh
  DNS_DOMAIN=octodemo.cloud OCIR_REGION=${OCI_REGION} OCIR_TENANCY=\$(oci os ns get --profile ${OCI_PROFILE} --query data --raw-output) ./deploy/oke/deploy-oke.sh
EOF
