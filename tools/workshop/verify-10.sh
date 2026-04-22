#!/usr/bin/env bash
# Lab 10 — End-to-end debug a failed checkout.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
require_var LA_NAMESPACE

# Find at least one POST /api/orders trace with status 500 in last 24h
out=$(oci log-analytics query \
    --namespace-name "${LA_NAMESPACE}" \
    --query-string "'Log Source' = 'octo-shop-app-json' and route = '/api/orders' and http_status = 500 and Time > dateTime('$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ)')" 2>&1)

if echo "${out}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "found at least one POST /api/orders trace with status 500 in the last 24h"
else
    warn "no 500s in the last 24h — re-run lab 09 to inject failures"
fi

# CRM pod restart in window
if command -v kubectl >/dev/null 2>&1; then
    restarts=$(kubectl get pods -n octo-backend-prod \
        -o jsonpath='{range .items[*]}{.metadata.name}{":"}{.status.containerStatuses[0].restartCount}{"\n"}{end}' 2>/dev/null \
        | awk -F: '$2 > 0 {count++} END {print count+0}')
    if [[ "${restarts:-0}" -ge 1 ]]; then
        ok "at least one CRM pod restart observed"
    else
        warn "no CRM pod restarts — synthetic; lab 10 narrative is illustrative"
    fi
else
    warn "kubectl not available — skipping pod-restart check"
fi

pass_or_fail "10"
