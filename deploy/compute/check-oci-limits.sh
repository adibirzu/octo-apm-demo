#!/usr/bin/env bash
# Check OCI service-limit availability for the two-instance Compute stack.
#
# This script calls OCI read-only APIs. It does not create resources.
#
# Usage:
#   OCI_PROFILE=cap \
#   TENANCY_OCID=ocid1.tenancy.oc1..example \
#   COMPARTMENT_ID=ocid1.compartment.oc1..example \
#   ./deploy/compute/check-oci-limits.sh

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

OCI_PROFILE="${OCI_PROFILE:-${oci_profile:-${TF_VAR_oci_profile:-DEFAULT}}}"
TENANCY_OCID="${TENANCY_OCID:-${TF_VAR_tenancy_ocid:-}}"
COMPARTMENT_ID="${COMPARTMENT_ID:-${TF_VAR_compartment_id:-}}"
AVAILABILITY_DOMAIN="${AVAILABILITY_DOMAIN:-${TF_VAR_availability_domain_name:-}}"
SHOP_AVAILABILITY_DOMAIN="${SHOP_AVAILABILITY_DOMAIN:-${TF_VAR_shop_availability_domain_name:-}}"
CRM_AVAILABILITY_DOMAIN="${CRM_AVAILABILITY_DOMAIN:-${TF_VAR_crm_availability_domain_name:-}}"
INSTANCE_SHAPE="${INSTANCE_SHAPE:-${TF_VAR_instance_shape:-VM.Standard.E5.Flex}}"
INSTANCE_OCPUS="${INSTANCE_OCPUS:-${TF_VAR_instance_ocpus:-2}}"
INSTANCE_MEMORY_GBS="${INSTANCE_MEMORY_GBS:-${TF_VAR_instance_memory_gbs:-16}}"
ATP_ECPU_COUNT="${ATP_ECPU_COUNT:-${TF_VAR_atp_compute_count:-2}}"
LB_MAX_BANDWIDTH_MBPS="${LB_MAX_BANDWIDTH_MBPS:-${TF_VAR_lb_max_bandwidth_mbps:-100}}"
CREATE_NETWORK="${CREATE_NETWORK:-${TF_VAR_create_network:-true}}"
CREATE_LOAD_BALANCER="${CREATE_LOAD_BALANCER:-${TF_VAR_create_load_balancer:-true}}"

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

if ! command -v oci >/dev/null 2>&1; then
    red "oci CLI is required"
    exit 1
fi

if [[ -z "${TENANCY_OCID}" ]]; then
    TENANCY_OCID="$(python3 - "${OCI_PROFILE}" <<'PY'
import configparser
import os
import sys

profile = sys.argv[1]
cfg = configparser.ConfigParser()
cfg.read(os.path.expanduser("~/.oci/config"))
print(cfg.get(profile, "tenancy", fallback=""))
PY
)"
fi

if [[ -z "${TENANCY_OCID}" ]]; then
    red "TENANCY_OCID is required or must be present in OCI profile ${OCI_PROFILE}"
    exit 1
fi

if [[ -z "${COMPARTMENT_ID}" ]]; then
    red "COMPARTMENT_ID is required"
    exit 1
fi

is_true() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
        true|1|yes|y) return 0 ;;
        *) return 1 ;;
    esac
}

multiply_decimal() {
    python3 - "$1" "$2" <<'PY'
import decimal
import sys

left = decimal.Decimal(sys.argv[1])
right = decimal.Decimal(sys.argv[2])
value = left * right
print(value.normalize() if value == value.to_integral() else value)
PY
}

if [[ -z "${AVAILABILITY_DOMAIN}" && ( -z "${SHOP_AVAILABILITY_DOMAIN}" || -z "${CRM_AVAILABILITY_DOMAIN}" ) ]]; then
    AVAILABILITY_DOMAIN="$(
        oci iam availability-domain list \
            --profile "${OCI_PROFILE}" \
            --compartment-id "${TENANCY_OCID}" \
            --query 'data[0].name' \
            --raw-output
    )"
fi

SHOP_AVAILABILITY_DOMAIN="${SHOP_AVAILABILITY_DOMAIN:-${AVAILABILITY_DOMAIN}}"
CRM_AVAILABILITY_DOMAIN="${CRM_AVAILABILITY_DOMAIN:-${AVAILABILITY_DOMAIN}}"

case "${INSTANCE_SHAPE}" in
    *Standard.E5*) compute_core_limit="standard-e5-core-count"; compute_memory_limit="standard-e5-memory-count" ;;
    *Standard.E4*) compute_core_limit="standard-e4-core-count"; compute_memory_limit="standard-e4-memory-count" ;;
    *Standard.E3*) compute_core_limit="standard-e3-core-ad-count"; compute_memory_limit="standard-e3-memory-count" ;;
    *Standard.A1*) compute_core_limit="standard-a1-core-count"; compute_memory_limit="standard-a1-memory-count" ;;
    *)
        red "Unsupported shape for automatic limit mapping: ${INSTANCE_SHAPE}"
        exit 1
        ;;
esac

failures=0

check_availability() {
    local label="$1"
    local service="$2"
    local limit_name="$3"
    local required="$4"
    local ad="${5:-}"

    local args=(limits resource-availability get --profile "${OCI_PROFILE}" --compartment-id "${COMPARTMENT_ID}" --service-name "${service}" --limit-name "${limit_name}" --output json)
    if [[ -n "${ad}" ]]; then
        args+=(--availability-domain "${ad}")
    fi

    local json
    if ! json="$(oci "${args[@]}" 2>/tmp/octo-limit-error.log)"; then
        yellow "WARN ${label}: availability API did not return data for ${service}/${limit_name}"
        sed 's/^/     /' /tmp/octo-limit-error.log >&2
        return 0
    fi

    local available used
    read -r available used < <(python3 -c 'import json,sys; payload=json.load(sys.stdin)["data"]; print(payload.get("available"), payload.get("used"))' <<<"${json}")

    if [[ -z "${available}" || "${available}" == "None" || "${available}" == "null" ]]; then
        yellow "WARN ${label}: available is not reported (used=${used})"
        return 0
    fi

    if python3 - "${available}" "${required}" <<'PY'
import decimal
import sys
available = decimal.Decimal(sys.argv[1])
required = decimal.Decimal(sys.argv[2])
raise SystemExit(0 if available >= required else 1)
PY
    then
        green "PASS ${label}: available=${available}, required=${required}, used=${used}"
    else
        red "FAIL ${label}: available=${available}, required=${required}, used=${used}"
        failures=$((failures + 1))
    fi
}

echo "OCI profile: ${OCI_PROFILE}"
echo "Compartment: ${COMPARTMENT_ID}"
echo "Shop availability domain: ${SHOP_AVAILABILITY_DOMAIN}"
echo "CRM availability domain: ${CRM_AVAILABILITY_DOMAIN}"
echo

if [[ "${SHOP_AVAILABILITY_DOMAIN}" == "${CRM_AVAILABILITY_DOMAIN}" ]]; then
    required_compute_ocpus="$(multiply_decimal "${INSTANCE_OCPUS}" 2)"
    required_compute_memory="$(multiply_decimal "${INSTANCE_MEMORY_GBS}" 2)"
    check_availability "Compute OCPUs (${INSTANCE_SHAPE}, shop+crm)" compute "${compute_core_limit}" "${required_compute_ocpus}" "${SHOP_AVAILABILITY_DOMAIN}"
    check_availability "Compute memory GB (${INSTANCE_SHAPE}, shop+crm)" compute "${compute_memory_limit}" "${required_compute_memory}" "${SHOP_AVAILABILITY_DOMAIN}"
else
    check_availability "Shop Compute OCPUs (${INSTANCE_SHAPE})" compute "${compute_core_limit}" "${INSTANCE_OCPUS}" "${SHOP_AVAILABILITY_DOMAIN}"
    check_availability "Shop Compute memory GB (${INSTANCE_SHAPE})" compute "${compute_memory_limit}" "${INSTANCE_MEMORY_GBS}" "${SHOP_AVAILABILITY_DOMAIN}"
    check_availability "CRM Compute OCPUs (${INSTANCE_SHAPE})" compute "${compute_core_limit}" "${INSTANCE_OCPUS}" "${CRM_AVAILABILITY_DOMAIN}"
    check_availability "CRM Compute memory GB (${INSTANCE_SHAPE})" compute "${compute_memory_limit}" "${INSTANCE_MEMORY_GBS}" "${CRM_AVAILABILITY_DOMAIN}"
fi
check_availability "Autonomous Transaction Processing ECPU" database atp-ecpu-count "${ATP_ECPU_COUNT}"
if is_true "${CREATE_LOAD_BALANCER}"; then
    check_availability "Flexible Load Balancer count" load-balancer lb-flexible-count 1
    check_availability "Flexible Load Balancer bandwidth Mbps" load-balancer lb-flexible-bandwidth-sum "${LB_MAX_BANDWIDTH_MBPS}"
fi
if is_true "${CREATE_NETWORK}"; then
    check_availability "VCN count" vcn vcn-count 1
fi

rm -f /tmp/octo-limit-error.log
exit "${failures}"
