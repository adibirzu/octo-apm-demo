#!/usr/bin/env bash
# Lab 02 — Trace ↔ Log correlation.
# Usage: ./tools/workshop/verify-02.sh <trace_id>

source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

trace_id="${1:-${TRACE_ID:-}}"
[[ -z "${trace_id}" ]] && { fail "trace_id required"; pass_or_fail "02"; }

if [[ "${trace_id}" =~ ^[0-9a-f]{32}$ ]]; then
    ok "trace_id valid format"
else
    fail "trace_id must be 32 lowercase hex chars"
fi

require_cmd oci
require_var LA_NAMESPACE

if [[ "${errors}" -eq 0 ]]; then
    query="'Log Source' = 'octo-shop-app-json' | where oracleApmTraceId = '${trace_id}' | head limit = 5"
    out=$(oci log-analytics query \
        --namespace-name "${LA_NAMESPACE}" \
        --query-string "${query}" 2>&1)

    if echo "${out}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
        ok "Log Analytics returned ≥ 1 record for trace_id"
    else
        fail "no LA record for trace_id ${trace_id} — check Service Connector + ingestion lag (~60s)"
    fi

    if echo "${out}" | jq -e '[.data.results[] | .oracleApmTraceId] | all(. == "'"${trace_id}"'")' >/dev/null 2>&1; then
        ok "records include oracleApmTraceId field"
    else
        warn "couldn't confirm every row carries oracleApmTraceId"
    fi
fi

pass_or_fail "02"
