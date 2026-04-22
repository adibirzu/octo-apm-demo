#!/usr/bin/env bash
# Lab 09 — Chaos drill.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

run_id="${1:-${RUN_ID:-}}"
[[ -z "${run_id}" ]] && { fail "run_id required"; pass_or_fail "09"; }

require_cmd oci
require_var LA_NAMESPACE

# Audit log row exists
audit=$(oci log-analytics query \
    --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'octo-chaos-audit' | where run_id = '${run_id}' and action = 'apply' | head limit = 1" 2>&1)

if echo "${audit}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "chaos profile was applied (audit log row exists)"
else
    fail "no audit row for run_id ${run_id}"
fi

# APM has traces tagged with run_id
require_var OCI_APM_DOMAIN_ID
trace_count=$(oci apm-traces trace search \
    --apm-domain-id "${OCI_APM_DOMAIN_ID}" \
    --query-details '{
        "queryType": "TRACE_QUERY",
        "predicate": "attributes.\"chaos.run_id\" = '"'"'${run_id}'"'"'"
    }' 2>/dev/null | jq '.data.items // [] | length' 2>/dev/null || echo 0)

if [[ "${trace_count}" -ge 1 ]]; then
    ok "APM has ≥ ${trace_count} traces tagged with run_id"
else
    warn "no APM traces with chaos.run_id — was traffic generated during the chaos window?"
fi

# Clear emitted
clear_audit=$(oci log-analytics query \
    --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'octo-chaos-audit' | where run_id = '${run_id}' and action = 'clear' | head limit = 1" 2>&1)

if echo "${clear_audit}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "chaos clear emitted"
else
    warn "no clear action recorded — chaos profile may still be active"
fi

pass_or_fail "09"
