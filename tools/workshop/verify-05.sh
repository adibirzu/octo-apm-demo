#!/usr/bin/env bash
# Lab 05 — Custom metric + alarm.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
require_var OCI_COMPARTMENT_ID

# 1. Confirm custom metric arrived
out=$(oci monitoring metric-data summarize-metrics-data \
    --compartment-id "${OCI_COMPARTMENT_ID}" \
    --namespace octo_drone_shop \
    --query-text 'shop.checkout.count[1m].sum()' \
    --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
    --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>&1)

if echo "${out}" | jq -e '.data | length > 0' >/dev/null 2>&1; then
    ok "custom namespace octo_drone_shop has metrics in the last hour"
else
    fail "no shop.checkout.count datapoints — confirm OCI_COMPARTMENT_ID + traffic"
fi

# 2. Alarm exists
alarms=$(oci monitoring alarm list \
    --compartment-id "${OCI_COMPARTMENT_ID}" \
    --display-name "octo-shop-error-rate-lab05" 2>&1)

if echo "${alarms}" | jq -e '.data | length > 0' >/dev/null 2>&1; then
    ok "alarm 'octo-shop-error-rate-lab05' exists"
else
    fail "alarm not found — see lab 05 step 2 to create"
fi

# 3. Body uses annotation contract
if echo "${alarms}" | jq -e '.data[].body // "" | test("annotation\\.run_id")' >/dev/null 2>&1; then
    ok "alarm body references annotation contract (run_id)"
else
    warn "alarm body does not reference {annotation.run_id} — read the correlation contract"
fi

pass_or_fail "05"
