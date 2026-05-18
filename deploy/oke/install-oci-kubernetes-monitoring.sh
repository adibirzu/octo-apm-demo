#!/usr/bin/env bash
# Install Oracle's OCI Kubernetes Monitoring solution for the current cluster.
#
# This follows the oracle-quickstart/oci-kubernetes-monitoring Helm path while
# keeping all resources scoped to the Octo emdemo compartment and existing Log
# Analytics namespace/log group.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy/oke/install-oci-kubernetes-monitoring.sh

Installs or upgrades Oracle OCI Kubernetes Monitoring for the current OKE
cluster. It creates/reuses the Log Analytics Kubernetes entity and a short-lived
Management Agent install key, then applies the Helm chart with Octo emdemo
compartment and Log Analytics settings.

Optional hardening:
  CHART_URL=<pinned-release-url>
  CHART_SHA256=<sha256-of-chart-tgz>
  MGMT_AGENT_STATE_STORAGE=emptyDir|persistent
  APPLY=false                 # render and validate only; no OCI/K8s writes
  SERVER_DRY_RUN=false        # skip kubectl server-side dry-run
  RENDERED_MANIFEST=<path>    # optional rendered Helm manifest output
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
: "${MONITORING_NAMESPACE:=oci-onm}"
: "${RELEASE_NAME:=oci-kubernetes-monitoring}"
: "${CHART_URL:=https://github.com/oracle-quickstart/oci-kubernetes-monitoring/releases/download/oci-onm-4.2.1/helm-chart.tgz}"
: "${CHART_SHA256:=d61d3cd9c72deefc1dbd83cedd5f1cf775bfc33c24d4c1206fd19b4e7b4ca8fc}"
: "${MGMT_AGENT_INSTALL_KEY_NAME:=octo-apm-demo-oke-mgmt-agent}"
: "${MGMT_AGENT_INSTALL_KEY_B64:=}"
: "${MGMT_AGENT_STATE_STORAGE:=emptyDir}"
: "${OCI_ONM_ENABLE_SERVICE_LOGS:=false}"
: "${APPLY:=true}"
: "${SERVER_DRY_RUN:=true}"
: "${SKIP_CONTEXT_CHECK:=false}"
: "${RENDERED_MANIFEST:=}"

require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}

require_tool oci
require_tool jq
require_tool kubectl
require_tool helm
require_tool curl
require_tool tar
require_tool perl

case "${MGMT_AGENT_STATE_STORAGE}" in
    emptyDir|persistent)
        ;;
    *)
        echo "MGMT_AGENT_STATE_STORAGE must be emptyDir or persistent." >&2
        exit 1
        ;;
esac

case "${OCI_ONM_ENABLE_SERVICE_LOGS}" in
    true|false)
        ;;
    *)
        echo "OCI_ONM_ENABLE_SERVICE_LOGS must be true or false." >&2
        exit 1
        ;;
esac

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

read_output_value() {
    local jq_expr="$1"
    local label="$2"
    local value
    if ! value="$(jq -er "${jq_expr} // empty" "${OUTPUTS_FILE}")"; then
        echo "Missing required outputs.json value: ${label}" >&2
        exit 1
    fi
    printf '%s' "${value}"
}

COMPARTMENT_ID="$(read_output_value '.deployment_compartment_id.value' 'deployment_compartment_id.value')"
LA_NAMESPACE="$(read_output_value '.log_analytics.value.namespace' 'log_analytics.value.namespace')"
LA_LOG_GROUP_ID="$(read_output_value '.log_analytics.value.log_group_id' 'log_analytics.value.log_group_id')"
CLUSTER_ID="$(oci ce cluster list --profile "${OCI_PROFILE}" --compartment-id "${COMPARTMENT_ID}" --all --output json |
    jq -r --arg name "${OKE_CLUSTER_NAME}" '.data[] | select(.name == $name and ."lifecycle-state" == "ACTIVE") | .id' | head -1)"

if [[ -z "${CLUSTER_ID}" ]]; then
    echo "No ACTIVE cluster named ${OKE_CLUSTER_NAME} in the emdemo compartment." >&2
    exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

cluster_file="${tmp}/cluster.json"
oci ce cluster get --profile "${OCI_PROFILE}" --cluster-id "${CLUSTER_ID}" --output json > "${cluster_file}"
CLUSTER_CREATED_RAW="$(jq -r '.data.metadata."time-created" // .data."time-created" // .data."defined-tags"."Oracle-Tags".CreatedOn // empty' "${cluster_file}")"
if [[ -z "${CLUSTER_CREATED_RAW}" || "${CLUSTER_CREATED_RAW}" == "null" ]]; then
    echo "Could not read OKE cluster creation time for ${OKE_CLUSTER_NAME}." >&2
    exit 1
fi
read -r CLUSTER_CREATED CLUSTER_CREATED_SUFFIX < <(python3 - "${CLUSTER_CREATED_RAW}" <<'PY'
from datetime import datetime, timezone
import sys

raw = sys.argv[1].replace("Z", "+00:00")
dt = datetime.fromisoformat(raw)
utc = dt.astimezone(timezone.utc)
print(utc.strftime("%Y-%m-%dT%H:%M:%SZ"), utc.strftime("%Y%m%dT%H%M%SZ"))
PY
)
K8S_VERSION="$(jq -r '.data."kubernetes-version"' "${cluster_file}")"
ENTITY_NAME="${OKE_CLUSTER_NAME}_${CLUSTER_CREATED_SUFFIX}"

ensure_mgmt_agent_install_key_b64() {
    if [[ -n "${MGMT_AGENT_INSTALL_KEY_B64}" ]]; then
        return
    fi

    if [[ "${APPLY}" != "true" ]]; then
        MGMT_AGENT_INSTALL_KEY_B64="$(printf '%s' "dry-run-management-agent-install-key" | base64 | tr -d '\n')"
        echo "  DRY RUN only: using placeholder Management Agent install key content."
        return
    fi

    local key_id expires_at key_file
    key_id="$(oci management-agent install-key list \
        --profile "${OCI_PROFILE}" \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${MGMT_AGENT_INSTALL_KEY_NAME}" \
        --lifecycle-state ACTIVE \
        --all \
        --output json |
        jq -r --arg name "${MGMT_AGENT_INSTALL_KEY_NAME}" '
            (if (.data | type) == "array" then .data else (.data.items // []) end)
            | .[]
            | select(."display-name" == $name)
            | .id
        ' | head -1)"

    if [[ -z "${key_id}" ]]; then
        expires_at="$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
)"
        key_id="$(oci management-agent install-key create \
            --profile "${OCI_PROFILE}" \
            --compartment-id "${COMPARTMENT_ID}" \
            --display-name "${MGMT_AGENT_INSTALL_KEY_NAME}" \
            --allowed-key-install-count 20 \
            --time-expires "${expires_at}" \
            --wait-for-state ACTIVE \
            --max-wait-seconds 600 \
            --output json |
            jq -r '.data.id')"
        echo "  Created Management Agent install key ${MGMT_AGENT_INSTALL_KEY_NAME}"
    else
        echo "  Reusing Management Agent install key ${MGMT_AGENT_INSTALL_KEY_NAME}"
    fi

    key_file="${tmp}/mgmt-agent-install-key.txt"
    oci management-agent install-key get-install-key-content \
        --profile "${OCI_PROFILE}" \
        --management-agent-install-key-id "${key_id}" \
        --file "${key_file}" >/dev/null
    MGMT_AGENT_INSTALL_KEY_B64="$(base64 < "${key_file}" | tr -d '\n')"
}

metadata_file="${tmp}/entity_metadata.json"
cat > "${metadata_file}" <<JSON
{
  "items": [
    {"name": "cluster", "value": "${ENTITY_NAME}", "type": "k8s_solution"},
    {"name": "cluster_date", "value": "${CLUSTER_CREATED}", "type": "k8s_solution"},
    {"name": "cluster_name", "value": "${OKE_CLUSTER_NAME}", "type": "k8s_solution"},
    {"name": "cluster_ocid", "value": "${CLUSTER_ID}", "type": "k8s_solution"},
    {"name": "deployment_stack_ocid", "value": "NA", "type": "k8s_solution"},
    {"name": "deployment_status", "value": "NA", "type": "k8s_solution"},
    {"name": "k8s_version", "value": "${K8S_VERSION}", "type": "k8s_solution"},
    {"name": "metrics_namespace", "value": "mgmtagent_kubernetes_metrics", "type": "k8s_solution"},
    {"name": "name", "value": "${ENTITY_NAME}", "type": "k8s_solution"},
    {"name": "onm_compartment", "value": "${COMPARTMENT_ID}", "type": "k8s_solution"},
    {"name": "solution_type", "value": "OKE", "type": "k8s_solution"}
  ]
}
JSON

echo "Ensuring Log Analytics Kubernetes entity..."
entity_list_file="${tmp}/entities.json"
oci log-analytics entity list \
    --profile "${OCI_PROFILE}" \
    --namespace-name "${LA_NAMESPACE}" \
    --compartment-id "${COMPARTMENT_ID}" \
    --cloud-resource-id "${CLUSTER_ID}" \
    --all \
    --output json > "${entity_list_file}" 2>/dev/null || true
ENTITY_ID="$(jq -r '.data.items[0].id // empty' "${entity_list_file}")"
ENTITY_CURRENT_NAME="$(jq -r '.data.items[0].name // empty' "${entity_list_file}")"
if [[ -z "${ENTITY_ID}" ]]; then
    oci log-analytics entity list \
        --profile "${OCI_PROFILE}" \
        --namespace-name "${LA_NAMESPACE}" \
        --compartment-id "${COMPARTMENT_ID}" \
        --name "${ENTITY_NAME}" \
        --all \
        --output json > "${entity_list_file}" 2>/dev/null || true
    ENTITY_ID="$(jq -r '.data.items[0].id // empty' "${entity_list_file}")"
    ENTITY_CURRENT_NAME="$(jq -r '.data.items[0].name // empty' "${entity_list_file}")"
fi
if [[ -z "${ENTITY_ID}" ]]; then
    if [[ "${APPLY}" == "true" ]]; then
        ENTITY_ID="$(oci log-analytics entity create \
            --profile "${OCI_PROFILE}" \
            --namespace-name "${LA_NAMESPACE}" \
            --compartment-id "${COMPARTMENT_ID}" \
            --entity-type-name omc_kubernetes_cluster \
            --name "${ENTITY_NAME}" \
            --cloud-resource-id "${CLUSTER_ID}" \
            --metadata "file://${metadata_file}" \
            --output json |
            jq -r '.data.id')"
        echo "  Created entity for ${OKE_CLUSTER_NAME}"
    else
        ENTITY_ID="dry-run-log-analytics-entity-id"
        echo "  DRY RUN only: using placeholder Log Analytics entity id."
    fi
else
    if [[ "${ENTITY_CURRENT_NAME}" != "${ENTITY_NAME}" ]]; then
        # Log Analytics does not currently support renaming entities. Reuse the
        # existing cloud-resource-id match so upgrades do not create duplicates
        # or fail after a legacy entity name has been registered.
        echo "  Reusing existing entity name ${ENTITY_CURRENT_NAME}; Log Analytics entity names cannot be renamed."
        ENTITY_NAME="${ENTITY_CURRENT_NAME}"
    else
        echo "  Reusing entity for ${OKE_CLUSTER_NAME}"
    fi
fi

ensure_mgmt_agent_install_key_b64

values_file="${tmp}/override-values.yaml"
cat > "${values_file}" <<YAML
global:
  kubernetesClusterID: "${CLUSTER_ID}"
  kubernetesClusterName: "${OKE_CLUSTER_NAME}"

oci-onm-logan:
  ociLANamespace: "${LA_NAMESPACE}"
  ociLALogGroupID: "${LA_LOG_GROUP_ID}"
  ociLAClusterEntityID: "${ENTITY_ID}"
  k8sDiscovery:
    infra:
      enable_service_log: ${OCI_ONM_ENABLE_SERVICE_LOGS}

oci-onm-mgmt-agent:
  deployMetricServer: false
  kubernetesCluster:
    compartmentId: "${COMPARTMENT_ID}"
    monitoringNamespace: "mgmtagent_kubernetes_metrics"
    name: "${OKE_CLUSTER_NAME}"
    namespace: "*"
  mgmtagent:
    installKeyFileContent: "${MGMT_AGENT_INSTALL_KEY_B64}"
YAML
chmod 600 "${values_file}"

echo "Installing/upgrading OCI Kubernetes Monitoring Helm chart..."
chart_path="${tmp}/helm-chart.tgz"
curl -fsSL -o "${chart_path}" "${CHART_URL}"
actual_sha="$(shasum -a 256 "${chart_path}" | awk '{print $1}')"
if [[ "${actual_sha}" != "${CHART_SHA256}" ]]; then
    echo "Downloaded chart SHA256 mismatch for ${CHART_URL}" >&2
    echo "Expected: ${CHART_SHA256}" >&2
    echo "Actual:   ${actual_sha}" >&2
    exit 1
fi

tar -xzf "${chart_path}" -C "${tmp}"
if [[ -f "${tmp}/Chart.yaml" ]]; then
    chart_ref="${tmp}"
elif [[ -f "${tmp}/charts/oci-onm/Chart.yaml" ]]; then
    chart_ref="${tmp}/charts/oci-onm"
else
    echo "Downloaded OCI Kubernetes Monitoring chart does not contain Chart.yaml." >&2
    exit 1
fi

if [[ "${MGMT_AGENT_STATE_STORAGE}" == "emptyDir" ]]; then
    mgmt_agent_statefulset="$(find "${tmp}" -path '*/mgmt-agent/templates/mgmt-agent-statefulset.yaml' -print -quit)"
    if [[ -z "${mgmt_agent_statefulset}" ]]; then
        echo "Could not find Management Agent StatefulSet template in downloaded chart." >&2
        exit 1
    fi

    # The upstream chart always creates a Block Volume PVC for the Management
    # Agent. The Octo demo cluster is intentionally small and private, so the
    # default install uses ephemeral agent state to avoid provisioning a volume.
    perl -0pi -e 's/(      volumes:\n)/$1        - name: mgmtagent-pvc\n          emptyDir: {}\n/' "${mgmt_agent_statefulset}"
    perl -0pi -e 's/\n  volumeClaimTemplates:\n    - metadata:\n        name: mgmtagent-pvc\n      spec:\n        accessModes: \[ "ReadWriteOnce" \]\n        \{\{- if \.Values\.deployment\.storageClass \}\}\n        storageClassName: \{\{ \.Values\.deployment\.storageClass \}\}\n        \{\{- end \}\}\n        resources:\n          requests:\n            storage: \{\{ \.Values\.deployment\.resource\.request\.storage \}\}\n//s' "${mgmt_agent_statefulset}"
    echo "  Patched Management Agent StatefulSet to use emptyDir state."
fi

helm dependency build "${chart_ref}" >/dev/null

rendered_manifest="${RENDERED_MANIFEST:-${tmp}/rendered-manifest.yaml}"
helm template "${RELEASE_NAME}" "${chart_ref}" \
    --namespace "${MONITORING_NAMESPACE}" \
    --values "${values_file}" \
    > "${rendered_manifest}"
chmod 600 "${rendered_manifest}"

if [[ "${OCI_ONM_ENABLE_SERVICE_LOGS}" != "true" ]]; then
    if grep -Eq -- '--enable_service_log|--rms_template_base64_encoded' "${rendered_manifest}"; then
        echo "Rendered OCI Kubernetes Monitoring chart still enables Resource Manager service-log collection." >&2
        exit 1
    fi
fi

if [[ "${SERVER_DRY_RUN}" == "true" ]]; then
    echo "Server-side dry-run for OCI Kubernetes Monitoring manifests..."
    if kubectl get namespace "${MONITORING_NAMESPACE}" >/dev/null 2>&1; then
        kubectl apply --dry-run=server -f "${rendered_manifest}" >/dev/null
    else
        echo "  Namespace ${MONITORING_NAMESPACE} does not exist yet; validating namespace creation only."
        kubectl create namespace "${MONITORING_NAMESPACE}" --dry-run=server -o yaml >/dev/null
    fi
fi

if [[ "${APPLY}" != "true" ]]; then
    echo "DRY RUN only: rendered OCI Kubernetes Monitoring manifest successfully."
    if [[ -n "${RENDERED_MANIFEST}" ]]; then
        echo "  Rendered manifest: ${RENDERED_MANIFEST}"
    fi
    exit 0
fi

kubectl create namespace "${MONITORING_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl label namespace "${MONITORING_NAMESPACE}" app.kubernetes.io/managed-by=Helm --overwrite >/dev/null
kubectl annotate namespace "${MONITORING_NAMESPACE}" \
    "meta.helm.sh/release-name=${RELEASE_NAME}" \
    "meta.helm.sh/release-namespace=${MONITORING_NAMESPACE}" \
    --overwrite >/dev/null

helm upgrade --install "${RELEASE_NAME}" "${chart_ref}" \
    --namespace "${MONITORING_NAMESPACE}" \
    --values "${values_file}" \
    --rollback-on-failure \
    --history-max 5 \
    --wait \
    --timeout 15m

echo "OCI Kubernetes Monitoring installed in namespace ${MONITORING_NAMESPACE}."
