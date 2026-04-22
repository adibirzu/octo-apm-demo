#!/usr/bin/env bash
# Lab 01 — Your first trace.
# Usage: ./tools/workshop/verify-01.sh <trace_id>

source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

trace_id="${1:-${TRACE_ID:-}}"

if [[ -z "${trace_id}" ]]; then
    fail "trace_id required (pass as argv[1] or TRACE_ID env)"
    pass_or_fail "01"
fi

# Format check
if [[ "${trace_id}" =~ ^[0-9a-f]{32}$ ]]; then
    ok "trace_id format valid (32 hex)"
else
    fail "trace_id must be 32 lowercase hex chars (got '${trace_id}')"
fi

require_cmd oci
require_var OCI_APM_DOMAIN_ID

if [[ "${errors}" -eq 0 ]]; then
    if oci apm-traces trace get \
            --apm-domain-id "${OCI_APM_DOMAIN_ID}" \
            --trace-key "${trace_id}" >/dev/null 2>&1; then
        ok "trace appears in APM (HTTP 200)"
    else
        fail "trace not found in APM — wait 60s after the request and retry"
    fi

    spans_json=$(oci apm-traces trace get \
        --apm-domain-id "${OCI_APM_DOMAIN_ID}" \
        --trace-key "${trace_id}" 2>/dev/null \
        | jq -r '.data.spans // []')

    if echo "${spans_json}" | jq -e 'any(.attributes // {} | to_entries[]; .key=="service.name" and .value=="octo-drone-shop")' >/dev/null 2>&1; then
        ok "at least one span has service.name=octo-drone-shop"
    else
        warn "could not detect service.name=octo-drone-shop (may still be valid for cross-service traces)"
    fi
fi

pass_or_fail "01"
