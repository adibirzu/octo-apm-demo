#!/usr/bin/env bash
# Render /opt/octo/runtime.env for one Compute role from Terraform outputs
# plus operator-provided secret environment variables.
#
# This script reads local Terraform outputs only. It does not call OCI.
# Required secret env vars:
#   INTERNAL_SERVICE_KEY ORACLE_PASSWORD ORACLE_WALLET_PASSWORD
#   OCI_APM_PRIVATE_DATAKEY
# Role-specific:
#   shop: AUTH_TOKEN_SECRET
#   crm:  APP_SECRET_KEY BOOTSTRAP_ADMIN_PASSWORD
#
# Usage:
#   ROLE=shop ./deploy/compute/render-runtime-env.sh > runtime.shop.env
#   ROLE=crm  ./deploy/compute/render-runtime-env.sh > runtime.crm.env

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
TF_DIR="${TF_DIR:-${SCRIPT_DIR}/terraform}"
ROLE="${ROLE:-}"

if [[ "${ROLE}" != "shop" && "${ROLE}" != "crm" ]]; then
    echo "ROLE must be shop or crm" >&2
    exit 1
fi

require_env() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        echo "Missing required env: ${name}" >&2
        exit 1
    fi
}

for name in INTERNAL_SERVICE_KEY ORACLE_PASSWORD ORACLE_WALLET_PASSWORD OCI_APM_PRIVATE_DATAKEY; do
    require_env "${name}"
done

if [[ "${ROLE}" == "shop" ]]; then
    require_env AUTH_TOKEN_SECRET
else
    require_env APP_SECRET_KEY
    require_env BOOTSTRAP_ADMIN_PASSWORD
fi

outputs_file="$(mktemp)"
trap 'rm -f "${outputs_file}"' EXIT
terraform -chdir="${TF_DIR}" output -json >"${outputs_file}"

python3 - "${ROLE}" "${outputs_file}" <<'PY'
import json
import os
import shlex
import sys

role = sys.argv[1]
with open(sys.argv[2], encoding="utf-8") as handle:
    data = json.load(handle)

def out(name):
    return data[name]["value"]

ips = out("instance_ips")
logging = out("logging")
apm = out("apm") or {}
hints = out("runtime_env_hints")[role]
atp = out("atp")

dns_domain = os.environ.get("DNS_DOMAIN") or ".".join(ips[role]["hostname"].split(".")[1:])
ocir_region = os.environ.get("OCIR_REGION", "")
ocir_tenancy = os.environ.get("OCIR_TENANCY", "")
image_tag = os.environ.get("IMAGE_TAG", "latest")
if role == "shop":
    image_name = "octo-drone-shop"
else:
    image_name = "enterprise-crm-portal"

app_image = os.environ.get("APP_IMAGE") or f"{ocir_region}.ocir.io/{ocir_tenancy}/{image_name}:{image_tag}"

values = {
    "OCTO_COMPUTE_ROLE": role,
    "CONTAINER_RUNTIME": os.environ.get("CONTAINER_RUNTIME", "podman"),
    "APP_IMAGE": app_image,
    "APP_IMAGE_PULL_POLICY": os.environ.get("APP_IMAGE_PULL_POLICY", "if-not-present"),
    "APP_IMAGE_BUILD_ENABLED": os.environ.get("APP_IMAGE_BUILD_ENABLED", "false"),
    "APP_IMAGE_BUILD_CONTEXT": os.environ.get("APP_IMAGE_BUILD_CONTEXT", "/opt/octo/repo"),
    "APP_IMAGE_DOCKERFILE": os.environ.get("APP_IMAGE_DOCKERFILE", f"{role}/Dockerfile"),
    "OCIR_REGISTRY": os.environ.get("OCIR_REGISTRY", f"{ocir_region}.ocir.io" if ocir_region else ""),
    "OCIR_USERNAME": os.environ.get("OCIR_USERNAME", ""),
    "OCIR_AUTH_TOKEN": os.environ.get("OCIR_AUTH_TOKEN", ""),
    "APP_NAME": hints["app_name"],
    "APP_RUNTIME": "compute",
    "OTEL_SERVICE_NAME": hints["otel_service_name"],
    "SERVICE_INSTANCE_ID": hints["service_instance_id"],
    "DNS_DOMAIN": dns_domain,
    "ENVIRONMENT": os.environ.get("ENVIRONMENT", "production"),
    "DEMO_STACK_NAME": os.environ.get("DEMO_STACK_NAME", "octo-compute"),
    "SERVICE_NAMESPACE": os.environ.get("SERVICE_NAMESPACE", "octo"),
    "PORT": os.environ.get("PORT", "8080"),
    "APP_PORT": os.environ.get("APP_PORT", "8080"),
    "APP_CONTAINER_UID": os.environ.get("APP_CONTAINER_UID", "10001" if role == "shop" else "1000"),
    "APP_CONTAINER_GID": os.environ.get("APP_CONTAINER_GID", "10001" if role == "shop" else "1000"),
    "OCI_COMPARTMENT_ID": os.environ.get("OCI_COMPARTMENT_ID", ""),
    "INTERNAL_SERVICE_KEY": os.environ["INTERNAL_SERVICE_KEY"],
    "ORACLE_DSN": os.environ.get("ORACLE_DSN", "octoatp_low"),
    "ORACLE_USER": os.environ.get("ORACLE_USER", "ADMIN"),
    "ORACLE_PASSWORD": os.environ["ORACLE_PASSWORD"],
    "ORACLE_WALLET_PASSWORD": os.environ["ORACLE_WALLET_PASSWORD"],
    "ORACLE_WALLET_DIR": "/opt/oracle/wallet",
    "ATP_OCID": atp["id"],
    "DATABASE_OBSERVABILITY_ENABLED": os.environ.get("DATABASE_OBSERVABILITY_ENABLED", "true"),
    "OCI_AUTH_MODE": os.environ.get("OCI_AUTH_MODE", "instance_principal"),
    "OCI_APM_ENDPOINT": apm.get("endpoint", ""),
    "OCI_APM_PRIVATE_DATAKEY": os.environ["OCI_APM_PRIVATE_DATAKEY"],
    "OCI_APM_PUBLIC_DATAKEY": os.environ.get("OCI_APM_PUBLIC_DATAKEY", ""),
    "OCI_APM_RUM_ENDPOINT": apm.get("rum_endpoint", ""),
    "OCI_APM_WEB_APPLICATION": os.environ.get("OCI_APM_WEB_APPLICATION", "octo-drone-shop-web"),
    "OCI_APM_RUM_PUBLIC_DATAKEY": os.environ.get("OCI_APM_PUBLIC_DATAKEY", ""),
    "OTEL_TRACES_SAMPLER": os.environ.get("OTEL_TRACES_SAMPLER", "always_on"),
    "OTEL_PYTHON_LOG_CORRELATION": os.environ.get("OTEL_PYTHON_LOG_CORRELATION", "true"),
    "OTLP_LOG_EXPORT_ENABLED": os.environ.get("OTLP_LOG_EXPORT_ENABLED", "false"),
    "OCI_LOG_GROUP_ID": logging["log_group_id"],
    "OCI_LOG_ID": logging["app_log_id"],
    "OCI_LOG_CHAOS_AUDIT_ID": logging["chaos_audit_log_id"],
    "OCI_LOG_SECURITY_ID": logging["security_log_id"],
    "IDCS_DOMAIN_URL": os.environ.get("IDCS_DOMAIN_URL", ""),
    "IDCS_CLIENT_ID": os.environ.get("IDCS_CLIENT_ID", ""),
    "IDCS_CLIENT_SECRET": os.environ.get("IDCS_CLIENT_SECRET", ""),
}

if role == "shop":
    values.update({
        "AUTH_TOKEN_SECRET": os.environ["AUTH_TOKEN_SECRET"],
        "APP_SECRET_KEY": "",
        "BOOTSTRAP_ADMIN_PASSWORD": "",
        "SERVICE_CRM_URL": hints["service_crm_url"],
        "CRM_PUBLIC_URL": hints["crm_public_url"],
        "CRM_BASE_URL": hints["crm_public_url"],
        "SERVICE_SHOP_URL": "",
    })
else:
    values.update({
        "AUTH_TOKEN_SECRET": "",
        "APP_SECRET_KEY": os.environ["APP_SECRET_KEY"],
        "BOOTSTRAP_ADMIN_PASSWORD": os.environ["BOOTSTRAP_ADMIN_PASSWORD"],
        "SERVICE_CRM_URL": "",
        "CRM_PUBLIC_URL": "",
        "CRM_BASE_URL": hints["crm_base_url"],
        "SERVICE_SHOP_URL": hints["service_shop_url"],
    })

for key, value in values.items():
    print(f"{key}={shlex.quote(str(value))}")
PY
