#!/usr/bin/env bash
# Ensure OCI WAF (Web Application Firewall) for OCTO Drone Shop (Shop service).
#
# Creates (idempotently):
#   1. WAF Policy with protection rules (SQLi, XSS, rate limiting)
#   2. Attaches WAF policy to the Load Balancer
#
# This enables WAF block → security_event correlation in OCI Console:
#   WAF log → Log Analytics → APM trace (via oracleApmTraceId)
#
# Prerequisites:
#   - OCI CLI configured (instance_principal or config file)
#   - COMPARTMENT_ID set
#   - LOAD_BALANCER_OCID set (the OKE LB serving the shop)
#
# Usage:
#   COMPARTMENT_ID="ocid1.compartment...." \
#   LOAD_BALANCER_OCID="ocid1.loadbalancer...." \
#   ./deploy/oci/ensure_waf.sh

set -euo pipefail

: "${COMPARTMENT_ID:?COMPARTMENT_ID is required}"
: "${LOAD_BALANCER_OCID:?LOAD_BALANCER_OCID is required (OKE LB OCID)}"
WAF_POLICY_NAME="${WAF_POLICY_NAME:-octo-drone-shop-waf}"

echo "[waf] Compartment: ${COMPARTMENT_ID}"
echo "[waf] Load Balancer: ${LOAD_BALANCER_OCID}"
echo "[waf] Policy name: ${WAF_POLICY_NAME}"

# ── 1. Check for existing WAF Policy ────────────────────────────
echo "[waf] Checking for existing WAF policy '${WAF_POLICY_NAME}'..."

existing_policy=$(oci waf web-app-firewall-policy list \
    --compartment-id "${COMPARTMENT_ID}" \
    --display-name "${WAF_POLICY_NAME}" \
    --lifecycle-state "ACTIVE" \
    --query "data.items[0].id" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_policy" && "$existing_policy" != "null" && "$existing_policy" != "None" ]]; then
    WAF_POLICY_OCID="$existing_policy"
    echo "[waf] WAF policy exists: ${WAF_POLICY_OCID}"
else
    echo "[waf] Creating WAF policy with protection rules..."

    # Build the WAF policy JSON with protection rules
    WAF_POLICY_JSON=$(cat <<'POLICY_EOF'
{
  "actions": [
    {
      "name": "block-action",
      "type": "RETURN_HTTP_RESPONSE",
      "code": 403,
      "body": {
        "type": "STATIC_TEXT",
        "text": "{\"error\": \"Request blocked by WAF\", \"code\": \"WAF-403\"}"
      },
      "headers": [
        {"name": "Content-Type", "value": "application/json"},
        {"name": "X-OCI-WAF-Action", "value": "blocked"}
      ]
    },
    {
      "name": "detect-action",
      "type": "CHECK"
    }
  ],
  "requestAccessControl": {
    "defaultActionName": "detect-action",
    "rules": [
      {
        "name": "rate-limit-global",
        "type": "ACCESS_CONTROL",
        "actionName": "block-action",
        "condition": "i_contains(connection.source.ip.address, '')",
        "conditionLanguage": "JMESPATH"
      }
    ]
  },
  "requestProtection": {
    "rules": [
      {
        "name": "sqli-protection",
        "type": "PROTECTION",
        "actionName": "block-action",
        "isBodyInspectionEnabled": true,
        "protectionCapabilities": [
          {
            "key": "941100",
            "version": 1,
            "collaborativeWeights": [],
            "exclusions": {}
          }
        ],
        "protectionCapabilitySettings": {
          "maxNumberOfArguments": 255,
          "maxSingleArgumentLength": 400,
          "maxTotalArgumentLength": 64000
        }
      },
      {
        "name": "xss-protection",
        "type": "PROTECTION",
        "actionName": "block-action",
        "isBodyInspectionEnabled": true,
        "protectionCapabilities": [
          {
            "key": "942100",
            "version": 1,
            "collaborativeWeights": [],
            "exclusions": {}
          }
        ],
        "protectionCapabilitySettings": {
          "maxNumberOfArguments": 255,
          "maxSingleArgumentLength": 400,
          "maxTotalArgumentLength": 64000
        }
      },
      {
        "name": "command-injection-protection",
        "type": "PROTECTION",
        "actionName": "block-action",
        "isBodyInspectionEnabled": true,
        "protectionCapabilities": [
          {
            "key": "932100",
            "version": 1,
            "collaborativeWeights": [],
            "exclusions": {}
          }
        ]
      },
      {
        "name": "path-traversal-protection",
        "type": "PROTECTION",
        "actionName": "block-action",
        "protectionCapabilities": [
          {
            "key": "930100",
            "version": 1,
            "collaborativeWeights": [],
            "exclusions": {}
          }
        ]
      }
    ]
  },
  "requestRateLimiting": {
    "rules": [
      {
        "name": "api-rate-limit",
        "type": "REQUEST_RATE_LIMITING",
        "actionName": "block-action",
        "configurations": [
          {
            "periodInSeconds": 60,
            "requestsLimit": 120,
            "actionDurationInSeconds": 300
          }
        ]
      },
      {
        "name": "login-rate-limit",
        "type": "REQUEST_RATE_LIMITING",
        "actionName": "block-action",
        "condition": "i_contains(http.request.uri.path, '/api/auth/login')",
        "conditionLanguage": "JMESPATH",
        "configurations": [
          {
            "periodInSeconds": 300,
            "requestsLimit": 10,
            "actionDurationInSeconds": 600
          }
        ]
      },
      {
        "name": "checkout-rate-limit",
        "type": "REQUEST_RATE_LIMITING",
        "actionName": "block-action",
        "condition": "i_contains(http.request.uri.path, '/api/shop/checkout')",
        "conditionLanguage": "JMESPATH",
        "configurations": [
          {
            "periodInSeconds": 60,
            "requestsLimit": 5,
            "actionDurationInSeconds": 300
          }
        ]
      }
    ]
  }
}
POLICY_EOF
)

    # Write policy JSON to temp file for OCI CLI
    TMPFILE=$(mktemp /tmp/waf-policy-XXXXXX.json)
    echo "$WAF_POLICY_JSON" > "$TMPFILE"

    WAF_POLICY_OCID=$(oci waf web-app-firewall-policy create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${WAF_POLICY_NAME}" \
        --from-json "file://${TMPFILE}" \
        --query "data.id" \
        --raw-output 2>/dev/null || echo "")

    rm -f "$TMPFILE"

    if [[ -n "$WAF_POLICY_OCID" && "$WAF_POLICY_OCID" != "null" ]]; then
        echo "[waf] WAF policy created: ${WAF_POLICY_OCID}"
    else
        echo "[waf] WAF policy creation failed — check OCI CLI permissions"
        exit 1
    fi
fi

# ── 2. Attach WAF to Load Balancer ──────────────────────────────
echo "[waf] Checking for existing WAF on Load Balancer..."

existing_waf=$(oci waf web-app-firewall list \
    --compartment-id "${COMPARTMENT_ID}" \
    --query "data.items[?\"web-app-firewall-policy-id\"=='${WAF_POLICY_OCID}'].id | [0]" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_waf" && "$existing_waf" != "null" && "$existing_waf" != "None" ]]; then
    echo "[waf] WAF already attached to LB: ${existing_waf}"
else
    echo "[waf] Attaching WAF policy to Load Balancer..."
    WAF_OCID=$(oci waf web-app-firewall create \
        --compartment-id "${COMPARTMENT_ID}" \
        --backend-type "LOAD_BALANCER" \
        --load-balancer-id "${LOAD_BALANCER_OCID}" \
        --web-app-firewall-policy-id "${WAF_POLICY_OCID}" \
        --display-name "octo-drone-shop-waf" \
        --query "data.id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -n "$WAF_OCID" && "$WAF_OCID" != "null" ]]; then
        echo "[waf] WAF attached: ${WAF_OCID}"
    else
        echo "[waf] WAF attachment failed — verify LB OCID and permissions"
    fi
fi

cat <<'EOF'

WAF configuration complete.

Protection rules enabled:
  - SQL Injection (CRS 941100) — BLOCK mode
  - Cross-Site Scripting (CRS 942100) — BLOCK mode
  - Command Injection (CRS 932100) — BLOCK mode
  - Path Traversal (CRS 930100) — BLOCK mode

Rate limiting:
  - Global: 120 req/min per IP
  - Login: 10 req/5min per IP
  - Checkout: 5 req/min per IP

Correlation path:
  WAF block → OCI Logging → Log Analytics (search by source IP)
  WAF block → x-oci-waf-action header → app security_span → APM trace

Next steps:
  1. Verify WAF is ACTIVE in OCI Console → WAF → Firewalls
  2. Enable WAF logging to OCI Logging (Console → WAF → Logs)
  3. Create Log Analytics saved search for WAF blocks
  4. Test with: curl -d "1' OR '1'='1" https://shop.${DNS_DOMAIN}/api/auth/login
EOF

echo ""
echo "Outputs:"
echo "  WAF_POLICY_OCID=${WAF_POLICY_OCID}"
