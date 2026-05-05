#!/usr/bin/env bash
# Offline validator for the two-instance Compute deployment surface.
#
# This intentionally does not call OCI and does not require an OCI profile.
# It validates shell syntax/help, compose rendering, cloud-init YAML, nginx
# template rendering, and Terraform init/validate.
#
# Usage:
#   ./deploy/compute/validate.sh

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FAILED=0

ok() { printf '\033[32m  PASS  \033[0m%s\n' "$*"; }
fail() { printf '\033[31m  FAIL  \033[0m%s\n' "$*" >&2; FAILED=1; }
warn() { printf '\033[33m  WARN  \033[0m%s\n' "$*"; }

for script in "${SCRIPT_DIR}/install.sh" "${SCRIPT_DIR}/render-runtime-env.sh" "${SCRIPT_DIR}/deploy-apps.sh" "${SCRIPT_DIR}/stack-package.sh" "${SCRIPT_DIR}/check-oci-limits.sh" "${SCRIPT_DIR}/configure-lb-certificate.sh" "${SCRIPT_DIR}/verify-deployment.sh" "${SCRIPT_DIR}/validate.sh"; do
    if bash -n "${script}"; then
        ok "${script#${REPO_ROOT}/} bash -n"
    else
        fail "${script#${REPO_ROOT}/} bash -n"
    fi
    if bash "${script}" --help | grep -q "Usage:"; then
        ok "${script#${REPO_ROOT}/} --help"
    else
        fail "${script#${REPO_ROOT}/} --help"
    fi
done

tmp_env="$(mktemp)"
cat >"${tmp_env}" <<'EOF'
OCTO_COMPUTE_ROLE=shop
CONTAINER_RUNTIME=podman
APP_IMAGE=iad.ocir.io/example/octo-drone-shop:verify
APP_IMAGE_PULL_POLICY=if-not-present
APP_IMAGE_BUILD_ENABLED=false
APP_IMAGE_BUILD_CONTEXT=/opt/octo/repo
APP_IMAGE_DOCKERFILE=shop/Dockerfile
OCIR_REGISTRY=iad.ocir.io
OCIR_USERNAME=
OCIR_AUTH_TOKEN=
APP_NAME=octo-drone-shop
APP_RUNTIME=compute
OTEL_SERVICE_NAME=octo-drone-shop
SERVICE_INSTANCE_ID=verify-shop
DNS_DOMAIN=verify.example.invalid
ENVIRONMENT=production
DEMO_STACK_NAME=octo-compute
SERVICE_NAMESPACE=octo
PORT=8080
APP_PORT=8080
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..verify
SERVICE_CRM_URL=http://10.0.1.20:8080
CRM_PUBLIC_URL=https://crm.verify.example.invalid
CRM_BASE_URL=https://crm.verify.example.invalid
SERVICE_SHOP_URL=http://10.0.1.10:8080
INTERNAL_SERVICE_KEY=verify-internal-service-key
AUTH_TOKEN_SECRET=verify-auth-token-secret
APP_SECRET_KEY=verify-app-secret-key
BOOTSTRAP_ADMIN_PASSWORD=verify-admin-password
ORACLE_DSN=octoatp_low
ORACLE_USER=ADMIN
ORACLE_PASSWORD=verify-db-password
ORACLE_WALLET_PASSWORD=verify-wallet-password
ORACLE_WALLET_DIR=/opt/oracle/wallet
ATP_OCID=ocid1.autonomousdatabase.oc1..verify
DATABASE_OBSERVABILITY_ENABLED=true
OCI_AUTH_MODE=instance_principal
OCI_APM_ENDPOINT=https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.apm-agt.eu-frankfurt-1.oci.oraclecloud.com
OCI_APM_PRIVATE_DATAKEY=verify-apm-private-key
OCI_APM_PUBLIC_DATAKEY=verify-apm-public-key
OCI_APM_RUM_ENDPOINT=https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.apm-agt.eu-frankfurt-1.oci.oraclecloud.com
OCI_APM_RUM_PUBLIC_DATAKEY=verify-apm-public-key
OCI_LOG_GROUP_ID=ocid1.loggroup.oc1..verify
OCI_LOG_ID=ocid1.log.oc1..verify
OCI_LOG_CHAOS_AUDIT_ID=ocid1.log.oc1..verifychaos
OCI_LOG_SECURITY_ID=ocid1.log.oc1..verifysecurity
OTEL_TRACES_SAMPLER=always_on
OTEL_PYTHON_LOG_CORRELATION=true
OTLP_LOG_EXPORT_ENABLED=false
EOF

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    if docker compose -f "${SCRIPT_DIR}/app-compose.yml" --env-file "${tmp_env}" config >/dev/null; then
        ok "deploy/compute/app-compose.yml renders"
    else
        fail "deploy/compute/app-compose.yml renders"
    fi
else
    warn "docker compose not installed — skipped compute compose config"
fi

if OCTO_PUBLIC_HOSTNAME=shop.verify.example.invalid \
    envsubst '${OCTO_PUBLIC_HOSTNAME}' < "${SCRIPT_DIR}/nginx/app.conf.template" >/tmp/octo-compute-nginx.conf; then
    if command -v nginx >/dev/null 2>&1; then
        if nginx -t -c /tmp/octo-compute-nginx.conf >/dev/null 2>&1; then
            ok "deploy/compute nginx template validates"
        else
            fail "deploy/compute nginx template validates"
        fi
    else
        ok "deploy/compute nginx template renders"
    fi
else
    fail "deploy/compute nginx template renders"
fi

if grep -q -- "--env-file /opt/octo/container.env" "${SCRIPT_DIR}/systemd/octo-podman.service" && \
   grep -q -- "--env-file /opt/octo/container.env" "${SCRIPT_DIR}/systemd/octo-compute.service"; then
    ok "deploy/compute systemd units use container-runtime env file"
else
    fail "deploy/compute systemd units use container-runtime env file"
fi

python3 - "${SCRIPT_DIR}/terraform/cloud-init/compute.yaml.tftpl" <<'PY'
import base64
import pathlib
import re
import sys
import yaml

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for token in (
    "${role}",
    "${repo_url}",
    "${repo_ref}",
    "${dns_domain}",
    "${public_hostname}",
):
    text = text.replace(token, "verify")
text = text.replace("${runtime_env}", "      OCTO_COMPUTE_ROLE=shop\n      APP_IMAGE=verify")
text = text.replace("${bootstrap_file.path}", "/opt/octo/deploy/compute/install.sh")
text = text.replace("${bootstrap_file.permissions}", "0755")
text = text.replace(
    "${bootstrap_file.content}",
    base64.b64encode(b"#!/usr/bin/env bash\n").decode("ascii"),
)
text = re.sub(r"^%\{[^\n]*\}\s*$", "", text, flags=re.MULTILINE)
yaml.safe_load(text)
PY
if [[ "$?" -eq 0 ]]; then
    ok "deploy/compute cloud-init template parses as YAML"
else
    fail "deploy/compute cloud-init template parses as YAML"
fi

if command -v terraform >/dev/null 2>&1; then
    if terraform -chdir="${SCRIPT_DIR}/terraform" init -backend=false -input=false -no-color >/tmp/octo-compute-tf-init.log 2>&1 && \
       terraform -chdir="${SCRIPT_DIR}/terraform" validate -no-color >/tmp/octo-compute-tf-validate.log 2>&1; then
        ok "deploy/compute terraform validates"
    else
        fail "deploy/compute terraform validates"
        cat /tmp/octo-compute-tf-init.log /tmp/octo-compute-tf-validate.log | tail -40 | sed 's/^/         /'
    fi
else
    warn "terraform not installed — skipped compute terraform validate"
fi

package_log="$(mktemp)"
if bash "${SCRIPT_DIR}/stack-package.sh" >"${package_log}" 2>&1; then
    ok "deploy/compute Resource Manager package builds"
else
    fail "deploy/compute Resource Manager package builds"
    sed 's/^/         /' "${package_log}" | tail -20
fi

stack_zip="${SCRIPT_DIR}/build/octo-compute-stack.zip"
if [[ -f "${stack_zip}" ]] && unzip -tq "${stack_zip}" >/dev/null 2>&1; then
    ok "deploy/compute/build/octo-compute-stack.zip is a valid zip"
else
    fail "deploy/compute/build/octo-compute-stack.zip is a valid zip"
fi

if command -v terraform >/dev/null 2>&1 && [[ -f "${stack_zip}" ]]; then
    stack_tmp="$(mktemp -d)"
    if unzip -q "${stack_zip}" -d "${stack_tmp}" && \
       terraform -chdir="${stack_tmp}" init -backend=false -input=false -no-color >/tmp/octo-compute-stack-init.log 2>&1 && \
       terraform -chdir="${stack_tmp}" validate -no-color >/tmp/octo-compute-stack-validate.log 2>&1; then
        ok "deploy/compute Resource Manager package terraform validates"
    else
        fail "deploy/compute Resource Manager package terraform validates"
        cat /tmp/octo-compute-stack-init.log /tmp/octo-compute-stack-validate.log | tail -40 | sed 's/^/         /'
    fi
    rm -rf "${stack_tmp}"
fi

rm -f "${tmp_env}" /tmp/octo-compute-nginx.conf /tmp/octo-compute-tf-init.log /tmp/octo-compute-tf-validate.log \
    /tmp/octo-compute-stack-init.log /tmp/octo-compute-stack-validate.log "${package_log}"

exit "${FAILED}"
