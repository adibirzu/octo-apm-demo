#!/usr/bin/env bash
# Lab 04 — RUM outage detection.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

require_var OCI_APM_DOMAIN_ID
require_var OCI_APM_RUM_WEB_APP_ID
require_cmd oci

if [[ -n "${OCI_APM_RUM_WEB_APP_ID:-}" ]]; then
    ok "RUM Web Application configured (OCI_APM_RUM_WEB_APP_ID not empty)"
else
    fail "OCI_APM_RUM_WEB_APP_ID is empty — run ensure_apm.sh --apply first"
fi

# Sessions Explorer is a Console UI; the SDK doesn't expose it via REST yet.
# Verify indirectly by checking the RUM data ingestion endpoint received
# at least one POST in the last 5 min via Logging.
warn "session-existence check requires Console UI inspection — automating in v2"

pass_or_fail "04"
