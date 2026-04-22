#!/usr/bin/env bash
# Lab 07 — Build a saved search.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
require_var LA_NAMESPACE

if oci log-analytics saved-search list \
        --namespace-name "${LA_NAMESPACE}" \
        --display-name "OCTO — failed checkouts by reason (last 1h)" \
        2>/dev/null | jq -e '.data.items // [] | length > 0' >/dev/null; then
    ok "saved search 'octo-failed-checkouts-by-reason' exists"
else
    fail "saved search not found — see lab 07 step 3"
fi

# Run it
out=$(oci log-analytics query \
    --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'octo-shop-app-json' and route = '/api/orders' and http_status >= 400 | head limit = 5" 2>&1)

if echo "${out}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "saved search returns rows in the last 1h"
else
    warn "no failed checkouts in last hour — generate some with the curl loop in lab 07 step 2"
fi

pass_or_fail "07"
