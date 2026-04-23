#!/usr/bin/env bash
# octo-apm-demo end-to-end tenancy bootstrap.
#
# Non-interactive when every required env is present. If
# OCI_COMPARTMENT_ID is empty AND stdin is a TTY, prompts the operator
# with a numbered picker.
#
# Usage:
#   # fully non-interactive
#   OCI_PROFILE=DEFAULT OCI_COMPARTMENT_ID=ocid1.compartment... \
#   DNS_BASE_DOMAIN=cyber-sec.ro \
#   OCIR_NAMESPACE=<ns> \
#   ./deploy/bootstrap.sh
#
#   # interactive compartment picker
#   OCI_PROFILE=DEFAULT ./deploy/bootstrap.sh
#
# What it does, idempotently:
#   1. Validate OCI CLI profile + kubeconfig + docker access.
#   2. Resolve (or prompt) compartment. Store choice in deploy/.last-tenancy.env.
#   3. Provision ATP via terraform (skip if OCI_ATP_DSN already set).
#   4. Decode + extract wallet, seed K8s secrets (atp, atp-wallet, auth,
#      apm, logging, oci-config).
#   5. Build + push shop + crm images via the remote x86_64 builder.
#   6. Apply k8s manifests (shop, crm, optional apm-java-demo).
#   7. Install nginx-ingress (if not present) + Ingress objects.
#   8. Create DNS A records in the configured base domain pointing at the ingress LB.
#   9. Smoke-verify every HTML + JSON endpoint over the public FQDN.
#
# Tagging: every OCI resource created here carries freeform_tag
# `project=octo-apm-demo` + `managed-by=bootstrap.sh` so destroy.sh can
# tear them down without touching anything else in the compartment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_TAG_KEY="project"
PROJECT_TAG_VAL="octo-apm-demo"

# ── Defaults (every one overridable via env) ──────────────────────────
: "${OCI_PROFILE:=DEFAULT}"
: "${DNS_BASE_DOMAIN:=cyber-sec.ro}"
: "${SHOP_SUBDOMAIN:=shop}"
: "${CRM_SUBDOMAIN:=crm}"
: "${K8S_NAMESPACE_SHOP:=octo-drone-shop}"
: "${K8S_NAMESPACE_CRM:=enterprise-crm}"
: "${REMOTE_BUILD_HOST:=control-plane-oci}"
: "${INSTALL_NGINX_INGRESS:=true}"
: "${SKIP_APM_JAVA_DEMO:=true}"
: "${PUBLISH_VIA_INGRESS:=true}"
: "${TLS_MODE:=auto}"
: "${TLS_REQUIRED:=false}"
: "${TLS_SECRET_NAME:=cyber-sec-ro-tls}"
: "${OCI_CERTIFICATE_OCID:=}"
# When the cluster is virtual-node-only, classic LB / NLB Services are
# unsupported. Two paths:
#   true  — auto-provision a 2-node managed pool so nginx-ingress works.
#   false — skip external exposure. Operator installs OCI Native Ingress
#           Controller add-on manually (console one-click).
: "${OKE_ADD_NODE_POOL_IF_VIRTUAL:=true}"
: "${OKE_NODE_POOL_SIZE:=2}"
: "${OKE_NODE_SHAPE:=VM.Standard.E5.Flex}"
: "${OKE_NODE_OCPUS:=1}"
: "${OKE_NODE_MEMORY_GBS:=8}"
: "${OKE_NODE_BOOT_VOLUME_GBS:=93}"
# DNS modes:
#   auto   — PATCH the OCI DNS zone. Requires `DNS_BASE_DOMAIN` to exist
#            as an OCI DNS zone the profile can write.
#   manual — print the A records + exit. Operator adds them to whatever
#            DNS provider they actually use (Route 53, Cloudflare, etc.).
#   skip   — don't touch DNS. Smoke test uses `-H "Host: ..."`.
: "${DNS_MODE:=auto}"

# Tenancy cache — written once picked, skipped if re-run.
TENANCY_CACHE="${SCRIPT_DIR}/.last-tenancy.env"

# ── Colour helpers ────────────────────────────────────────────────────
_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
_green() { printf '\033[32m%s\033[0m\n' "$*"; }
_yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }
_blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
section(){ printf '\n\033[1;36m── %s ──\033[0m\n' "$*"; }

get_secret_value() {
    local namespace="$1"
    local name="$2"
    local key="$3"
    kubectl get secret "${name}" -n "${namespace}" -o json 2>/dev/null | \
        python3 -c '
import base64, json, sys
try:
    data = json.load(sys.stdin).get("data", {})
    value = data.get(sys.argv[1], "")
    print(base64.b64decode(value).decode("utf-8") if value else "", end="")
except Exception:
    pass
' "${key}" 2>/dev/null || true
}

first_nonempty_secret_value() {
    local name="$1"
    local key="$2"
    local namespace
    local value
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        value="$(get_secret_value "${namespace}" "${name}" "${key}")"
        if [[ -n "${value}" ]]; then
            printf '%s' "${value}"
            return 0
        fi
    done
    return 1
}

first_nonempty_secret_value_or_blank() {
    first_nonempty_secret_value "$@" || true
}

apply_literal_secret() {
    local namespace="$1"
    local name="$2"
    shift 2
    local -a args=()
    local pair key value
    for pair in "$@"; do
        key="${pair%%=*}"
        value="${pair#*=}"
        [[ -n "${value}" ]] || continue
        args+=(--from-literal="${key}=${value}")
    done
    if [[ "${#args[@]}" -eq 0 ]]; then
        _yellow "      ${namespace}/${name} — skipped (no non-empty values)"
        return
    fi
    kubectl -n "${namespace}" create secret generic "${name}" "${args[@]}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    _green "      ${namespace}/${name} — applied"
}

apply_literal_secret_all_namespaces() {
    local name="$1"
    shift
    local namespace
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        apply_literal_secret "${namespace}" "${name}" "$@"
    done
}

resolve_ocir_pull_credentials() {
    if [[ -n "${OCIR_USERNAME:-}" && -n "${OCIR_AUTH_TOKEN:-}" ]]; then
        return 0
    fi
    [[ -f "${HOME}/.docker/config.json" ]] || return 1
    local parsed
    parsed="$(
        OCIR_REGION="${OCIR_REGION}" python3 - <<'PYEOF'
import base64
import json
import os
import pathlib
import sys

path = pathlib.Path.home() / ".docker" / "config.json"
data = json.loads(path.read_text())
server = f"{os.environ['OCIR_REGION']}.ocir.io"
entry = (data.get("auths") or {}).get(server) or {}
auth = entry.get("auth")
if not auth:
    sys.exit(1)
username, password = base64.b64decode(auth).decode().split(":", 1)
print(f"{username}\t{password}")
PYEOF
    )" || return 1
    IFS=$'\t' read -r OCIR_USERNAME OCIR_AUTH_TOKEN <<< "${parsed}"
    export OCIR_USERNAME OCIR_AUTH_TOKEN
    return 0
}

apply_ocir_pull_secret() {
    local namespace="$1"
    kubectl -n "${namespace}" create secret docker-registry ocir-pull-secret \
        --docker-server="${OCIR_REGION}.ocir.io" \
        --docker-username="${OCIR_USERNAME}" \
        --docker-password="${OCIR_AUTH_TOKEN}" \
        --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    _green "      ${namespace}/ocir-pull-secret — applied"
}

ingress_controller_service_name() {
    local candidate
    for candidate in ingress-nginx-controller nginx-ingress-ingress-nginx-controller; do
        if kubectl -n ingress-nginx get svc "${candidate}" >/dev/null 2>&1; then
            printf '%s' "${candidate}"
            return 0
        fi
    done
    return 1
}

render_and_apply_manifest() {
    local namespace="$1"
    local image_tag="$2"
    local manifest_path="$3"
    local rendered
    rendered="$(mktemp)"
    IMAGE_TAG="${image_tag}" envsubst < "${manifest_path}" > "${rendered}"
    if [[ "${PUBLISH_VIA_INGRESS}" == "true" ]]; then
        python3 - "${rendered}" <<'PYEOF' | kubectl apply -n "${namespace}" -f -
import sys
import yaml

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    docs = list(yaml.safe_load_all(handle))

for doc in docs:
    if not doc:
        continue
    if doc.get("kind") == "Service" and doc.get("spec", {}).get("type") == "LoadBalancer":
        continue
    print("---")
    sys.stdout.write(yaml.safe_dump(doc, sort_keys=False))
PYEOF
    else
        kubectl apply -n "${namespace}" -f "${rendered}"
    fi
    rm -f "${rendered}"
}

ensure_tls_secrets_from_oci_certificate() {
    local cert_file key_file cert_id
    cert_file="$(mktemp)"
    key_file="$(mktemp)"
    cert_id="$(
        OCI_PROFILE="${OCI_PROFILE}" \
        OCI_COMPARTMENT_ID="${OCI_COMPARTMENT_ID}" \
        DNS_BASE_DOMAIN="${DNS_BASE_DOMAIN}" \
        OCI_CERTIFICATE_OCID="${OCI_CERTIFICATE_OCID}" \
        CERT_FILE="${cert_file}" \
        KEY_FILE="${key_file}" \
        python3 - <<'PYEOF'
import os
import sys
import oci

cfg = oci.config.from_file(profile_name=os.environ["OCI_PROFILE"])
cert_id = os.environ.get("OCI_CERTIFICATE_OCID", "")

if not cert_id:
    client = oci.certificates_management.CertificatesManagementClient(cfg)
    target_names = {
        f"star.{os.environ['DNS_BASE_DOMAIN']}",
        f"*.{os.environ['DNS_BASE_DOMAIN']}",
    }
    for cert in client.list_certificates(
        compartment_id=os.environ["OCI_COMPARTMENT_ID"]
    ).data:
        if cert.name in target_names:
            cert_id = cert.id
            break

if not cert_id:
    sys.exit(2)

bundle = oci.certificates.CertificatesClient(cfg).get_certificate_bundle(
    cert_id,
    certificate_bundle_type="CERTIFICATE_CONTENT_WITH_PRIVATE_KEY",
).data

certificate_pem = bundle.certificate_pem or ""
chain_pem = bundle.cert_chain_pem or ""
private_key_pem = bundle.private_key_pem or ""
if not certificate_pem or not private_key_pem:
    sys.exit(3)

with open(os.environ["CERT_FILE"], "w", encoding="utf-8") as cert_handle:
    cert_handle.write(certificate_pem.rstrip() + "\n")
    if chain_pem:
        cert_handle.write(chain_pem)

with open(os.environ["KEY_FILE"], "w", encoding="utf-8") as key_handle:
    key_handle.write(private_key_pem)

print(cert_id)
PYEOF
    )"
    local rc=$?
    if [[ ${rc} -ne 0 ]]; then
        rm -f "${cert_file}" "${key_file}"
        return "${rc}"
    fi

    local namespace
    for namespace in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        kubectl -n "${namespace}" create secret tls "${TLS_SECRET_NAME}" \
            --cert="${cert_file}" \
            --key="${key_file}" \
            --dry-run=client -o yaml | kubectl apply -f - >/dev/null
        _green "      ${namespace}/${TLS_SECRET_NAME} — applied from OCI certificate"
    done

    rm -f "${cert_file}" "${key_file}"
    printf '%s' "${cert_id}"
}

# ── Step 0: resolve OCI config ────────────────────────────────────────
section "Step 0 — OCI profile validation"
if ! oci iam user get --user-id "$(python3 -c "import oci; print(oci.config.from_file(profile_name='${OCI_PROFILE}')['user'])")" --profile "${OCI_PROFILE}" >/dev/null 2>&1; then
    # The Python SDK path is more reliable than the CLI for broken installs.
    OCI_PROFILE="${OCI_PROFILE}" python3 - <<'PYEOF'
import os, oci, sys
cfg = oci.config.from_file(profile_name=os.environ['OCI_PROFILE'])
iam = oci.identity.IdentityClient(cfg)
user = iam.get_user(cfg['user']).data
print(f"profile={os.environ['OCI_PROFILE']} user={user.name} tenancy={cfg['tenancy'][:40]}... region={cfg['region']}")
PYEOF
fi

TENANCY_OCID=$(python3 -c "import oci; print(oci.config.from_file(profile_name='${OCI_PROFILE}')['tenancy'])")
OCI_REGION=$(python3 -c "import oci; print(oci.config.from_file(profile_name='${OCI_PROFILE}')['region'])")
export TENANCY_OCID OCI_REGION

# ── Step 1: compartment selection ─────────────────────────────────────
section "Step 1 — Compartment selection"
if [[ -z "${OCI_COMPARTMENT_ID:-}" ]] && [[ -f "${TENANCY_CACHE}" ]]; then
    # shellcheck disable=SC1090
    source "${TENANCY_CACHE}"
    _yellow "Using cached compartment from ${TENANCY_CACHE}: ${OCI_COMPARTMENT_NAME:-unnamed} (${OCI_COMPARTMENT_ID:0:40}...)"
fi

if [[ -z "${OCI_COMPARTMENT_ID:-}" ]]; then
    if [[ -t 0 ]]; then
        _blue "No OCI_COMPARTMENT_ID in env. Listing compartments under tenancy…"
        OCI_PROFILE="${OCI_PROFILE}" python3 - <<'PYEOF' > /tmp/_octo_compartments.tsv
import os, oci
cfg = oci.config.from_file(profile_name=os.environ['OCI_PROFILE'])
iam = oci.identity.IdentityClient(cfg)
comps = iam.list_compartments(
    compartment_id=cfg['tenancy'],
    compartment_id_in_subtree=True,
    lifecycle_state='ACTIVE',
    limit=500,
).data
# Sort by name for predictable numbering.
comps.sort(key=lambda c: c.name.lower())
for i, c in enumerate(comps, 1):
    print(f"{i}\t{c.name}\t{c.id}")
PYEOF
        if ! [[ -s /tmp/_octo_compartments.tsv ]]; then
            _red "No compartments visible to this user. Check IAM policy."
            exit 1
        fi
        nl=$(wc -l < /tmp/_octo_compartments.tsv | tr -d ' ')
        awk -F'\t' '{ printf "  %3s) %s\n", $1, $2 }' /tmp/_octo_compartments.tsv
        read -r -p "Pick compartment number [1-${nl}]: " pick
        if ! [[ "${pick}" =~ ^[0-9]+$ ]] || (( pick < 1 || pick > nl )); then
            _red "Invalid choice ${pick}"
            exit 1
        fi
        OCI_COMPARTMENT_NAME=$(awk -F'\t' -v k="${pick}" '$1==k {print $2}' /tmp/_octo_compartments.tsv)
        OCI_COMPARTMENT_ID=$(awk -F'\t' -v k="${pick}" '$1==k {print $3}' /tmp/_octo_compartments.tsv)
    else
        _red "stdin is not a TTY and OCI_COMPARTMENT_ID not set. Either export it or run interactively."
        exit 1
    fi
fi

if [[ -n "${OCI_COMPARTMENT_ID:-}" ]] && [[ -z "${OCI_COMPARTMENT_NAME:-}" ]]; then
    OCI_COMPARTMENT_NAME="$(
        OCI_PROFILE="${OCI_PROFILE}" OCI_COMPARTMENT_ID="${OCI_COMPARTMENT_ID}" python3 - <<'PYEOF'
import os
import oci

cfg = oci.config.from_file(profile_name=os.environ["OCI_PROFILE"])
identity = oci.identity.IdentityClient(cfg)
compartment_id = os.environ["OCI_COMPARTMENT_ID"]
try:
    print(identity.get_compartment(compartment_id).data.name, end="")
except oci.exceptions.ServiceError:
    if compartment_id == cfg["tenancy"]:
        print(identity.get_tenancy(compartment_id).data.name, end="")
PYEOF
    )"
fi

mkdir -p "$(dirname "${TENANCY_CACHE}")"
cat > "${TENANCY_CACHE}" <<EOF
# Cached selection from $(date -u +%FT%TZ). Safe to delete to reset.
export OCI_PROFILE=${OCI_PROFILE}
export OCI_COMPARTMENT_ID=${OCI_COMPARTMENT_ID}
export OCI_COMPARTMENT_NAME=${OCI_COMPARTMENT_NAME:-}
export TENANCY_OCID=${TENANCY_OCID}
export OCI_REGION=${OCI_REGION}
export DNS_BASE_DOMAIN=${DNS_BASE_DOMAIN}
EOF
chmod 600 "${TENANCY_CACHE}"

_green "Using compartment: ${OCI_COMPARTMENT_NAME:-unnamed} (${OCI_COMPARTMENT_ID})"
export OCI_COMPARTMENT_ID OCI_COMPARTMENT_NAME

# ── Step 2: OCIR namespace + auth ─────────────────────────────────────
section "Step 2 — OCIR namespace"
OCIR_NAMESPACE="${OCIR_NAMESPACE:-$(python3 -c "
import oci
cfg = oci.config.from_file(profile_name='${OCI_PROFILE}')
print(oci.object_storage.ObjectStorageClient(cfg).get_namespace().data)
")}"
export OCIR_NAMESPACE OCIR_REGION="${OCI_REGION}" OCIR_TENANCY="${OCIR_NAMESPACE}"
_green "OCIR ns: ${OCIR_NAMESPACE}"

# Ensure repos exist (tagged).
OCI_PROFILE="${OCI_PROFILE}" OCI_COMPARTMENT_ID="${OCI_COMPARTMENT_ID}" python3 - <<'PYEOF'
import os, oci
cfg = oci.config.from_file(profile_name=os.environ['OCI_PROFILE'])
client = oci.artifacts.ArtifactsClient(cfg)
for name in ["octo-drone-shop", "enterprise-crm-portal", "octo-apm-java-demo"]:
    try:
        client.create_container_repository(
            oci.artifacts.models.CreateContainerRepositoryDetails(
                compartment_id=os.environ['OCI_COMPARTMENT_ID'],
                display_name=name,
                is_public=False,
            )
        )
        print(f"  created {name}")
    except oci.exceptions.ServiceError as e:
        if e.status in (409,):
            print(f"  exists  {name}")
        else:
            print(f"  err     {name}: {e.message[:60]}")
PYEOF

# ── Step 3: kubeconfig ────────────────────────────────────────────────
section "Step 3 — Kubeconfig"
CLUSTER_ID="${OKE_CLUSTER_ID:-}"
if [[ -z "${CLUSTER_ID}" ]]; then
    CLUSTER_ID=$(python3 -c "
import oci
cfg = oci.config.from_file(profile_name='${OCI_PROFILE}')
c = oci.container_engine.ContainerEngineClient(cfg)
clusters = [cl for cl in c.list_clusters(compartment_id='${OCI_COMPARTMENT_ID}').data if cl.lifecycle_state == 'ACTIVE']
if not clusters:
    print('', end='')
else:
    print(clusters[0].id)
")
fi
if [[ -z "${CLUSTER_ID}" ]]; then
    _red "No ACTIVE OKE cluster in compartment. Set OKE_CLUSTER_ID or run terraform with create_oke=true."
    exit 1
fi
KUBE_CTX="octo-${OCI_COMPARTMENT_NAME:-tenancy}"
mkdir -p ~/.kube
KUBECONFIG=/tmp/_octo-kubeconfig oci ce cluster create-kubeconfig --cluster-id "${CLUSTER_ID}" --file /tmp/_octo-kubeconfig --region "${OCI_REGION}" --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT --profile "${OCI_PROFILE}" >/dev/null
KUBECONFIG=/tmp/_octo-kubeconfig:$HOME/.kube/config kubectl config view --flatten > /tmp/_octo-merged && mv /tmp/_octo-merged "$HOME/.kube/config"
ctx=$(KUBECONFIG=/tmp/_octo-kubeconfig kubectl config current-context)
kubectl config rename-context "${ctx}" "${KUBE_CTX}" >/dev/null 2>&1 || true
kubectl config use-context "${KUBE_CTX}" >/dev/null
_green "Using context ${KUBE_CTX} → cluster ${CLUSTER_ID:0:40}..."

# Namespaces
kubectl create namespace "${K8S_NAMESPACE_SHOP}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl create namespace "${K8S_NAMESPACE_CRM}"  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# ── Step 4: Terraform (ATP + APM) ─────────────────────────────────────
section "Step 4 — Terraform (ATP + APM optional)"
TFVARS="${SCRIPT_DIR}/terraform/terraform.${OCI_COMPARTMENT_NAME:-custom}.tfvars"
ATP_ADMIN_PW="${ATP_ADMIN_PW:-$(python3 -c 'import secrets; pw=secrets.token_urlsafe(20); print("".join(c for c in pw if c.isalnum())[:16] + "Aa1!")')}"
ATP_WALLET_PW="${ATP_WALLET_PW:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')}"
if [[ ! -f "${TFVARS}" ]]; then
    cat > "${TFVARS}" <<EOF
compartment_id      = "${OCI_COMPARTMENT_ID}"
waf_mode            = "DETECTION"
waf_log_group_id    = "ocid1.loggroup.oc1..xxxx"
admin_allow_cidrs   = []
shop_domain         = "${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
crm_domain          = "${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
ops_domain          = "ops.${DNS_BASE_DOMAIN}"
coordinator_domain  = "coordinator.${DNS_BASE_DOMAIN}"
la_namespace        = "${LA_NAMESPACE:-unused}"
la_log_group_id     = "ocid1.loganalyticsloggroup.oc1..xxxx"

create_atp          = true
atp_admin_password  = "${ATP_ADMIN_PW}"
atp_wallet_password = "${ATP_WALLET_PW}"
EOF
    chmod 600 "${TFVARS}"
    _green "Wrote ${TFVARS} (chmod 600)"
else
    # Pull passwords from the existing tfvars
    ATP_ADMIN_PW=$(grep atp_admin_password "${TFVARS}" | cut -d\" -f2)
    ATP_WALLET_PW=$(grep atp_wallet_password "${TFVARS}" | cut -d\" -f2)
fi

cd "${SCRIPT_DIR}/terraform"
terraform init -input=false -no-color >/dev/null
# Idempotent — only adds/updates ATP.
terraform apply -auto-approve -var-file="${TFVARS}" -target=module.atp -no-color 2>&1 | grep -E "Apply complete|Error:|^module\.atp" | head -5

ATP_DB_NAME=$(terraform output -json atp | python3 -c "import sys,json; print(json.load(sys.stdin)['atp_db_name'].lower())")
ATP_DSN="${ATP_DB_NAME}_low"
_green "ATP ready, DSN alias: ${ATP_DSN}"

# ── Step 5: Wallet + secrets ──────────────────────────────────────────
section "Step 5 — K8s secrets (atp-wallet, auth, apm, logging, oci-config)"
WALLET_ZIP=/tmp/_octo-wallet.zip
WALLET_DIR=/tmp/_octo-wallet-extract
terraform output -json atp_wallet_b64 | python3 -c "import sys,json,base64; sys.stdout.buffer.write(base64.b64decode(json.load(sys.stdin)))" > "${WALLET_ZIP}"
rm -rf "${WALLET_DIR}" && mkdir -p "${WALLET_DIR}" && unzip -q "${WALLET_ZIP}" -d "${WALLET_DIR}"
cd "${REPO_ROOT}"

gen() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }
AUTH_TOKEN_SECRET="${AUTH_TOKEN_SECRET:-$(first_nonempty_secret_value_or_blank octo-auth token-secret)}"
INTERNAL_SERVICE_KEY="${INTERNAL_SERVICE_KEY:-$(first_nonempty_secret_value_or_blank octo-auth internal-service-key)}"
APP_SECRET_KEY="${APP_SECRET_KEY:-$(first_nonempty_secret_value_or_blank octo-auth app-secret-key)}"
BOOTSTRAP_ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-$(first_nonempty_secret_value_or_blank octo-auth bootstrap-admin-password)}"
[[ -n "${AUTH_TOKEN_SECRET}" ]] || AUTH_TOKEN_SECRET="$(gen)"
[[ -n "${INTERNAL_SERVICE_KEY}" ]] || INTERNAL_SERVICE_KEY="$(gen)"
[[ -n "${APP_SECRET_KEY}" ]] || APP_SECRET_KEY="$(gen)"
[[ -n "${BOOTSTRAP_ADMIN_PASSWORD}" ]] || BOOTSTRAP_ADMIN_PASSWORD="$(gen)"

OCI_APM_ENDPOINT="${OCI_APM_ENDPOINT:-$(first_nonempty_secret_value_or_blank octo-apm endpoint)}"
OCI_APM_PRIVATE_DATAKEY="${OCI_APM_PRIVATE_DATAKEY:-$(first_nonempty_secret_value_or_blank octo-apm private-key)}"
OCI_APM_PUBLIC_DATAKEY="${OCI_APM_PUBLIC_DATAKEY:-$(first_nonempty_secret_value_or_blank octo-apm public-key)}"
OCI_APM_RUM_ENDPOINT="${OCI_APM_RUM_ENDPOINT:-$(first_nonempty_secret_value_or_blank octo-apm rum-endpoint)}"
OCI_APM_RUM_WEB_APPLICATION_OCID="${OCI_APM_RUM_WEB_APPLICATION_OCID:-$(first_nonempty_secret_value_or_blank octo-apm rum-web-application-ocid)}"

OCI_LOG_GROUP_ID="${OCI_LOG_GROUP_ID:-$(first_nonempty_secret_value_or_blank octo-logging log-group-id)}"
OCI_LOG_ID="${OCI_LOG_ID:-$(first_nonempty_secret_value_or_blank octo-logging log-id)}"
OCI_LOG_CHAOS_AUDIT_ID="${OCI_LOG_CHAOS_AUDIT_ID:-$(first_nonempty_secret_value_or_blank octo-logging log-chaos-audit-id)}"
OCI_LOG_SECURITY_ID="${OCI_LOG_SECURITY_ID:-$(first_nonempty_secret_value_or_blank octo-logging log-security-id)}"
SPLUNK_HEC_URL="${SPLUNK_HEC_URL:-$(first_nonempty_secret_value_or_blank octo-logging splunk-hec-url)}"
SPLUNK_HEC_TOKEN="${SPLUNK_HEC_TOKEN:-$(first_nonempty_secret_value_or_blank octo-logging splunk-hec-token)}"

APM_CONSOLE_URL="${APM_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations apm-console-url)}"
OPSI_CONSOLE_URL="${OPSI_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations opsi-console-url)}"
DB_MANAGEMENT_CONSOLE_URL="${DB_MANAGEMENT_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations db-management-console-url)}"
LOG_ANALYTICS_CONSOLE_URL="${LOG_ANALYTICS_CONSOLE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations log-analytics-console-url)}"
WORKFLOW_API_BASE_URL="${WORKFLOW_API_BASE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations workflow-api-base-url)}"
WORKFLOW_PUBLIC_API_BASE_URL="${WORKFLOW_PUBLIC_API_BASE_URL:-$(first_nonempty_secret_value_or_blank octo-integrations workflow-public-api-base-url)}"

if resolve_ocir_pull_credentials; then
    for NS in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
        apply_ocir_pull_secret "${NS}"
    done
else
    _yellow "      ocir-pull-secret — skipped (set OCIR_USERNAME/OCIR_AUTH_TOKEN or docker login ${OCIR_REGION}.ocir.io first)"
fi

for NS in "${K8S_NAMESPACE_SHOP}" "${K8S_NAMESPACE_CRM}"; do
    apply_literal_secret "${NS}" octo-auth \
        "token-secret=${AUTH_TOKEN_SECRET}" \
        "internal-service-key=${INTERNAL_SERVICE_KEY}" \
        "app-secret-key=${APP_SECRET_KEY}" \
        "bootstrap-admin-password=${BOOTSTRAP_ADMIN_PASSWORD}"
    kubectl -n "$NS" create secret generic octo-atp \
        --from-literal=dsn="${ATP_DSN}" \
        --from-literal=username=ADMIN \
        --from-literal=password="${ATP_ADMIN_PW}" \
        --from-literal=wallet-password="${ATP_WALLET_PW}" \
        --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    kubectl -n "$NS" delete secret octo-atp-wallet --ignore-not-found >/dev/null
    kubectl -n "$NS" create secret generic octo-atp-wallet \
        --from-file="${WALLET_DIR}/tnsnames.ora" \
        --from-file="${WALLET_DIR}/sqlnet.ora" \
        --from-file="${WALLET_DIR}/cwallet.sso" \
        --from-file="${WALLET_DIR}/ewallet.p12" \
        --from-file="${WALLET_DIR}/ewallet.pem" \
        --from-file="${WALLET_DIR}/keystore.jks" \
        --from-file="${WALLET_DIR}/truststore.jks" \
        --from-file="${WALLET_DIR}/ojdbc.properties" >/dev/null
done
apply_literal_secret_all_namespaces octo-apm \
    "endpoint=${OCI_APM_ENDPOINT:-}" \
    "private-key=${OCI_APM_PRIVATE_DATAKEY:-}" \
    "public-key=${OCI_APM_PUBLIC_DATAKEY:-}" \
    "rum-endpoint=${OCI_APM_RUM_ENDPOINT:-}" \
    "rum-web-application-ocid=${OCI_APM_RUM_WEB_APPLICATION_OCID:-}"
apply_literal_secret_all_namespaces octo-logging \
    "log-group-id=${OCI_LOG_GROUP_ID:-}" \
    "log-id=${OCI_LOG_ID:-}" \
    "log-chaos-audit-id=${OCI_LOG_CHAOS_AUDIT_ID:-}" \
    "log-security-id=${OCI_LOG_SECURITY_ID:-}" \
    "splunk-hec-url=${SPLUNK_HEC_URL:-}" \
    "splunk-hec-token=${SPLUNK_HEC_TOKEN:-}"
apply_literal_secret_all_namespaces octo-oci-config \
    "compartment-id=${OCI_COMPARTMENT_ID}" \
    "genai-endpoint=${OCI_GENAI_ENDPOINT:-}" \
    "genai-model-id=${OCI_GENAI_MODEL_ID:-}"
apply_literal_secret_all_namespaces octo-integrations \
    "crm-url=https://${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}" \
    "shop-url=https://${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}" \
    "workflow-api-base-url=${WORKFLOW_API_BASE_URL:-}" \
    "workflow-public-api-base-url=${WORKFLOW_PUBLIC_API_BASE_URL:-}" \
    "apm-console-url=${APM_CONSOLE_URL:-}" \
    "opsi-console-url=${OPSI_CONSOLE_URL:-}" \
    "db-management-console-url=${DB_MANAGEMENT_CONSOLE_URL:-}" \
    "log-analytics-console-url=${LOG_ANALYTICS_CONSOLE_URL:-}"
_green "Secrets seeded in ${K8S_NAMESPACE_SHOP} + ${K8S_NAMESPACE_CRM}"

# ── Step 6: Build + push images ───────────────────────────────────────
section "Step 6 — Build + push (remote VM ${REMOTE_BUILD_HOST})"
build_service() {
    local svc="$1" repo="$2" dir="$3" ns="$4"
    local logfile="/tmp/_octo_build_${svc}.log"
    # Capture full output to a log; set +o pipefail so grep's exit code
    # doesn't kill the parent script when matches are sparse.
    set +o pipefail
    OCIR_REPO="${OCIR_REGION}.ocir.io/${OCIR_NAMESPACE}/${repo}" \
      DNS_DOMAIN="${DNS_BASE_DOMAIN}" \
      K8S_NAMESPACE="${ns}" \
      REMOTE_HOST="${REMOTE_BUILD_HOST}" \
      REMOTE_DIR="${dir}" \
      bash "${SCRIPT_DIR}/deploy-${svc}.sh" --build-only > "${logfile}" 2>&1
    local rc=$?
    set -o pipefail
    grep -E "Image:|Build complete|Push complete|failed to build|ERROR" "${logfile}" || true
    if [[ $rc -ne 0 ]]; then
        _red "  ${svc} build exited ${rc}. Full log:"
        tail -20 "${logfile}"
        return $rc
    fi
}
build_service shop octo-drone-shop /tmp/octo-apm-demo-shop "${K8S_NAMESPACE_SHOP}"
build_service crm  enterprise-crm-portal /tmp/octo-apm-demo-crm  "${K8S_NAMESPACE_CRM}"

# Tag resolution — the most recently-built image, not `latest` label.
SHOP_TAG=$(ssh "${REMOTE_BUILD_HOST}" "docker images ${OCIR_REGION}.ocir.io/${OCIR_NAMESPACE}/octo-drone-shop --format '{{.Tag}}'" 2>/dev/null | grep -vE '^latest$' | sort -r | head -1 || true)
CRM_TAG=$(ssh "${REMOTE_BUILD_HOST}" "docker images ${OCIR_REGION}.ocir.io/${OCIR_NAMESPACE}/enterprise-crm-portal --format '{{.Tag}}'" 2>/dev/null | grep -vE '^latest$' | sort -r | head -1 || true)
[[ -n "${SHOP_TAG}" ]] || { _red "Shop image tag resolution failed"; exit 1; }
[[ -n "${CRM_TAG}" ]] || { _red "CRM image tag resolution failed"; exit 1; }
_green "Shop image: ${SHOP_TAG} · CRM image: ${CRM_TAG}"

# ── Step 7: Apply k8s manifests ───────────────────────────────────────
section "Step 7 — Apply k8s manifests"
export OCIR_REGION OCIR_TENANCY="${OCIR_NAMESPACE}" DNS_DOMAIN="${DNS_BASE_DOMAIN}" \
       K8S_NAMESPACE_SHOP K8S_NAMESPACE_CRM \
       CRM_PUBLIC_URL="https://${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}" \
       SHOP_PUBLIC_URL="https://${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}" \
       OCI_LB_SUBNET_OCID="${OCI_LB_SUBNET_OCID:-}"
render_and_apply_manifest "${K8S_NAMESPACE_SHOP}" "${SHOP_TAG}" "${REPO_ROOT}/deploy/k8s/oke/shop/deployment.yaml"
render_and_apply_manifest "${K8S_NAMESPACE_CRM}" "${CRM_TAG}" "${REPO_ROOT}/deploy/k8s/oke/crm/deployment.yaml"

# Drop the IDCS_REDIRECT_URI env (partial-IDCS guard trips when secret octo-sso absent).
kubectl -n "${K8S_NAMESPACE_SHOP}" set env deployment/octo-drone-shop      IDCS_REDIRECT_URI- IDCS_POST_LOGOUT_REDIRECT- >/dev/null || true
kubectl -n "${K8S_NAMESPACE_CRM}"  set env deployment/enterprise-crm-portal IDCS_REDIRECT_URI- IDCS_POST_LOGOUT_REDIRECT- >/dev/null || true

kubectl -n "${K8S_NAMESPACE_SHOP}" rollout status deployment/octo-drone-shop      --timeout=240s
kubectl -n "${K8S_NAMESPACE_CRM}"  rollout status deployment/enterprise-crm-portal --timeout=240s
_green "Both deployments Ready"

# ── Step 8: ingress ───────────────────────────────────────────────────
section "Step 8 — Ingress"
INGRESS_CLASS="${INGRESS_CLASS:-nginx}"
EXISTING_INGRESS_SERVICE="$(ingress_controller_service_name || true)"
VIRTUAL_ONLY=$(kubectl get nodes -o json | python3 -c "
import sys, json
items = json.load(sys.stdin).get('items', [])
if not items:
    print('true'); sys.exit()
virtual = sum(1 for n in items if 'virtual-node' in n.get('status',{}).get('nodeInfo',{}).get('kubeletVersion','').lower() or n.get('metadata',{}).get('labels',{}).get('node.kubernetes.io/instance-type','').startswith('virtual'))
# OCI virtual nodes carry label 'node.kubernetes.io/instance-type=VirtualNode' or role 'virtual-node'.
# Safer check: look for roles.
any_real = any('virtual-node' not in (n.get('metadata',{}).get('labels',{}).get('node-role.kubernetes.io/node-role','') or '') and n.get('status',{}).get('nodeInfo',{}).get('operatingSystem') for n in items)
roles = [list((n.get('metadata',{}).get('labels') or {}).keys()) for n in items]
is_virtual = all(any('virtual' in r.lower() for r in rlist) for rlist in roles) if roles else True
print('true' if is_virtual else 'false')
")

if [[ -n "${EXISTING_INGRESS_SERVICE}" ]]; then
    _green "Reusing ingress controller service ${EXISTING_INGRESS_SERVICE}"
elif [[ "${INSTALL_NGINX_INGRESS}" == "true" && "${VIRTUAL_ONLY}" == "false" ]]; then
    # Managed node pool present — nginx-ingress works.
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
    helm repo update >/dev/null 2>&1 || true
    cat > /tmp/_octo-nginx-values.yaml <<EOF
controller:
  replicaCount: 2
  service:
    type: LoadBalancer
    annotations:
      service.beta.kubernetes.io/oci-load-balancer-shape: "flexible"
      service.beta.kubernetes.io/oci-load-balancer-shape-flex-min: "10"
      service.beta.kubernetes.io/oci-load-balancer-shape-flex-max: "100"
  ingressClassResource:
    default: true
EOF
    helm upgrade --install nginx-ingress ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace -f /tmp/_octo-nginx-values.yaml --wait --timeout 5m >/dev/null
    EXISTING_INGRESS_SERVICE="$(ingress_controller_service_name || true)"
    _green "nginx-ingress installed"
elif [[ "${VIRTUAL_ONLY}" == "true" ]]; then
    _yellow "Virtual-node-only cluster detected (KB-459). Classic LB Services + nginx-ingress need managed nodes."
    if [[ "${OKE_ADD_NODE_POOL_IF_VIRTUAL}" == "true" ]]; then
        _yellow "Auto-provisioning a managed node pool (${OKE_NODE_POOL_SIZE} × ${OKE_NODE_SHAPE})…"
        OCI_PROFILE="${OCI_PROFILE}" \
          CLUSTER_ID="${CLUSTER_ID}" \
          OKE_NODE_SHAPE="${OKE_NODE_SHAPE}" \
          OKE_NODE_OCPUS="${OKE_NODE_OCPUS}" \
          OKE_NODE_MEMORY_GBS="${OKE_NODE_MEMORY_GBS}" \
          OKE_NODE_BOOT_VOLUME_GBS="${OKE_NODE_BOOT_VOLUME_GBS}" \
          OKE_NODE_POOL_SIZE="${OKE_NODE_POOL_SIZE}" \
          python3 - <<'PYEOF'
import os, oci, sys, time
cfg = oci.config.from_file(profile_name=os.environ['OCI_PROFILE'])
ce = oci.container_engine.ContainerEngineClient(cfg)
net = oci.core.VirtualNetworkClient(cfg)
iam = oci.identity.IdentityClient(cfg)
cluster_id = os.environ['CLUSTER_ID']
cluster = ce.get_cluster(cluster_id).data
# Pick the private "nodesubnet" in the cluster's VCN.
node_subnet = None
for s in net.list_subnets(compartment_id=cluster.compartment_id, vcn_id=cluster.vcn_id).data:
    if 'nodesubnet' in (s.display_name or '').lower() or (s.prohibit_public_ip_on_vnic and s.cidr_block != '10.0.0.0/28'):
        node_subnet = s.id
        break
if not node_subnet:
    print("no node subnet found", file=sys.stderr); sys.exit(1)
# Pick ADs from the region.
ads = [ad.name for ad in iam.list_availability_domains(compartment_id=cfg['tenancy']).data]
# Find the newest Oracle Linux 8 OKE image matching the cluster k8s version.
opts = ce.get_node_pool_options(node_pool_option_id=cluster_id).data
image_id = None
for src in (opts.sources or []):
    sn = src.source_name or ''
    if 'Oracle-Linux-8' in sn and 'aarch' not in sn.lower() and 'GPU' not in sn and cluster.kubernetes_version.lstrip('v') in sn:
        image_id = src.image_id
        break
if not image_id:
    print("no image found", file=sys.stderr); sys.exit(1)
# Check if a pool already exists for us.
for np in ce.list_node_pools(compartment_id=cluster.compartment_id, cluster_id=cluster_id).data:
    if np.name == 'octo-apm-managed-pool':
        print(f"NODE_POOL_ID={np.id}")
        sys.exit(0)
# Create.
work_req = ce.create_node_pool(
    oci.container_engine.models.CreateNodePoolDetails(
        compartment_id=cluster.compartment_id,
        cluster_id=cluster_id,
        name='octo-apm-managed-pool',
        kubernetes_version=cluster.kubernetes_version,
        node_shape=os.environ['OKE_NODE_SHAPE'],
        node_shape_config=oci.container_engine.models.CreateNodeShapeConfigDetails(
            ocpus=float(os.environ['OKE_NODE_OCPUS']),
            memory_in_gbs=float(os.environ['OKE_NODE_MEMORY_GBS']),
        ),
        node_source_details=oci.container_engine.models.NodeSourceViaImageDetails(
            source_type='IMAGE',
            image_id=image_id,
            boot_volume_size_in_gbs=int(os.environ['OKE_NODE_BOOT_VOLUME_GBS']),
        ),
        node_config_details=oci.container_engine.models.CreateNodePoolNodeConfigDetails(
            size=int(os.environ['OKE_NODE_POOL_SIZE']),
            placement_configs=[
                oci.container_engine.models.NodePoolPlacementConfigDetails(
                    availability_domain=ads[0],
                    subnet_id=node_subnet,
                )
            ],
            # Cluster uses OCI_VCN_IP_NATIVE — node pool must match or
            # the API rejects with "pod network options didn't match".
            node_pool_pod_network_option_details=(
                oci.container_engine.models.OciVcnIpNativePodNetworkOptionDetails(
                    cni_type="OCI_VCN_IP_NATIVE",
                    pod_subnet_ids=[node_subnet],
                )
                if cluster.cluster_pod_network_options
                and any(
                    p.cni_type == "OCI_VCN_IP_NATIVE"
                    for p in (cluster.cluster_pod_network_options or [])
                )
                else oci.container_engine.models.FlannelOverlayPodNetworkOptionDetails(
                    cni_type="FLANNEL_OVERLAY",
                )
            ),
        ),
        freeform_tags={"project": "octo-apm-demo", "managed-by": "bootstrap.sh"},
    )
).headers['opc-work-request-id']
print(f"WORK_REQ={work_req}")
# Poll the work request until the node pool is ACCEPTED/SUCCEEDED.
deadline = time.time() + 600
while time.time() < deadline:
    wr = ce.get_work_request(work_req).data
    print(f"  state={wr.status}", flush=True)
    if wr.status == 'SUCCEEDED':
        break
    if wr.status in ('FAILED', 'CANCELED'):
        print("node pool create failed", file=sys.stderr); sys.exit(1)
    time.sleep(20)
# Find the node pool we just created.
for np in ce.list_node_pools(compartment_id=cluster.compartment_id, cluster_id=cluster_id).data:
    if np.name == 'octo-apm-managed-pool':
        print(f"NODE_POOL_ID={np.id}")
        break
PYEOF
        _yellow "Waiting up to 10 min for node(s) to register as Ready…"
        for _ in $(seq 1 60); do
            n=$(kubectl get nodes -l oke.oraclecloud.com/node.info.managed=true -o json 2>/dev/null | python3 -c "import sys,json; print(sum(1 for n in json.load(sys.stdin).get('items',[]) if any(c['type']=='Ready' and c['status']=='True' for c in n.get('status',{}).get('conditions',[]))))" 2>/dev/null || echo 0)
            if [[ "${n}" -ge 1 ]]; then
                _green "Managed nodes Ready: ${n}"
                break
            fi
            sleep 10
        done
        # Re-run the nginx install now that we have a managed node.
        helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
        helm repo update >/dev/null 2>&1 || true
        cat > /tmp/_octo-nginx-values.yaml <<EOF
controller:
  replicaCount: 2
  service:
    type: LoadBalancer
    annotations:
      service.beta.kubernetes.io/oci-load-balancer-shape: "flexible"
      service.beta.kubernetes.io/oci-load-balancer-shape-flex-min: "10"
      service.beta.kubernetes.io/oci-load-balancer-shape-flex-max: "100"
  nodeSelector:
    oke.oraclecloud.com/node.info.managed: "true"
  ingressClassResource:
    default: true
EOF
        helm upgrade --install nginx-ingress ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace -f /tmp/_octo-nginx-values.yaml --wait --timeout 5m >/dev/null
        EXISTING_INGRESS_SERVICE="$(ingress_controller_service_name || true)"
        _green "nginx-ingress installed (pinned to managed nodes via nodeSelector)"
    else
        _yellow "OKE_ADD_NODE_POOL_IF_VIRTUAL=false — external exposure skipped."
        _yellow "To expose externally: run the OCI Native Ingress Controller add-on install."
        _yellow "Alternative: rerun with OKE_ADD_NODE_POOL_IF_VIRTUAL=true."
        exit 0
    fi
else
    _yellow "INSTALL_NGINX_INGRESS=false and no shared ingress controller detected"
    exit 1
fi

# ── Step 9: Ingress objects ───────────────────────────────────────────
section "Step 9 — Ingress objects"
TLS_ENABLED=false
if [[ "${TLS_MODE}" != "skip" ]]; then
    if OCI_CERT_ID="$(ensure_tls_secrets_from_oci_certificate 2>/dev/null)"; then
        TLS_ENABLED=true
        _green "TLS enabled via OCI certificate ${OCI_CERT_ID}"
    else
        _yellow "TLS secret provisioning skipped for ${DNS_BASE_DOMAIN} (TLS_MODE=${TLS_MODE})"
        if [[ "${TLS_REQUIRED}" == "true" ]]; then
            _red "TLS_REQUIRED=true but no usable OCI certificate was found"
            exit 1
        fi
    fi
fi

SSL_REDIRECT=false
if [[ "${TLS_ENABLED}" == "true" ]]; then
    SSL_REDIRECT=true
fi
for spec in \
    "${K8S_NAMESPACE_SHOP}|${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}|octo-drone-shop|8080" \
    "${K8S_NAMESPACE_CRM}|${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}|enterprise-crm-portal|8080"; do
    IFS="|" read -r ns host svc port <<< "$spec"
    cat <<EOF | kubectl apply -f - >/dev/null
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${svc}-ingress
  namespace: ${ns}
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "${SSL_REDIRECT}"
spec:
  ingressClassName: ${INGRESS_CLASS}
  rules:
    - host: ${host}
      http:
        paths:
          - pathType: Prefix
            path: /
            backend:
              service:
                name: ${svc}
                port:
                  number: ${port}
$(if [[ "${TLS_ENABLED}" == "true" ]]; then cat <<EOF2
  tls:
    - hosts:
        - ${host}
      secretName: ${TLS_SECRET_NAME}
EOF2
fi)
EOF
done
_green "Ingress objects applied (class=${INGRESS_CLASS})"

# ── Step 10: DNS ──────────────────────────────────────────────────────
section "Step 10 — DNS (${DNS_MODE})"
INGRESS_SERVICE_NAME="$(ingress_controller_service_name || true)"
[[ -n "${INGRESS_SERVICE_NAME}" ]] || { _red "ingress controller service not found"; exit 1; }
INGRESS_IP=$(kubectl -n ingress-nginx get svc "${INGRESS_SERVICE_NAME}" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
if [[ -z "${INGRESS_IP}" ]]; then
    _yellow "Waiting 30s for nginx LB IP…"
    sleep 30
    INGRESS_IP=$(kubectl -n ingress-nginx get svc "${INGRESS_SERVICE_NAME}" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
fi
[[ -n "${INGRESS_IP}" ]] || { _red "nginx-ingress LB IP not ready"; exit 1; }
_green "nginx-ingress IP: ${INGRESS_IP}"

# Persist for destroy.sh so it knows whether/which records to remove.
{
    echo "export INGRESS_IP=${INGRESS_IP}"
    echo "export DNS_MODE=${DNS_MODE}"
    echo "export INGRESS_SERVICE_NAME=${INGRESS_SERVICE_NAME}"
    echo "export TLS_ENABLED=${TLS_ENABLED}"
    echo "export TLS_SECRET_NAME=${TLS_SECRET_NAME}"
    echo "export SHOP_FQDN=${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
    echo "export CRM_FQDN=${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
} >> "${TENANCY_CACHE}"

case "${DNS_MODE}" in
auto)
    # Try to PATCH the OCI DNS zone. Fall through to `manual` if the zone
    # doesn't exist or the profile lacks permission — still useful output.
    if OCI_PROFILE="${OCI_PROFILE}" \
       DNS_BASE_DOMAIN="${DNS_BASE_DOMAIN}" \
       SHOP_SUBDOMAIN="${SHOP_SUBDOMAIN}" \
       CRM_SUBDOMAIN="${CRM_SUBDOMAIN}" \
       INGRESS_IP="${INGRESS_IP}" python3 - <<'PYEOF'; then
import os, oci, sys
cfg = oci.config.from_file(profile_name=os.environ['OCI_PROFILE'])
dns = oci.dns.DnsClient(cfg)
zone = os.environ['DNS_BASE_DOMAIN']
ingress_ip = os.environ['INGRESS_IP']
try:
    for sub in (os.environ['SHOP_SUBDOMAIN'], os.environ['CRM_SUBDOMAIN']):
        name = f"{sub}.{zone}"
        dns.patch_domain_records(
            zone_name_or_id=zone, domain=name,
            patch_domain_records_details=oci.dns.models.PatchDomainRecordsDetails(
                items=[
                    oci.dns.models.RecordOperation(operation="REMOVE", domain=name, rtype="A"),
                    oci.dns.models.RecordOperation(operation="ADD", domain=name, rtype="A", ttl=60, rdata=ingress_ip),
                ],
            ),
        )
        print(f"  A {name} -> {ingress_ip}", flush=True)
except oci.exceptions.ServiceError as exc:
    print(f"OCI DNS PATCH failed: {exc.status} {exc.code} - {exc.message[:120]}", file=sys.stderr)
    sys.exit(2)
PYEOF
        _green "OCI DNS records updated"
    else
        _yellow "OCI DNS zone ${DNS_BASE_DOMAIN} not manageable — falling back to manual mode."
        DNS_MODE=manual
    fi
    ;;
esac

if [[ "${DNS_MODE}" == "manual" ]]; then
    cat <<EOF

${YELLOW:-}────────────────────────────────────────────────────────────────
  MANUAL DNS — add these records at your DNS provider (Cloudflare,
  Route 53, NS1, Namecheap, in-house BIND, …):

    ${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}.   A   ${INGRESS_IP}   TTL 60
    ${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}.    A   ${INGRESS_IP}   TTL 60

  Once propagated, curl-test:
    curl -v http://${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}/ready
    curl -v http://${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}/ready

  Until then bootstrap.sh verifies via Host: header (see next step).
────────────────────────────────────────────────────────────────
EOF
fi

if [[ "${DNS_MODE}" == "skip" ]]; then
    _yellow "DNS_MODE=skip — no DNS action. Smoke test will use Host: header only."
fi

# ── Step 11: Smoke test ───────────────────────────────────────────────
section "Step 11 — Smoke test"
for host in "${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}" "${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}"; do
    # Try via ingress IP directly (DNS propagation takes up to TTL).
    code=$(curl -sS -m 10 -H "Host: ${host}" -o /dev/null -w "%{http_code}" "http://${INGRESS_IP}/" 2>/dev/null || echo 000)
    ready=$(curl -sS -m 10 -H "Host: ${host}" "http://${INGRESS_IP}/ready" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('ready','?'))" 2>/dev/null || echo "?")
    [[ "${code}" == "200" || "${code}" == "302" ]] && \
        _green "  ${host}: / → HTTP ${code}, /ready ready=${ready}" || \
        _red   "  ${host}: / → HTTP ${code}, /ready ready=${ready}"
    if [[ "${TLS_ENABLED}" == "true" ]]; then
        https_code=$(curl -sS -m 15 --resolve "${host}:443:${INGRESS_IP}" -o /dev/null -w "%{http_code}" "https://${host}/" 2>/dev/null || echo 000)
        https_ready=$(curl -sS -m 15 --resolve "${host}:443:${INGRESS_IP}" "https://${host}/ready" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('ready','?'))" 2>/dev/null || echo "?")
        [[ "${https_code}" == "200" || "${https_code}" == "302" ]] && \
            _green "  ${host}: / → HTTPS ${https_code}, /ready ready=${https_ready}" || \
            _red   "  ${host}: / → HTTPS ${https_code}, /ready ready=${https_ready}"
    fi
done

section "Bootstrap complete"
_green "  ATP DSN:                    ${ATP_DSN}"
if [[ "${TLS_ENABLED}" == "true" ]]; then
    _green "  Shop URL:                   https://${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
    _green "  CRM  URL:                   https://${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
else
    _green "  Shop URL:                   http://${SHOP_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
    _green "  CRM  URL:                   http://${CRM_SUBDOMAIN}.${DNS_BASE_DOMAIN}"
fi
_green "  kubectl context:            ${KUBE_CTX}"
_green "  Tenancy cache:              ${TENANCY_CACHE}"
_green "  Terraform tfvars:           ${TFVARS}"
_yellow "Destroy with: ./deploy/destroy.sh"
