#!/usr/bin/env bash
# Post-deploy validation for the OCTO APM Demo platform.
#
# Probes every observable surface to confirm the deployment is functional
# end-to-end: storefront reachable, /ready returns true for every
# observability subsystem, APM/RUM/Logging configured, ATP connected,
# Java sidecar healthy, workflow gateway responding.
#
# Usage:
#   ./deploy/validate-deployment.sh                # full check
#   ./deploy/validate-deployment.sh --info-only    # print current config, skip probes
#   ./deploy/validate-deployment.sh --verbose      # show every HTTP response body
#
# Required env (read from the calling shell or .env):
#   DNS_DOMAIN          public DNS zone (e.g. demo.acme.io)
#
# Optional env:
#   SHOP_HOST           override shop hostname (default: drones.${DNS_DOMAIN})
#   ADMIN_HOST          override admin hostname (default: admin.${DNS_DOMAIN})
#   VERBOSE             set to 1 to dump full /ready responses
#
# Exit codes:
#   0   all probes passed
#   1   at least one probe failed
#   2   missing required env / unreachable

set -uo pipefail

INFO_ONLY=0
VERBOSE="${VERBOSE:-0}"
for arg in "$@"; do
    case "$arg" in
        --info-only) INFO_ONLY=1 ;;
        --verbose)   VERBOSE=1 ;;
        -h|--help)
            sed -n '2,25p' "$0"
            exit 0
            ;;
    esac
done

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
bold()   { printf '\033[1m%s\033[0m\n' "$*"; }

bold "=== OCTO APM Demo — deployment validation ==="
echo

if [[ -z "${DNS_DOMAIN:-}" ]]; then
    red "DNS_DOMAIN is not set. export DNS_DOMAIN=<your-dns-zone> first."
    exit 2
fi

SHOP_HOST="${SHOP_HOST:-drones.${DNS_DOMAIN}}"
ADMIN_HOST="${ADMIN_HOST:-admin.${DNS_DOMAIN}}"

echo "Target hosts:"
echo "  Shop:  https://${SHOP_HOST}"
echo "  Admin: https://${ADMIN_HOST}"
echo

if [[ "$INFO_ONLY" == "1" ]]; then
    echo "(--info-only: skipping probes)"
    exit 0
fi

PASS=0
FAIL=0

check() {
    local label="$1"
    local url="$2"
    local expected_substr="${3:-}"

    local response
    response=$(curl -sS --max-time 10 "$url" 2>&1) || {
        red "✗ ${label}: unreachable"
        FAIL=$((FAIL + 1))
        return
    }

    if [[ -n "$expected_substr" && "$response" != *"$expected_substr"* ]]; then
        red "✗ ${label}: response missing '${expected_substr}'"
        [[ "$VERBOSE" == "1" ]] && echo "$response" | head -5
        FAIL=$((FAIL + 1))
        return
    fi

    green "✓ ${label}"
    [[ "$VERBOSE" == "1" ]] && echo "$response" | jq . 2>/dev/null | head -20 || true
    PASS=$((PASS + 1))
}

check_json_field() {
    local label="$1"
    local url="$2"
    local jq_filter="$3"
    local expected="$4"

    local actual
    actual=$(curl -sS --max-time 10 "$url" 2>&1 | jq -r "$jq_filter" 2>/dev/null) || {
        red "✗ ${label}: unreachable or invalid JSON"
        FAIL=$((FAIL + 1))
        return
    }

    if [[ "$actual" == "$expected" ]]; then
        green "✓ ${label} (${jq_filter} = ${actual})"
        PASS=$((PASS + 1))
    else
        red "✗ ${label}: ${jq_filter} = '${actual}', expected '${expected}'"
        FAIL=$((FAIL + 1))
    fi
}

bold "--- Storefront reachability ---"
check "Shop HTML"      "https://${SHOP_HOST}/"        "<!doctype html"
check "Shop /shop"     "https://${SHOP_HOST}/shop"    "<html"
check "Shop /login"    "https://${SHOP_HOST}/login"
echo

bold "--- Storefront observability subsystems (/ready) ---"
URL="https://${SHOP_HOST}/ready"
check_json_field "Database reachable"    "$URL" '.ready'                            "true"
check_json_field "ATP connection"        "$URL" '.db_type'                          "oracle_atp"
check_json_field "APM configured"        "$URL" '.apm_configured'                   "true"
check_json_field "RUM configured"        "$URL" '.rum_configured'                   "true"
check_json_field "Logging configured"    "$URL" '.logging_configured'               "true"
check_json_field "Java sidecar enabled"  "$URL" '.java_apm_enabled'                 "true"
check_json_field "Workflow gateway"      "$URL" '.workflow_gateway_configured'      "true"
check_json_field "Select AI"             "$URL" '.selectai_configured'              "true"
check_json_field "GenAI"                 "$URL" '.genai_configured'                 "true"
echo

bold "--- Admin / CRM reachability ---"
check "Admin HTML"     "https://${ADMIN_HOST}/"
check "Admin /ready"   "https://${ADMIN_HOST}/ready"  '"ready"'
echo

bold "--- Java payment sidecar (via shop) ---"
# Java APM sidecar isn't usually exposed publicly; check via shop's
# health proxy if one exists.
check "Shop /app-server/health" "https://${SHOP_HOST}/app-server/health" || true
echo

bold "--- Summary ---"
TOTAL=$((PASS + FAIL))
if [[ "$FAIL" == "0" ]]; then
    green "All ${TOTAL} checks passed. Deployment is healthy."
    exit 0
else
    red "${FAIL} of ${TOTAL} checks failed."
    echo
    yellow "Common fixes:"
    echo "  - APM/RUM/Logging 'false'  → check OCI_APM_* and OCI_LOG_* env vars in your deployment (see docs/CONFIGURATION.md)"
    echo "  - Database 'disconnected'  → check ATP wallet mount + ORACLE_DSN/ORACLE_USER/ORACLE_PASSWORD env"
    echo "  - Workflow gateway 'false' → check WORKFLOW_API_BASE_URL + workflow-gateway pod/container is running"
    echo "  - DNS not resolving        → confirm A records for drones.${DNS_DOMAIN} and admin.${DNS_DOMAIN} point at your LB IP"
    exit 1
fi
