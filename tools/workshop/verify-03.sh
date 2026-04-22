#!/usr/bin/env bash
# Lab 03 — Slow SQL drill-down.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

trace_id="${1:-${TRACE_ID:-}}"
[[ -z "${trace_id}" ]] && { fail "trace_id required"; pass_or_fail "03"; }

require_cmd oci
require_var OCI_APM_DOMAIN_ID

spans=$(oci apm-traces trace get \
    --apm-domain-id "${OCI_APM_DOMAIN_ID}" \
    --trace-key "${trace_id}" 2>/dev/null | jq '.data.spans // []')

if [[ -z "${spans}" ]] || [[ "${spans}" == "[]" ]]; then
    fail "no spans for trace_id ${trace_id}"
    pass_or_fail "03"
fi

if echo "${spans}" | jq -e 'any(.attributes // {} | to_entries[]; .key=="db.system" and .value=="oracle")' >/dev/null 2>&1; then
    ok "trace contains a span with db.system=oracle"
else
    fail "no oracle DB span found"
fi

if echo "${spans}" | jq -e 'any(."duration-in-ms" // 0 > 500)' >/dev/null 2>&1; then
    ok "slow span duration > 500 ms"
else
    warn "no span > 500ms — re-run with ?slow=true to force"
fi

if echo "${spans}" | jq -e 'any(.attributes // {} | to_entries[]; .key=="db.oracle.sql_id" or .key=="DbOracleSqlId")' >/dev/null 2>&1; then
    ok "slow span has db.oracle.sql_id attribute"
else
    fail "no SQL_ID attribute — check correlation.py session-tag wiring"
fi

pass_or_fail "03"
