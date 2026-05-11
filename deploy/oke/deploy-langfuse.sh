#!/usr/bin/env bash
# Deploy a low-footprint Langfuse v3 test stack on OKE for OCTO-DEMO.
#
# Defaults are tuned for the emdemo compartment, the existing OCTO compute
# VCN, and the requested hostname langfuse.octodemo.cloud. The script refuses
# to deploy to an OKE cluster in a different VCN unless ALLOW_DIFFERENT_VCN=true.
#
# Usage:
#   ./deploy/oke/deploy-langfuse.sh --check
#   LANGFUSE_HOSTNAME=langfuse.octodemo.cloud ./deploy/oke/deploy-langfuse.sh

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

MODE="apply"
case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
    --check)
        MODE="check"
        ;;
    --dry-run)
        MODE="dry-run"
        ;;
    "")
        ;;
    *)
        echo "Unknown argument: $1" >&2
        show_usage >&2
        exit 2
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST="${REPO_ROOT}/k8s/oke/langfuse/langfuse.yaml"
OUTPUTS_JSON="${OUTPUTS_JSON:-/Users/abirzu/dev/octo-apm-demo/credentials/emdemo/outputs.json}"

command_exists() { command -v "$1" >/dev/null 2>&1; }

require_cmd() {
    if ! command_exists "$1"; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

json_value() {
    local expr="$1"
    if [[ -f "${OUTPUTS_JSON}" ]] && command_exists jq; then
        jq -r "${expr} // empty" "${OUTPUTS_JSON}" 2>/dev/null || true
    fi
}

random_base64() {
    openssl rand -base64 "${1:-32}" | tr -d '\n'
}

random_hex() {
    openssl rand -hex "${1:-32}" | tr -d '\n'
}

run_with_timeout() {
    local seconds="$1"
    shift

    if command_exists timeout; then
        timeout "${seconds}" "$@"
        return
    fi

    if command_exists gtimeout; then
        gtimeout "${seconds}" "$@"
        return
    fi

    python3 - "${seconds}" "$@" <<'PY'
import subprocess
import sys

seconds = float(sys.argv[1])
cmd = sys.argv[2:]

try:
    completed = subprocess.run(cmd, check=False, timeout=seconds)
except subprocess.TimeoutExpired:
    preview = " ".join(cmd[:4])
    print(f"Timed out after {seconds:g}s: {preview} ...", file=sys.stderr)
    raise SystemExit(124)

raise SystemExit(completed.returncode)
PY
}

oci_cmd() {
    run_with_timeout "${OCI_CMD_TIMEOUT}" oci \
        --connection-timeout "${OCI_CLI_CONNECTION_TIMEOUT}" \
        --read-timeout "${OCI_CLI_READ_TIMEOUT}" \
        "$@"
}

require_cmd oci
require_cmd kubectl
require_cmd jq
require_cmd envsubst
require_cmd openssl
if ! command_exists timeout && ! command_exists gtimeout; then
    require_cmd python3
fi

: "${OCI_PROFILE:=emdemo}"
: "${OCI_REGION:=us-phoenix-1}"
: "${OCI_CMD_TIMEOUT:=45}"
: "${OCI_CLI_CONNECTION_TIMEOUT:=10}"
: "${OCI_CLI_READ_TIMEOUT:=30}"
: "${COMPARTMENT_ID:=$(json_value '.deployment_compartment_id.value // .deployment_compartment_id')}"
: "${TARGET_VCN_ID:=$(json_value '.network.value.vcn_id')}"
: "${OCI_LB_SUBNET_OCID:=$(json_value '.network.value.lb_subnet_id')}"
: "${LANGFUSE_NAMESPACE:=octo-langfuse}"
: "${LANGFUSE_HOSTNAME:=langfuse.octodemo.cloud}"
: "${LANGFUSE_PUBLIC_URL:=https://${LANGFUSE_HOSTNAME}}"
: "${LANGFUSE_STORAGE_CLASS:=oci-bv}"
: "${LANGFUSE_POSTGRES_STORAGE:=10Gi}"
: "${LANGFUSE_CLICKHOUSE_STORAGE:=20Gi}"
: "${LANGFUSE_REDIS_STORAGE:=2Gi}"
: "${LANGFUSE_MINIO_STORAGE:=10Gi}"
: "${OCI_LB_SHAPE_FLEX_MIN:=10}"
: "${OCI_LB_SHAPE_FLEX_MAX:=10}"
: "${KUBE_ENDPOINT:=PUBLIC_ENDPOINT}"
: "${KUBECONFIG:=${REPO_ROOT}/../.tmp/oke-langfuse-kubeconfig}"
: "${ALLOW_DIFFERENT_VCN:=false}"

if [[ -z "${COMPARTMENT_ID}" || -z "${TARGET_VCN_ID}" || -z "${OCI_LB_SUBNET_OCID}" ]]; then
    echo "Missing COMPARTMENT_ID, TARGET_VCN_ID, or OCI_LB_SUBNET_OCID." >&2
    echo "Set them explicitly or provide OUTPUTS_JSON with emdemo network outputs." >&2
    exit 2
fi

echo "================================================================"
echo " OKE Langfuse deploy — OCTO-DEMO"
echo "   OCI profile:       ${OCI_PROFILE}"
echo "   OCI region:        ${OCI_REGION}"
echo "   Namespace:         ${LANGFUSE_NAMESPACE}"
echo "   Hostname:          ${LANGFUSE_HOSTNAME}"
echo "   Public URL:        ${LANGFUSE_PUBLIC_URL}"
echo "   Target VCN:        ${TARGET_VCN_ID:0:32}..."
echo "   LB subnet:         ${OCI_LB_SUBNET_OCID:0:32}..."
echo "   Storage class:     ${LANGFUSE_STORAGE_CLASS}"
echo "   LB bandwidth Mbps: ${OCI_LB_SHAPE_FLEX_MIN}-${OCI_LB_SHAPE_FLEX_MAX}"
echo "================================================================"

echo
echo "[1/7] OCI rights and VCN checks..."
if [[ -z "${OKE_CLUSTER_ID:-}" ]]; then
    OKE_CLUSTER_ID="$(
        oci_cmd ce cluster list \
            --profile "${OCI_PROFILE}" \
            --region "${OCI_REGION}" \
            --compartment-id "${COMPARTMENT_ID}" \
            --all \
            --output json |
        jq -r --arg vcn "${TARGET_VCN_ID}" \
            '.data[] | select(."lifecycle-state"=="ACTIVE" and ."vcn-id"==$vcn) | .id' |
        head -1
    )"
fi

if [[ -z "${OKE_CLUSTER_ID}" ]]; then
    echo "No ACTIVE OKE cluster was found in TARGET_VCN_ID." >&2
    echo "Active OKE clusters in the compartment:" >&2
    oci_cmd ce cluster list \
        --profile "${OCI_PROFILE}" \
        --region "${OCI_REGION}" \
        --compartment-id "${COMPARTMENT_ID}" \
        --all \
        --output json |
        jq -r '.data[] | select(."lifecycle-state"=="ACTIVE") | "  - \(.name) \(.id) vcn=\(."vcn-id") version=\(."kubernetes-version")"' >&2
    echo "Create/select an OKE cluster in the OCTO project VCN, or set ALLOW_DIFFERENT_VCN=true with OKE_CLUSTER_ID explicitly." >&2
    exit 4
fi

cluster_json="$(oci_cmd ce cluster get --profile "${OCI_PROFILE}" --region "${OCI_REGION}" --cluster-id "${OKE_CLUSTER_ID}" --output json)"
cluster_vcn="$(jq -r '.data."vcn-id"' <<<"${cluster_json}")"
cluster_name="$(jq -r '.data.name' <<<"${cluster_json}")"
cluster_state="$(jq -r '.data."lifecycle-state"' <<<"${cluster_json}")"

if [[ "${cluster_state}" != "ACTIVE" ]]; then
    echo "OKE cluster ${cluster_name} is ${cluster_state}, not ACTIVE." >&2
    exit 4
fi

if [[ "${cluster_vcn}" != "${TARGET_VCN_ID}" && "${ALLOW_DIFFERENT_VCN}" != "true" ]]; then
    echo "OKE cluster ${cluster_name} is not in TARGET_VCN_ID." >&2
    echo "  cluster VCN: ${cluster_vcn}" >&2
    echo "  target  VCN: ${TARGET_VCN_ID}" >&2
    echo "Refusing by default to keep OCTO-DEMO resources in the project VCN." >&2
    exit 4
fi

lb_subnet_json="$(oci_cmd network subnet get --profile "${OCI_PROFILE}" --region "${OCI_REGION}" --subnet-id "${OCI_LB_SUBNET_OCID}" --output json)"
lb_subnet_vcn="$(jq -r '.data."vcn-id"' <<<"${lb_subnet_json}")"

if [[ "${lb_subnet_vcn}" != "${cluster_vcn}" ]]; then
    echo "OCI_LB_SUBNET_OCID is not in the selected OKE cluster VCN." >&2
    echo "  subnet VCN:  ${lb_subnet_vcn}" >&2
    echo "  cluster VCN: ${cluster_vcn}" >&2
    exit 4
fi

echo "Using OKE cluster: ${cluster_name}"
mkdir -p "$(dirname "${KUBECONFIG}")"
oci_cmd ce cluster create-kubeconfig \
    --profile "${OCI_PROFILE}" \
    --region "${OCI_REGION}" \
    --cluster-id "${OKE_CLUSTER_ID}" \
    --file "${KUBECONFIG}" \
    --token-version 2.0.0 \
    --kube-endpoint "${KUBE_ENDPOINT}" >/dev/null
export KUBECONFIG

echo
echo "[2/7] Kubernetes rights and capacity checks..."
kubectl get nodes >/dev/null
kubectl get storageclass "${LANGFUSE_STORAGE_CLASS}" >/dev/null
kubectl auth can-i create namespaces >/dev/null
kubectl auth can-i create deployments -n "${LANGFUSE_NAMESPACE}" >/dev/null
kubectl auth can-i create statefulsets -n "${LANGFUSE_NAMESPACE}" >/dev/null
kubectl auth can-i create secrets -n "${LANGFUSE_NAMESPACE}" >/dev/null
kubectl auth can-i create services -n "${LANGFUSE_NAMESPACE}" >/dev/null
kubectl auth can-i create persistentvolumeclaims -n "${LANGFUSE_NAMESPACE}" >/dev/null
echo "Kubernetes access OK. Node summary:"
kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,VERSION:.status.nodeInfo.kubeletVersion --no-headers

if [[ "${MODE}" == "check" ]]; then
    echo
    echo "Check mode complete. No resources were changed."
    exit 0
fi

echo
echo "[3/7] Creating namespace and platform secret..."
kubectl create namespace "${LANGFUSE_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace "${LANGFUSE_NAMESPACE}" \
    app.kubernetes.io/part-of=octo-demo-observability \
    app.kubernetes.io/component=llmetry \
    octo.oracle.com/tier=test \
    --overwrite >/dev/null

: "${NEXTAUTH_SECRET:=$(random_base64 32)}"
: "${SALT:=$(random_base64 32)}"
: "${ENCRYPTION_KEY:=$(random_hex 32)}"
: "${POSTGRES_PASSWORD:=$(random_base64 32)}"
: "${CLICKHOUSE_PASSWORD:=$(random_base64 32)}"
: "${REDIS_AUTH:=$(random_base64 32)}"
: "${MINIO_ROOT_PASSWORD:=$(random_base64 32)}"
: "${LANGFUSE_S3_UPLOAD_SECRET_ACCESS_KEY:=$(random_base64 32)}"

secret_dir="$(mktemp -d)"
cleanup_secret_dir() {
    rm -rf "${secret_dir}"
}
trap cleanup_secret_dir EXIT

write_secret_file() {
    local name="$1"
    local value="$2"
    umask 077
    printf '%s' "${value}" > "${secret_dir}/${name}"
}

write_secret_file "nextauth-secret" "${NEXTAUTH_SECRET}"
write_secret_file "salt" "${SALT}"
write_secret_file "encryption-key" "${ENCRYPTION_KEY}"
write_secret_file "postgres-password" "${POSTGRES_PASSWORD}"
write_secret_file "clickhouse-password" "${CLICKHOUSE_PASSWORD}"
write_secret_file "redis-auth" "${REDIS_AUTH}"
write_secret_file "minio-root-password" "${MINIO_ROOT_PASSWORD}"
write_secret_file "s3-upload-secret-access-key" "${LANGFUSE_S3_UPLOAD_SECRET_ACCESS_KEY}"

kubectl -n "${LANGFUSE_NAMESPACE}" create secret generic langfuse-secrets \
    --from-file "nextauth-secret=${secret_dir}/nextauth-secret" \
    --from-file "salt=${secret_dir}/salt" \
    --from-file "encryption-key=${secret_dir}/encryption-key" \
    --from-file "postgres-password=${secret_dir}/postgres-password" \
    --from-file "clickhouse-password=${secret_dir}/clickhouse-password" \
    --from-file "redis-auth=${secret_dir}/redis-auth" \
    --from-file "minio-root-password=${secret_dir}/minio-root-password" \
    --from-file "s3-upload-secret-access-key=${secret_dir}/s3-upload-secret-access-key" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo
echo "[4/7] Rendering and applying Langfuse stack..."
export LANGFUSE_NAMESPACE LANGFUSE_PUBLIC_URL LANGFUSE_STORAGE_CLASS \
    LANGFUSE_POSTGRES_STORAGE LANGFUSE_CLICKHOUSE_STORAGE LANGFUSE_REDIS_STORAGE \
    LANGFUSE_MINIO_STORAGE OCI_LB_SUBNET_OCID OCI_LB_SHAPE_FLEX_MIN OCI_LB_SHAPE_FLEX_MAX

if [[ "${MODE}" == "dry-run" ]]; then
    envsubst < "${MANIFEST}" | kubectl apply --dry-run=server -f -
    echo "Dry run complete. No resources were persisted."
    exit 0
fi

envsubst < "${MANIFEST}" | kubectl apply -f -

echo
echo "[5/7] Waiting for data services..."
kubectl rollout status statefulset/langfuse-postgres -n "${LANGFUSE_NAMESPACE}" --timeout=300s
kubectl rollout status statefulset/langfuse-clickhouse -n "${LANGFUSE_NAMESPACE}" --timeout=420s
kubectl rollout status statefulset/langfuse-redis -n "${LANGFUSE_NAMESPACE}" --timeout=240s
kubectl rollout status statefulset/langfuse-minio -n "${LANGFUSE_NAMESPACE}" --timeout=240s
kubectl wait --for=condition=complete job/langfuse-minio-init -n "${LANGFUSE_NAMESPACE}" --timeout=240s

echo
echo "[6/7] Waiting for Langfuse web and worker..."
kubectl rollout status deployment/langfuse-worker -n "${LANGFUSE_NAMESPACE}" --timeout=420s
kubectl rollout status deployment/langfuse-web -n "${LANGFUSE_NAMESPACE}" --timeout=420s

echo
echo "[7/7] Optional OCTO app exporter secret..."
if [[ -n "${APP_LANGFUSE_PUBLIC_KEY:-}" && -n "${APP_LANGFUSE_SECRET_KEY:-}" ]]; then
    : "${K8S_NAMESPACE_SHOP:=octo-drone-shop}"
    : "${LANGFUSE_PROJECT_NAME:=drones.octodemo.cloud}"
    kubectl -n "${K8S_NAMESPACE_SHOP}" create secret generic octo-llmetry \
        --from-literal=langfuse-enabled=true \
        --from-literal=langfuse-host="${LANGFUSE_PUBLIC_URL}" \
        --from-literal=langfuse-project-name="${LANGFUSE_PROJECT_NAME}" \
        --from-literal=langfuse-public-key="${APP_LANGFUSE_PUBLIC_KEY}" \
        --from-literal=langfuse-secret-key="${APP_LANGFUSE_SECRET_KEY}" \
        --from-literal=langfuse-otel-export-enabled=true \
        --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    echo "Updated octo-llmetry secret in ${K8S_NAMESPACE_SHOP}."
else
    echo "Skipped app exporter secret. Set APP_LANGFUSE_PUBLIC_KEY and APP_LANGFUSE_SECRET_KEY after creating a project in this Langfuse instance."
fi

echo
echo "LoadBalancer status:"
kubectl get svc langfuse-web-lb -n "${LANGFUSE_NAMESPACE}"

echo
echo "================================================================"
echo " Done. Point DNS:"
echo "   ${LANGFUSE_HOSTNAME}  A/CNAME  -> langfuse-web-lb external IP/hostname"
echo
echo "Validate:"
echo "   kubectl -n ${LANGFUSE_NAMESPACE} port-forward svc/langfuse-web 33000:3000"
echo "   curl -fsS http://127.0.0.1:33000/api/public/health"
echo "================================================================"
