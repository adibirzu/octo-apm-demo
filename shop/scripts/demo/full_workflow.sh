#!/usr/bin/env bash
# ============================================================================
# Octo Demo — end-to-end remediation loop.
#
# Prereqs:
#   - `.env` at the repo root (see deploy/env.template)
#   - a CRM operator session cookie: export CRM_SESSION_COOKIE=...
#   - k6 installed locally
#   - `oci` CLI configured for the target tenancy
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$HERE"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

: "${SHOP_DOMAIN:?SHOP_DOMAIN required}"
: "${CRM_DOMAIN:?CRM_DOMAIN required}"
: "${CRM_SESSION_COOKIE:?CRM_SESSION_COOKIE required (authenticated operator)}"
: "${OCI_LA_NAMESPACE:?OCI_LA_NAMESPACE required}"

SCENARIO="${1:-db-slow-checkout}"
TTL="${2:-300}"

step() { printf '\n\e[1;36m== %s ==\e[0m\n' "$*"; }

step "1. apply chaos scenario=$SCENARIO ttl=${TTL}s on Shop via CRM"
curl -fsSL "https://${CRM_DOMAIN}/api/admin/chaos/apply" \
  -H 'Content-Type: application/json' \
  -H "Cookie: ${CRM_SESSION_COOKIE}" \
  -d "$(cat <<EOF
{"scenario_id":"${SCENARIO}","target":"shop","ttl_seconds":${TTL},"note":"full_workflow.sh"}
EOF
)" | jq '.'

step "2. run k6 checkout load (2m)"
if command -v k6 >/dev/null; then
  k6 run -e SHOP_DOMAIN="${SHOP_DOMAIN}" k6/checkout-load.js
else
  echo "k6 not installed — skipping load phase"
fi

step "3. wait for alarm ingestion (45s)"
sleep 45

step "4. query Log Analytics — chaos-vs-organic"
oci log-analytics query execute \
  --namespace-name "${OCI_LA_NAMESPACE}" \
  --query-string "$(cat deploy/oci/log_analytics/searches/chaos-vs-organic.sql)" \
  --time-filter "{\"timeStart\":\"$(date -u -v-10M +%FT%TZ 2>/dev/null || date -u -d '10 minutes ago' +%FT%TZ)\"}" \
  | jq '.data.results[0:5]'

step "5. clear chaos"
curl -fsSL -X POST "https://${CRM_DOMAIN}/api/admin/chaos/clear" \
  -H "Cookie: ${CRM_SESSION_COOKIE}" | jq '.'

step "6. re-run a short verify load (30s)"
if command -v k6 >/dev/null; then
  k6 run --duration 30s -e SHOP_DOMAIN="${SHOP_DOMAIN}" k6/checkout-load.js
fi

echo
echo "Demo complete. Inspect the Coordinator incident + Workflow Command Center dashboard."
