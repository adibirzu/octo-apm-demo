#!/usr/bin/env bash
# Configure the OCI Load Balancer HTTPS listener from local PEM files.
#
# The script reads certificate material into TF_VAR_* environment variables
# for a single Terraform plan/apply. It does not write PEM files into the repo.
#
# Usage:
#   ./deploy/compute/configure-lb-certificate.sh \
#     --certificate /path/to/fullchain.pem \
#     --private-key /path/to/privkey.pem \
#     [--ca-certificate /path/to/chain.pem] \
#     [--passphrase-file /path/to/passphrase.txt] \
#     [--profile cap] \
#     [--disable-http] \
#     [--apply]

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
CERTIFICATE_FILE=""
PRIVATE_KEY_FILE=""
CA_CERTIFICATE_FILE=""
PASSPHRASE_FILE=""
OCI_PROFILE_VALUE=""
APPLY=false
DISABLE_HTTP=false
SKIP_INIT=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_usage
            exit 0
            ;;
        --certificate)
            CERTIFICATE_FILE="${2:?--certificate requires a file path}"
            shift 2
            ;;
        --private-key)
            PRIVATE_KEY_FILE="${2:?--private-key requires a file path}"
            shift 2
            ;;
        --ca-certificate)
            CA_CERTIFICATE_FILE="${2:?--ca-certificate requires a file path}"
            shift 2
            ;;
        --passphrase-file)
            PASSPHRASE_FILE="${2:?--passphrase-file requires a file path}"
            shift 2
            ;;
        --terraform-dir)
            TERRAFORM_DIR="${2:?--terraform-dir requires a directory path}"
            shift 2
            ;;
        --profile)
            OCI_PROFILE_VALUE="${2:?--profile requires an OCI profile name}"
            shift 2
            ;;
        --disable-http)
            DISABLE_HTTP=true
            shift
            ;;
        --skip-init)
            SKIP_INIT=true
            shift
            ;;
        --apply)
            APPLY=true
            shift
            ;;
        *)
            printf 'Unknown option: %s\n\n' "$1" >&2
            show_usage >&2
            exit 2
            ;;
    esac
done

require_file() {
    local label="$1"
    local path="$2"
    if [[ -z "${path}" || ! -f "${path}" || ! -s "${path}" ]]; then
        printf '%s must point to a readable non-empty file.\n' "${label}" >&2
        exit 2
    fi
}

require_file "--certificate" "${CERTIFICATE_FILE}"
require_file "--private-key" "${PRIVATE_KEY_FILE}"
if [[ -n "${CA_CERTIFICATE_FILE}" ]]; then
    require_file "--ca-certificate" "${CA_CERTIFICATE_FILE}"
fi
if [[ -n "${PASSPHRASE_FILE}" ]]; then
    require_file "--passphrase-file" "${PASSPHRASE_FILE}"
fi
if [[ ! -d "${TERRAFORM_DIR}" ]]; then
    printf 'Terraform directory does not exist: %s\n' "${TERRAFORM_DIR}" >&2
    exit 2
fi

if command -v openssl >/dev/null 2>&1; then
    openssl x509 -in "${CERTIFICATE_FILE}" -noout >/dev/null
    if [[ -n "${CA_CERTIFICATE_FILE}" ]]; then
        openssl x509 -in "${CA_CERTIFICATE_FILE}" -noout >/dev/null
    fi
    if [[ -n "${PASSPHRASE_FILE}" ]]; then
        openssl pkey -in "${PRIVATE_KEY_FILE}" -passin "file:${PASSPHRASE_FILE}" -noout >/dev/null
    elif [[ -n "${LB_CERTIFICATE_PASSPHRASE:-}" ]]; then
        openssl pkey -in "${PRIVATE_KEY_FILE}" -passin "env:LB_CERTIFICATE_PASSPHRASE" -noout >/dev/null
    else
        openssl pkey -in "${PRIVATE_KEY_FILE}" -passin "pass:" -noout >/dev/null
    fi
fi

export TF_VAR_enable_lb_https=true
export TF_VAR_lb_certificate_public_certificate
export TF_VAR_lb_certificate_private_key
TF_VAR_lb_certificate_public_certificate="$(<"${CERTIFICATE_FILE}")"
TF_VAR_lb_certificate_private_key="$(<"${PRIVATE_KEY_FILE}")"

if [[ -n "${CA_CERTIFICATE_FILE}" ]]; then
    export TF_VAR_lb_certificate_ca_certificate
    TF_VAR_lb_certificate_ca_certificate="$(<"${CA_CERTIFICATE_FILE}")"
fi

if [[ -n "${PASSPHRASE_FILE}" ]]; then
    export TF_VAR_lb_certificate_passphrase
    TF_VAR_lb_certificate_passphrase="$(<"${PASSPHRASE_FILE}")"
elif [[ -n "${LB_CERTIFICATE_PASSPHRASE:-}" ]]; then
    export TF_VAR_lb_certificate_passphrase="${LB_CERTIFICATE_PASSPHRASE}"
fi

if [[ "${DISABLE_HTTP}" == "true" ]]; then
    export TF_VAR_enable_lb_http=false
fi

if [[ -n "${OCI_PROFILE_VALUE}" ]]; then
    export TF_VAR_oci_profile="${OCI_PROFILE_VALUE}"
fi

if [[ "${SKIP_INIT}" != "true" ]]; then
    terraform -chdir="${TERRAFORM_DIR}" init -input=false -no-color
fi

printf 'Prepared LB certificate variables for %s.\n' "${TERRAFORM_DIR}"
printf 'Note: Terraform state will contain the LB private key because OCI Load Balancer certificates are managed through Terraform.\n'

if [[ "${APPLY}" == "true" ]]; then
    terraform -chdir="${TERRAFORM_DIR}" apply -input=false -auto-approve -no-color
else
    terraform -chdir="${TERRAFORM_DIR}" plan -input=false -no-color
fi
