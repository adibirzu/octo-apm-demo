#!/usr/bin/env bash
# Prepare the existing emdemo OCI Load Balancer for an OKE cutover.
#
# Default mode is dry-run. With --apply, this creates/updates dedicated OKE
# backend sets and attaches current OKE worker private IPs on the NodePort
# services. It does not change live host routing unless --cutover is also set.
# Use --round-robin-active with --apply to add the OKE NodePort backends to the
# active VM backend sets without changing listener or host-routing policies.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUTS_FILE="${OUTPUTS_FILE:-${REPO_ROOT}/credentials/emdemo/outputs.json}"

: "${OCI_PROFILE:=emdemo}"
: "${SHOP_BACKEND_SET:=oke_shop_nodeport}"
: "${CRM_BACKEND_SET:=oke_admin_nodeport}"
: "${ACTIVE_SHOP_BACKEND_SET:=shop}"
: "${ACTIVE_CRM_BACKEND_SET:=crm}"
: "${SHOP_VM_IP:=<VM_SHOP_PRIV_IP>}"
: "${CRM_VM_IP:=<VM_CRM_PRIV_IP>}"
: "${VM_PORT:=8080}"
: "${SHOP_NODEPORT:=30080}"
: "${CRM_NODEPORT:=30081}"
: "${ROUTING_POLICY_NAME:=host_routing}"
: "${OKE_CLUSTER_NAME:=octo-apm-demo-oke}"
: "${SKIP_CONTEXT_CHECK:=false}"

APPLY=false
CUTOVER=false
ROLLBACK_VM=false
ROUND_ROBIN_ACTIVE=false
ROLLBACK_ACTIVE_VM=false

usage() {
    cat <<EOF
Usage: $0 [--apply] [--cutover | --rollback-vm | --round-robin-active | --rollback-active-vm]

  --apply               Mutate the existing OCI LB. Without this, print the plan.
  --cutover             Route drones/admin host rules to dedicated OKE backend sets.
  --rollback-vm         Route drones/admin host rules back to VM backend sets (shop/crm).
  --round-robin-active  Add OKE NodePort backends to active shop/crm backend sets.
                        This keeps listener 443 and host-routing unchanged.
  --rollback-active-vm  Restore active shop/crm backend sets to VM-only backends.

Without --apply the script only prints the planned backend set changes.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=true
            shift
            ;;
        --cutover)
            CUTOVER=true
            APPLY=true
            shift
            ;;
        --rollback-vm)
            ROLLBACK_VM=true
            shift
            ;;
        --round-robin-active)
            ROUND_ROBIN_ACTIVE=true
            shift
            ;;
        --rollback-active-vm)
            ROLLBACK_ACTIVE_VM=true
            APPLY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

active_modes=0
for mode in "${CUTOVER}" "${ROLLBACK_VM}" "${ROUND_ROBIN_ACTIVE}" "${ROLLBACK_ACTIVE_VM}"; do
    if [[ "${mode}" == "true" ]]; then
        active_modes=$((active_modes + 1))
    fi
done
if [[ "${active_modes}" -gt 1 ]]; then
    echo "--cutover, --rollback-vm, --round-robin-active, and --rollback-active-vm are mutually exclusive." >&2
    exit 1
fi

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

require_tool oci
require_tool jq
require_tool kubectl

if [[ "${SKIP_CONTEXT_CHECK}" != "true" ]]; then
    current_context="$(kubectl config current-context 2>/dev/null || true)"
    if [[ "${current_context}" != "${OKE_CLUSTER_NAME}" ]]; then
        echo "Current kubectl context is '${current_context:-unset}', expected '${OKE_CLUSTER_NAME}'." >&2
        echo "Set SKIP_CONTEXT_CHECK=true only after verifying the target cluster." >&2
        exit 1
    fi
fi

if [[ ! -f "${OUTPUTS_FILE}" ]]; then
    echo "Missing outputs file: ${OUTPUTS_FILE}" >&2
    exit 1
fi

LB_ID="$(jq -r '.load_balancer.value.id' "${OUTPUTS_FILE}")"
if [[ -z "${LB_ID}" || "${LB_ID}" == "null" ]]; then
    echo "Could not read load balancer id from ${OUTPUTS_FILE}." >&2
    exit 1
fi

NODE_IPS=()
while IFS= read -r node_ip; do
    NODE_IPS+=("${node_ip}")
done < <(
    kubectl get nodes -o json |
        jq -r '.items[]
            | select((.status.conditions[]? | select(.type == "Ready") | .status) == "True")
            | .status.addresses[]
            | select(.type == "InternalIP")
            | .address' |
        sort -u
)

if [[ "${#NODE_IPS[@]}" -eq 0 ]]; then
    echo "No Ready OKE node InternalIP values found in the current kubectl context." >&2
    exit 1
fi

backend_json() {
    local port="$1"
    printf '%s\n' "${NODE_IPS[@]}" |
        jq -R -s --argjson port "${port}" 'split("\n") | map(select(length > 0) | {
            ipAddress: .,
            port: $port,
            weight: 1,
            backup: false,
            drain: false,
            offline: false
        })'
}

mixed_backend_json() {
    local vm_ip="$1"
    local vm_port="$2"
    local nodeport="$3"
    {
        jq -n --arg ip "${vm_ip}" --argjson port "${vm_port}" '{
            ipAddress: $ip,
            port: $port,
            weight: 1,
            backup: false,
            drain: false,
            offline: false
        }'
        printf '%s\n' "${NODE_IPS[@]}" |
            jq -R -s --argjson port "${nodeport}" 'split("\n") | map(select(length > 0) | {
                ipAddress: .,
                port: $port,
                weight: 1,
                backup: false,
                drain: false,
                offline: false
            }) | .[]'
    } | jq -s '.'
}

vm_backend_json() {
    local vm_ip="$1"
    local vm_port="$2"
    jq -n --arg ip "${vm_ip}" --argjson port "${vm_port}" '[{
        ipAddress: $ip,
        port: $port,
        weight: 1,
        backup: false,
        drain: false,
        offline: false
    }]'
}

backend_set_exists() {
    local backend_set="$1"
    oci_json lb backend-set get \
        --load-balancer-id "${LB_ID}" \
        --backend-set-name "${backend_set}" >/dev/null 2>&1
}

update_backend_set_use_backend_ports() {
    local backend_set="$1"
    local backends="$2"

    if [[ "${APPLY}" != "true" ]]; then
        return
    fi

    oci_plain lb backend-set update \
        --load-balancer-id "${LB_ID}" \
        --backend-set-name "${backend_set}" \
        --policy ROUND_ROBIN \
        --backends "${backends}" \
        --health-checker-protocol HTTP \
        --health-checker-url-path /ready \
        --health-checker-return-code 200 \
        --health-checker-response-body-regex '.*' \
        --health-checker-interval-in-ms 10000 \
        --health-checker-timeout-in-ms 3000 \
        --health-checker-retries 3 \
        --force \
        --wait-for-state SUCCEEDED \
        --max-wait-seconds 600 >/dev/null
}

update_backend_set_fixed_health_port() {
    local backend_set="$1"
    local backends="$2"
    local health_port="$3"

    if [[ "${APPLY}" != "true" ]]; then
        return
    fi

    oci_plain lb backend-set update \
        --load-balancer-id "${LB_ID}" \
        --backend-set-name "${backend_set}" \
        --policy ROUND_ROBIN \
        --backends "${backends}" \
        --health-checker-protocol HTTP \
        --health-checker-port "${health_port}" \
        --health-checker-url-path /ready \
        --health-checker-return-code 200 \
        --health-checker-response-body-regex '.*' \
        --health-checker-interval-in-ms 10000 \
        --health-checker-timeout-in-ms 3000 \
        --health-checker-retries 3 \
        --force \
        --wait-for-state SUCCEEDED \
        --max-wait-seconds 600 >/dev/null
}

ensure_backend_set() {
    local backend_set="$1"
    local nodeport="$2"
    local backends
    backends="$(backend_json "${nodeport}")"

    echo "Planned ${backend_set} backends on port ${nodeport}:"
    printf '%s\n' "${NODE_IPS[@]}" | sed 's/^/  - /'

    if [[ "${APPLY}" != "true" ]]; then
        return
    fi

    if backend_set_exists "${backend_set}"; then
        oci_plain lb backend-set update \
            --load-balancer-id "${LB_ID}" \
            --backend-set-name "${backend_set}" \
            --policy ROUND_ROBIN \
            --backends "${backends}" \
            --health-checker-protocol HTTP \
            --health-checker-port "${nodeport}" \
            --health-checker-url-path /ready \
            --health-checker-return-code 200 \
            --health-checker-response-body-regex '.*' \
            --health-checker-interval-in-ms 10000 \
            --health-checker-timeout-in-ms 3000 \
            --health-checker-retries 3 \
            --force \
            --wait-for-state SUCCEEDED \
            --max-wait-seconds 600 >/dev/null
        echo "  Updated backend set ${backend_set}"
    else
        oci_plain lb backend-set create \
            --load-balancer-id "${LB_ID}" \
            --name "${backend_set}" \
            --policy ROUND_ROBIN \
            --backends "${backends}" \
            --health-checker-protocol HTTP \
            --health-checker-port "${nodeport}" \
            --health-checker-url-path /ready \
            --health-checker-return-code 200 \
            --health-checker-response-body-regex '.*' \
            --health-checker-interval-in-ms 10000 \
            --health-checker-timeout-in-ms 3000 \
            --health-checker-retries 3 \
            --wait-for-state SUCCEEDED \
            --max-wait-seconds 600 >/dev/null
        echo "  Created backend set ${backend_set}"
    fi
}

ensure_active_round_robin_backend_set() {
    local backend_set="$1"
    local vm_ip="$2"
    local nodeport="$3"
    local backends
    backends="$(mixed_backend_json "${vm_ip}" "${VM_PORT}" "${nodeport}")"

    echo "Planned active round-robin ${backend_set} backends:"
    echo "  - ${vm_ip}:${VM_PORT} (VM)"
    printf '%s\n' "${NODE_IPS[@]}" | sed "s/$/:${nodeport} (OKE NodePort)/" | sed 's/^/  - /'
    echo "  Health checker: HTTP /ready on each backend object's own port"

    update_backend_set_use_backend_ports "${backend_set}" "${backends}"
    if [[ "${APPLY}" == "true" ]]; then
        echo "  Updated active backend set ${backend_set}"
    fi
}

restore_active_vm_backend_set() {
    local backend_set="$1"
    local vm_ip="$2"
    local backends
    backends="$(vm_backend_json "${vm_ip}" "${VM_PORT}")"

    echo "Planned active VM-only ${backend_set} backends:"
    echo "  - ${vm_ip}:${VM_PORT} (VM)"
    echo "  Health checker: HTTP /ready on fixed port ${VM_PORT}"

    update_backend_set_fixed_health_port "${backend_set}" "${backends}" "${VM_PORT}"
    if [[ "${APPLY}" == "true" ]]; then
        echo "  Restored active backend set ${backend_set} to VM-only"
    fi
}

backend_set_health_status() {
    local backend_set="$1"
    oci_json lb backend-set-health get \
        --load-balancer-id "${LB_ID}" \
        --backend-set-name "${backend_set}" |
        jq -r '.data.status // "UNKNOWN"'
}

wait_backend_set_healthy() {
    local backend_set="$1"
    local status="UNKNOWN"
    local attempt
    if [[ "${APPLY}" != "true" ]]; then
        return
    fi
    for attempt in $(seq 1 30); do
        status="$(backend_set_health_status "${backend_set}")"
        if [[ "${status}" == "OK" ]]; then
            echo "  Backend set ${backend_set} health: OK"
            return
        fi
        sleep 10
    done
    echo "Backend set ${backend_set} did not become healthy; last status was ${status}." >&2
    exit 1
}

set_route_targets() {
    local shop_target="$1"
    local crm_target="$2"
    local tmp
    tmp="$(mktemp)"
    trap 'rm -f "${tmp}"' RETURN

    oci_json lb routing-policy get \
        --load-balancer-id "${LB_ID}" \
        --routing-policy-name "${ROUTING_POLICY_NAME}" |
        jq --arg shop "${shop_target}" --arg crm "${crm_target}" '
            .data.rules
            | map(
                if .name == "shop_host" then
                    .actions = (.actions | map(if .name == "FORWARD_TO_BACKENDSET" then .["backend-set-name"] = $shop else . end))
                elif .name == "crm_host" then
                    .actions = (.actions | map(if .name == "FORWARD_TO_BACKENDSET" then .["backend-set-name"] = $crm else . end))
                else
                    .
                end
            )
        ' > "${tmp}"

    oci_plain lb routing-policy update \
        --load-balancer-id "${LB_ID}" \
        --routing-policy-name "${ROUTING_POLICY_NAME}" \
        --condition-language-version V1 \
        --rules "file://${tmp}" \
        --force \
        --wait-for-state SUCCEEDED \
        --max-wait-seconds 600 >/dev/null
}

print_routing() {
    oci_json lb routing-policy get \
        --load-balancer-id "${LB_ID}" \
        --routing-policy-name "${ROUTING_POLICY_NAME}" |
        jq -r '.data.rules[] | "\(.name): \(.actions[] | select(.name == "FORWARD_TO_BACKENDSET") | .["backend-set-name"])"'
}

echo "================================================================"
echo " Existing OCI LB backend preparation for OKE"
echo "   LB:          ${LB_ID}"
echo "   Cluster:     ${OKE_CLUSTER_NAME}"
echo "   Shop set:    ${SHOP_BACKEND_SET} -> ${SHOP_NODEPORT}"
echo "   Admin set:   ${CRM_BACKEND_SET} -> ${CRM_NODEPORT}"
echo "   Active shop: ${ACTIVE_SHOP_BACKEND_SET} -> ${SHOP_VM_IP}:${VM_PORT} + OKE:${SHOP_NODEPORT}"
echo "   Active admin: ${ACTIVE_CRM_BACKEND_SET} -> ${CRM_VM_IP}:${VM_PORT} + OKE:${CRM_NODEPORT}"
echo "   Apply:       ${APPLY}"
echo "   Cutover:     ${CUTOVER}"
echo "   Rollback VM: ${ROLLBACK_VM}"
echo "   RR active:   ${ROUND_ROBIN_ACTIVE}"
echo "   Active VM:   ${ROLLBACK_ACTIVE_VM}"
echo "================================================================"

if [[ "${ROUND_ROBIN_ACTIVE}" == "true" ]]; then
    ensure_active_round_robin_backend_set "${ACTIVE_SHOP_BACKEND_SET}" "${SHOP_VM_IP}" "${SHOP_NODEPORT}"
    ensure_active_round_robin_backend_set "${ACTIVE_CRM_BACKEND_SET}" "${CRM_VM_IP}" "${CRM_NODEPORT}"
    wait_backend_set_healthy "${ACTIVE_SHOP_BACKEND_SET}"
    wait_backend_set_healthy "${ACTIVE_CRM_BACKEND_SET}"
    if [[ "${APPLY}" == "true" ]]; then
        echo "Active backend sets now include VM and OKE NodePort backends."
    else
        echo "Active backend sets would include VM and OKE NodePort backends."
    fi
elif [[ "${ROLLBACK_ACTIVE_VM}" == "true" ]]; then
    restore_active_vm_backend_set "${ACTIVE_SHOP_BACKEND_SET}" "${SHOP_VM_IP}"
    restore_active_vm_backend_set "${ACTIVE_CRM_BACKEND_SET}" "${CRM_VM_IP}"
    wait_backend_set_healthy "${ACTIVE_SHOP_BACKEND_SET}"
    wait_backend_set_healthy "${ACTIVE_CRM_BACKEND_SET}"
    echo "Active backend sets now use VM-only backends."
else
    ensure_backend_set "${SHOP_BACKEND_SET}" "${SHOP_NODEPORT}"
    ensure_backend_set "${CRM_BACKEND_SET}" "${CRM_NODEPORT}"
    wait_backend_set_healthy "${SHOP_BACKEND_SET}"
    wait_backend_set_healthy "${CRM_BACKEND_SET}"
fi

if [[ "${CUTOVER}" == "true" ]]; then
    set_route_targets "${SHOP_BACKEND_SET}" "${CRM_BACKEND_SET}"
    echo "Host routing now points to OKE backend sets."
elif [[ "${ROLLBACK_VM}" == "true" ]]; then
    set_route_targets shop crm
    echo "Host routing now points to the VM backend sets."
else
    echo "Host routing was not changed."
fi

echo
echo "Current host routing:"
print_routing
