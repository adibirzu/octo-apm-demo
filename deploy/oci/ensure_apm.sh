#!/usr/bin/env bash
# Ensure an OCI APM Domain exist in the target tenancy, and emit the
# env vars the app needs (OCI_APM_ENDPOINT,
# OCI_APM_PUBLIC_DATAKEY, OCI_APM_PRIVATE_DATAKEY, OCI_APM_RUM_ENDPOINT,
# OCI_APM_WEB_APPLICATION) on stdout for operator consumption.
#
# Idempotent: re-runs reuse the existing resources via terraform state.
#
# Modes:
#   --plan     Run terraform plan only (no changes). Default when $PLAN_ONLY=true.
#   --apply    Run terraform apply (requires explicit confirmation).
#   --print    Print current outputs from existing terraform state only.
#
# Required env:
#   COMPARTMENT_ID        OCI compartment OCID for the domain
#   TF_DIR (optional)     path to deploy/terraform (defaults to ../terraform)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${TF_DIR:-${SCRIPT_DIR}/../terraform}"
PLAN_ONLY="${PLAN_ONLY:-true}"

mode="plan"
for arg in "$@"; do
    case "$arg" in
        --plan)  mode="plan" ;;
        --apply) mode="apply" ;;
        --print) mode="print" ;;
        *) echo "Unknown arg: ${arg}" >&2; exit 2 ;;
    esac
done

: "${COMPARTMENT_ID:?Set COMPARTMENT_ID (compartment OCID)}"

if [[ ! -d "${TF_DIR}" ]]; then
    echo "Terraform directory not found: ${TF_DIR}" >&2
    exit 1
fi

export TF_VAR_compartment_id="${COMPARTMENT_ID}"
export TF_VAR_create_apm_domain="true"

# Inputs still required by the rest of main.tf. Safe defaults so plan works
# even before WAF/LA are configured.
: "${WAF_LOG_GROUP_ID:=}"
: "${LA_NAMESPACE:=}"
: "${LA_LOG_GROUP_ID:=}"
export TF_VAR_waf_log_group_id="${WAF_LOG_GROUP_ID}"
export TF_VAR_la_namespace="${LA_NAMESPACE}"
export TF_VAR_la_log_group_id="${LA_LOG_GROUP_ID}"

read_outputs_json() {
    terraform output -json 2>/dev/null || echo "{}"
}

print_apm_exports() {
    local outputs_json apm_endpoint rum_endpoint rum_app public_key private_key
    outputs_json="$(read_outputs_json)"
    apm_endpoint="$(
        OUTPUTS_JSON="${outputs_json}" python3 - <<'PY'
import json
import os

outputs = json.loads(os.environ["OUTPUTS_JSON"])
apm_domain = (outputs.get("apm_domain") or {}).get("value") or {}
print(apm_domain.get("apm_data_upload_endpoint", ""), end="")
PY
    )"
    rum_endpoint="$(
        OUTPUTS_JSON="${outputs_json}" python3 - <<'PY'
import json
import os

outputs = json.loads(os.environ["OUTPUTS_JSON"])
apm_domain = (outputs.get("apm_domain") or {}).get("value") or {}
print(apm_domain.get("rum_endpoint", ""), end="")
PY
    )"
    rum_app="$(
        OUTPUTS_JSON="${outputs_json}" python3 - <<'PY'
import json
import os

outputs = json.loads(os.environ["OUTPUTS_JSON"])
apm_domain = (outputs.get("apm_domain") or {}).get("value") or {}
print(apm_domain.get("rum_web_application_id", ""), end="")
PY
    )"
    public_key="$(
        OUTPUTS_JSON="${outputs_json}" python3 - <<'PY'
import json
import os

outputs = json.loads(os.environ["OUTPUTS_JSON"])
print((outputs.get("apm_public_datakey") or {}).get("value", ""), end="")
PY
    )"
    private_key="$(
        OUTPUTS_JSON="${outputs_json}" python3 - <<'PY'
import json
import os

outputs = json.loads(os.environ["OUTPUTS_JSON"])
print((outputs.get("apm_private_datakey") or {}).get("value", ""), end="")
PY
    )"

    if [[ -z "${apm_endpoint}" || -z "${public_key}" || -z "${private_key}" ]]; then
        echo "APM outputs are not present in the current Terraform state." >&2
        echo "Run with --apply first, or verify TF_VAR_create_apm_domain=true for this workspace." >&2
        return 1
    fi

    echo
    echo "# Export these env vars to wire the app to the provisioned APM Domain:"
    cat <<EOF
export OCI_APM_ENDPOINT="${apm_endpoint}"
export OCI_APM_RUM_ENDPOINT="${rum_endpoint:-${apm_endpoint}}"
export OCI_APM_WEB_APPLICATION="${rum_app}"
export OCI_APM_PUBLIC_DATAKEY="${public_key}"
export OCI_APM_PRIVATE_DATAKEY="${private_key}"
EOF
}

cd "${TF_DIR}"

case "${mode}" in
    plan)
        terraform init -input=false -backend=false
        terraform plan -input=false -target=module.apm_domain
        ;;
    apply)
        if [[ "${PLAN_ONLY}" == "true" ]]; then
            echo "PLAN_ONLY=true blocks --apply. Re-run with PLAN_ONLY=false to actually apply." >&2
            exit 1
        fi
        terraform init -input=false
        terraform apply -input=false -auto-approve -target=module.apm_domain
        ;;
    print)
        ;;
esac

if [[ "${mode}" == "apply" || "${mode}" == "print" ]]; then
    print_apm_exports
fi
