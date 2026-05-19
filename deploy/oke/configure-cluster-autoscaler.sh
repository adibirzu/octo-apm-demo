#!/usr/bin/env bash
# Configure the OCI Cluster Autoscaler managed add-on for the octo-apm-demo OKE cluster.
#
# Phase 7 D-04: enable Cluster Autoscaler on the existing emdemo worker node pool
# with min=2, max=4 nodes. Dry-run by default — only mutates OCI state when
# invoked with --apply AND the operator confirms the cluster name interactively.
#
# Pattern analog: deploy/oke/install-oci-kubernetes-monitoring.sh (lines 1-103)
# — same shebang, set -euo pipefail, usage(), tool checks, and context guard.
# Opposite default for APPLY: dry-run is the safe operator hand-off here.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy/oke/configure-cluster-autoscaler.sh [--apply]

Configures the OKE managed Cluster Autoscaler add-on against the existing
worker node pool. Idempotent: detects existing add-on via `oci ce cluster
list-addons` and switches between `install-addon` and `update-addon`
automatically.

Required environment:
  COMPARTMENT_ID        OCI compartment containing the OKE cluster
  OKE_NODE_POOL_OCID    Worker node pool OCID (envsubst into config JSON)

Optional environment (defaults shown):
  OCI_PROFILE=emdemo
  OCI_REGION=us-phoenix-1
  OKE_CLUSTER_NAME=octo-apm-demo-oke
  APPLY=false           (default: dry-run; pass --apply to mutate)
  SKIP_CONTEXT_CHECK=false

Modes:
  (no args)   Dry-run: prints the resolved `oci ce cluster install-addon`
              or `update-addon` command, including the rendered JSON config
              body. No OCI state is mutated.
  --apply     Mutate: prompts the operator to type the cluster name to
              confirm, then issues the install-addon (first run) or
              update-addon (subsequent runs) call.
  -h|--help   Print this help.

Safety:
  - No live OCIDs are committed to the repo. OKE_NODE_POOL_OCID is supplied
    by the operator at apply time and substituted into the JSON via envsubst.
  - APPLY defaults to false; the operator must opt in via --apply.
  - The operator must type the exact cluster name at the read -p confirm
    prompt before any mutation occurs.

See also: deploy/oke/cluster-autoscaler-config.json (the JSON config body).
EOF
}

case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
    --apply)
        APPLY=true
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

: "${OCI_PROFILE:=emdemo}"
: "${OCI_REGION:=us-phoenix-1}"
: "${OKE_CLUSTER_NAME:=octo-apm-demo-oke}"
: "${APPLY:=false}"
: "${SKIP_CONTEXT_CHECK:=false}"

require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Missing required tool: $1" >&2
        exit 1
    }
}

require_tool oci
require_tool jq
require_tool kubectl
require_tool envsubst

if [[ -z "${COMPARTMENT_ID:-}" ]]; then
    echo "COMPARTMENT_ID is required (the compartment containing the OKE cluster)." >&2
    exit 1
fi

if [[ -z "${OKE_NODE_POOL_OCID:-}" ]]; then
    echo "OKE_NODE_POOL_OCID is required (the worker node pool OCID to autoscale)." >&2
    exit 1
fi

if [[ "${SKIP_CONTEXT_CHECK}" != "true" ]]; then
    current_context="$(kubectl config current-context 2>/dev/null || true)"
    if [[ "${current_context}" != "${OKE_CLUSTER_NAME}" ]]; then
        echo "Current kubectl context is '${current_context:-unset}', expected '${OKE_CLUSTER_NAME}'." >&2
        echo "Set SKIP_CONTEXT_CHECK=true only after verifying the target cluster." >&2
        exit 1
    fi
fi

CONFIG_TEMPLATE="${SCRIPT_DIR}/cluster-autoscaler-config.json"
if [[ ! -f "${CONFIG_TEMPLATE}" ]]; then
    echo "Missing CA config template: ${CONFIG_TEMPLATE}" >&2
    exit 1
fi

echo "Resolving CLUSTER_ID for ${OKE_CLUSTER_NAME} in compartment ${COMPARTMENT_ID}..."
CLUSTER_ID="$(oci ce cluster list \
    --profile "${OCI_PROFILE}" \
    --region "${OCI_REGION}" \
    --compartment-id "${COMPARTMENT_ID}" \
    --name "${OKE_CLUSTER_NAME}" \
    --all \
    --output json 2>/dev/null |
    jq -r '.data[] | select(."lifecycle-state" == "ACTIVE") | .id' | head -1 || true)"

if [[ -z "${CLUSTER_ID}" ]]; then
    if [[ "${APPLY}" == "true" ]]; then
        echo "No ACTIVE cluster named ${OKE_CLUSTER_NAME} in compartment ${COMPARTMENT_ID}." >&2
        exit 1
    fi
    echo "  DRY RUN: cluster lookup skipped (no live OCI credentials); using placeholder."
    CLUSTER_ID="ocid1.cluster.oc1..dry-run-placeholder"
fi

# Render the JSON config with the operator-supplied node pool OCID. envsubst
# only expands ${OKE_NODE_POOL_OCID} (and other env-prefixed vars) — no live
# OCID is ever read from the repo file.
tmp_config="$(mktemp -t cluster-autoscaler-config.XXXXXX.json)"
trap 'rm -f "${tmp_config}"' EXIT
envsubst < "${CONFIG_TEMPLATE}" > "${tmp_config}"

if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "${tmp_config}" >/dev/null 2>&1; then
    echo "Rendered CA config is not valid JSON: ${tmp_config}" >&2
    exit 1
fi

echo "Probing existing add-ons via oci ce cluster list-addons..."
EXISTING_ADDON=""
if [[ "${APPLY}" == "true" || "${CLUSTER_ID}" != "ocid1.cluster.oc1..dry-run-placeholder" ]]; then
    EXISTING_ADDON="$(oci ce cluster list-addons \
        --profile "${OCI_PROFILE}" \
        --region "${OCI_REGION}" \
        --cluster-id "${CLUSTER_ID}" \
        --output json 2>/dev/null |
        jq -r '.data[] | select(."addon-name" == "ClusterAutoscaler") | ."addon-name"' | head -1 || true)"
fi

if [[ -n "${EXISTING_ADDON}" ]]; then
    ACTION="update-addon"
    echo "  Existing ClusterAutoscaler add-on detected — will update-addon."
else
    ACTION="install-addon"
    echo "  No ClusterAutoscaler add-on present — will install-addon."
fi

if [[ "${APPLY}" != "true" ]]; then
    echo ""
    echo "[dry-run] would call:"
    echo "  oci ce cluster ${ACTION} \\"
    echo "      --profile ${OCI_PROFILE} \\"
    echo "      --region ${OCI_REGION} \\"
    echo "      --cluster-id ${CLUSTER_ID} \\"
    echo "      --addon-name ClusterAutoscaler \\"
    echo "      --from-json file://${tmp_config}"
    echo ""
    echo "[dry-run] Rendered config body:"
    cat "${tmp_config}"
    echo ""
    echo "DRY RUN only: no OCI state was mutated. Re-run with --apply to commit."
    exit 0
fi

echo ""
echo "About to ${ACTION} ClusterAutoscaler on cluster ${OKE_CLUSTER_NAME} (${CLUSTER_ID})."
echo "Node pool: ${OKE_NODE_POOL_OCID}"
echo "Scaling bounds: min=2 max=4 nodes."
echo ""
read -p "Type the cluster name '${OKE_CLUSTER_NAME}' to confirm apply: " CONFIRM
if [[ "${CONFIRM}" != "${OKE_CLUSTER_NAME}" ]]; then
    echo "Confirmation mismatch — aborting." >&2
    exit 1
fi

oci ce cluster "${ACTION}" \
    --profile "${OCI_PROFILE}" \
    --region "${OCI_REGION}" \
    --cluster-id "${CLUSTER_ID}" \
    --addon-name ClusterAutoscaler \
    --from-json "file://${tmp_config}" \
    --wait-for-state ACTIVE \
    --max-wait-seconds 900

echo "ClusterAutoscaler ${ACTION} completed for ${OKE_CLUSTER_NAME}."
