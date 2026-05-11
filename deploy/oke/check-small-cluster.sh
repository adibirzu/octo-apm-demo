#!/usr/bin/env bash
# Check whether the emdemo OCTO project can host a small OKE test cluster.
#
# This script is intentionally read-only. It checks the target OCTO project VCN,
# existing clusters, OKE cluster quota, node OCPU quota, boot-volume capacity,
# and Service Connector Hub availability for Log Analytics routing.
#
# Usage:
#   OCI_PROFILE=emdemo ./deploy/oke/check-small-cluster.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
esac

OCI_PROFILE="${OCI_PROFILE:-emdemo}"
OCI_REGION="${OCI_REGION:-us-phoenix-1}"
NODE_COUNT="${NODE_COUNT:-2}"
NODE_OCPUS="${NODE_OCPUS:-1}"
NODE_BOOT_GBS="${NODE_BOOT_GBS:-80}"
AVAILABILITY_DOMAIN="${AVAILABILITY_DOMAIN:-Njav:PHX-AD-1}"
OUTPUTS_JSON="${OUTPUTS_JSON:-}"

if [[ -z "${OUTPUTS_JSON}" ]]; then
    if [[ -f "${REPO_ROOT}/credentials/${OCI_PROFILE}/outputs.json" ]]; then
        OUTPUTS_JSON="${REPO_ROOT}/credentials/${OCI_PROFILE}/outputs.json"
    elif [[ -f "/Users/abirzu/dev/octo-apm-demo/credentials/${OCI_PROFILE}/outputs.json" ]]; then
        OUTPUTS_JSON="/Users/abirzu/dev/octo-apm-demo/credentials/${OCI_PROFILE}/outputs.json"
    else
        echo "ERROR: set OUTPUTS_JSON to the OCTO deployment outputs.json path." >&2
        exit 2
    fi
fi

for cmd in oci jq awk; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "ERROR: missing required command: ${cmd}" >&2
        exit 2
    fi
done

if [[ ! -f "${OUTPUTS_JSON}" ]]; then
    echo "ERROR: OUTPUTS_JSON not found: ${OUTPUTS_JSON}" >&2
    exit 2
fi

COMPARTMENT_ID="$(jq -r '.deployment_compartment_id.value // empty' "${OUTPUTS_JSON}")"
TARGET_VCN_ID="$(jq -r '.network.value.vcn_id // empty' "${OUTPUTS_JSON}")"
APP_SUBNET_ID="$(jq -r '.network.value.app_subnet_id // empty' "${OUTPUTS_JSON}")"
LB_SUBNET_ID="$(jq -r '.network.value.lb_subnet_id // empty' "${OUTPUTS_JSON}")"

if [[ -z "${COMPARTMENT_ID}" || -z "${TARGET_VCN_ID}" || -z "${APP_SUBNET_ID}" || -z "${LB_SUBNET_ID}" ]]; then
    echo "ERROR: OUTPUTS_JSON is missing deployment_compartment_id or network outputs." >&2
    exit 2
fi

oci_cmd() {
    oci --profile "${OCI_PROFILE}" --region "${OCI_REGION}" "$@"
}

needed_ocpus="$(awk -v n="${NODE_COUNT}" -v o="${NODE_OCPUS}" 'BEGIN { printf "%.2f", n * o }')"
needed_boot_gbs="$(awk -v n="${NODE_COUNT}" -v g="${NODE_BOOT_GBS}" 'BEGIN { printf "%.0f", n * g }')"

echo "================================================================"
echo " OKE small-cluster preflight - OCTO DEMO"
echo "   OCI profile:      ${OCI_PROFILE}"
echo "   OCI region:       ${OCI_REGION}"
echo "   Compartment:      ${COMPARTMENT_ID}"
echo "   Target VCN:       ${TARGET_VCN_ID}"
echo "   Worker subnet:    ${APP_SUBNET_ID}"
echo "   LB/API subnet:    ${LB_SUBNET_ID}"
echo "   Node shape:       VM.Standard.E4.Flex or VM.Standard.E5.Flex"
echo "   Node plan:        ${NODE_COUNT} nodes x ${NODE_OCPUS} OCPU, ${NODE_BOOT_GBS} GB boot"
echo "   Availability AD:  ${AVAILABILITY_DOMAIN}"
echo "================================================================"

echo
echo "[1/6] Existing OKE clusters in the compartment"
clusters_json="$(oci_cmd ce cluster list --compartment-id "${COMPARTMENT_ID}" --all --output json)"
jq -r '.data[] | "  - \(.name) state=\(."lifecycle-state") vcn=\(."vcn-id") version=\(."kubernetes-version")"' <<<"${clusters_json}"

target_cluster_count="$(jq --arg vcn "${TARGET_VCN_ID}" '[.data[] | select(."lifecycle-state" == "ACTIVE" and ."vcn-id" == $vcn)] | length' <<<"${clusters_json}")"
if [[ "${target_cluster_count}" == "0" ]]; then
    echo "  WARN: no ACTIVE OKE cluster is currently in the OCTO project VCN."
else
    echo "  OK: found ${target_cluster_count} ACTIVE OKE cluster(s) in the OCTO project VCN."
fi

echo
echo "[2/6] Target VCN subnets"
oci_cmd network subnet get --subnet-id "${APP_SUBNET_ID}" --output json |
    jq -r '.data | "  worker subnet: \(.["display-name"]) cidr=\(.["cidr-block"]) private=\(.["prohibit-public-ip-on-vnic"]) state=\(.["lifecycle-state"])"'
oci_cmd network subnet get --subnet-id "${LB_SUBNET_ID}" --output json |
    jq -r '.data | "  lb/api subnet: \(.["display-name"]) cidr=\(.["cidr-block"]) private=\(.["prohibit-public-ip-on-vnic"]) state=\(.["lifecycle-state"])"'

echo
echo "[3/6] OKE cluster-count quota"
cluster_available="$(oci_cmd limits resource-availability get \
    --service-name container-engine \
    --limit-name cluster-count \
    --compartment-id "${COMPARTMENT_ID}" \
    --output json | jq -r '.data.available')"
echo "  available clusters: ${cluster_available}"

echo
echo "[4/6] Compute OCPU quota in ${AVAILABILITY_DOMAIN}"
e4_available="$(oci_cmd limits resource-availability get \
    --service-name compute \
    --limit-name standard-e4-core-count \
    --availability-domain "${AVAILABILITY_DOMAIN}" \
    --compartment-id "${COMPARTMENT_ID}" \
    --output json | jq -r '.data.available')"
e5_available="$(oci_cmd limits resource-availability get \
    --service-name compute \
    --limit-name standard-e5-core-count \
    --availability-domain "${AVAILABILITY_DOMAIN}" \
    --compartment-id "${COMPARTMENT_ID}" \
    --output json | jq -r '.data.available')"
echo "  needed OCPUs:       ${needed_ocpus}"
echo "  E4 Flex available:  ${e4_available}"
echo "  E5 Flex available:  ${e5_available}"

echo
echo "[5/6] Block Volume quota in ${AVAILABILITY_DOMAIN}"
block_available="$(oci_cmd limits resource-availability get \
    --service-name block-storage \
    --limit-name total-storage-gb \
    --availability-domain "${AVAILABILITY_DOMAIN}" \
    --compartment-id "${COMPARTMENT_ID}" \
    --output json | jq -r '.data.available')"
echo "  needed boot GB:     ${needed_boot_gbs}"
echo "  available GB:       ${block_available}"

echo
echo "[6/6] Service Connector Hub quota for Log Analytics"
connector_available="$(oci_cmd limits resource-availability get \
    --service-name service-connector-hub \
    --limit-name service-connector-count \
    --compartment-id "${COMPARTMENT_ID}" \
    --output json | jq -r '.data.available')"
connector_used="$(oci_cmd limits resource-availability get \
    --service-name service-connector-hub \
    --limit-name service-connector-count \
    --compartment-id "${COMPARTMENT_ID}" \
    --output json | jq -r '.data.used')"
echo "  available connectors: ${connector_available}"
echo "  used connectors:      ${connector_used}"
if [[ "${connector_available}" == "0" ]]; then
    echo "  WARN: new OCI Logging -> Log Analytics connectors are blocked by quota."
fi

can_create="true"
if awk -v a="${cluster_available}" 'BEGIN { exit !(a < 1) }'; then
    can_create="false"
fi
if awk -v e4="${e4_available}" -v e5="${e5_available}" -v need="${needed_ocpus}" 'BEGIN { exit !((e4 < need) && (e5 < need)) }'; then
    can_create="false"
fi
if awk -v a="${block_available}" -v need="${needed_boot_gbs}" 'BEGIN { exit !(a < need) }'; then
    can_create="false"
fi

echo
if [[ "${can_create}" == "true" ]]; then
    echo "RESULT: OK to create a small OKE test cluster from quota/capacity perspective."
    echo "NEXT: create/select a cluster in the target VCN, then run:"
    echo "      ./deploy/oke/deploy-oke.sh"
    echo "      ./deploy/oke/deploy-langfuse.sh --check"
    exit 0
fi

echo "RESULT: blocked for small OKE cluster creation. Review failed quota/capacity checks above."
exit 1
