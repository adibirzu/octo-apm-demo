#!/usr/bin/env bash
# Lab 08 — Stack Monitoring + ATP health.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_cmd oci
require_var OCI_COMPARTMENT_ID

resources=$(oci stack-monitoring monitored-resource list \
    --compartment-id "${OCI_COMPARTMENT_ID}" \
    --name octo-atp 2>&1)

if echo "${resources}" | jq -e '.data.items // [] | length > 0' >/dev/null 2>&1; then
    ok "ATP MonitoredResource 'octo-atp' exists in Stack Monitoring"
else
    fail "octo-atp not registered — run DRY_RUN=false ./deploy/oci/ensure_stack_monitoring.sh"
fi

# Health
resource_id=$(echo "${resources}" | jq -r '.data.items[0].id // ""')
if [[ -n "${resource_id}" ]]; then
    if oci stack-monitoring monitored-resource get \
            --monitored-resource-id "${resource_id}" >/dev/null 2>&1; then
        ok "Stack Monitoring health is reachable"
    else
        fail "could not read monitored-resource health"
    fi
fi

pass_or_fail "08"
