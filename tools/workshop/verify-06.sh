#!/usr/bin/env bash
# Lab 06 — WAF event investigation.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
require_var WAF_LOG_GROUP_ID

# Check log group is reachable
if oci logging log-group get --log-group-id "${WAF_LOG_GROUP_ID}" >/dev/null 2>&1; then
    ok "WAF log group reachable"
else
    fail "WAF log group not reachable: ${WAF_LOG_GROUP_ID}"
fi

# Search for a DETECTED event in the last hour
search_out=$(oci logging-search search-logs \
    --search-query "search '${WAF_LOG_GROUP_ID}' | where data.action = 'DETECTED'" \
    --time-start "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
    --time-end "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>&1)

if echo "${search_out}" | jq -e '.data.results // [] | length > 0' >/dev/null 2>&1; then
    ok "at least one DETECTED action in last 1h"
else
    warn "no WAF DETECTED actions in last hour — fire one with the SQLi probe in lab 06 step 1"
fi

pass_or_fail "06"
