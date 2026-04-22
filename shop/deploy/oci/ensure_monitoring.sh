#!/usr/bin/env bash
# Ensure OCI Monitoring resources for OCTO Drone Shop (Shop service).
#
# Creates (idempotently):
#   1. OCI Notification Topic for alarm delivery
#   2. OCI Health Check (HTTP) for the shop's /ready endpoint
#   3. OCI Alarms for key metrics in the octo_drone_shop namespace
#
# Prerequisites:
#   - OCI CLI configured (instance_principal or config file)
#   - COMPARTMENT_ID set
#   - SHOP_PUBLIC_URL set (e.g. https://shop.example.cloud)
#
# Usage:
#   COMPARTMENT_ID="ocid1.compartment...." \
#   SHOP_PUBLIC_URL="https://shop.<your-domain>" \
#   ALARM_EMAIL="ops@<your-domain>" \
#   ./deploy/oci/ensure_monitoring.sh

set -euo pipefail

: "${COMPARTMENT_ID:?COMPARTMENT_ID is required}"
: "${SHOP_PUBLIC_URL:?SHOP_PUBLIC_URL is required (e.g. https://shop.<your-domain>)}"
ALARM_EMAIL="${ALARM_EMAIL:-}"
METRIC_NAMESPACE="${OCI_MONITORING_NAMESPACE:-octo_drone_shop}"
DNS_DOMAIN="${DNS_DOMAIN:-}"

echo "[monitoring] Compartment: ${COMPARTMENT_ID}"
echo "[monitoring] Shop URL: ${SHOP_PUBLIC_URL}"
echo "[monitoring] Metric namespace: ${METRIC_NAMESPACE}"

# ── 1. Notification Topic ────────────────────────────────────────
TOPIC_NAME="octo-drone-shop-alarms"
echo "[monitoring] Ensuring notification topic '${TOPIC_NAME}'..."

existing_topic=$(oci ons topic list \
    --compartment-id "${COMPARTMENT_ID}" \
    --query "data[?name=='${TOPIC_NAME}'].\"topic-id\" | [0]" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_topic" && "$existing_topic" != "null" ]]; then
    TOPIC_OCID="$existing_topic"
    echo "[monitoring] Topic exists: ${TOPIC_OCID}"
else
    TOPIC_OCID=$(oci ons topic create \
        --compartment-id "${COMPARTMENT_ID}" \
        --name "${TOPIC_NAME}" \
        --description "OCTO Drone Shop alarm notifications" \
        --query "data.\"topic-id\"" \
        --raw-output 2>/dev/null || echo "")
    echo "[monitoring] Topic created: ${TOPIC_OCID}"
fi

# Subscribe email if provided
if [[ -n "$ALARM_EMAIL" && -n "$TOPIC_OCID" && "$TOPIC_OCID" != "null" ]]; then
    echo "[monitoring] Subscribing ${ALARM_EMAIL} to topic..."
    oci ons subscription create \
        --compartment-id "${COMPARTMENT_ID}" \
        --topic-id "${TOPIC_OCID}" \
        --protocol "EMAIL" \
        --endpoint "${ALARM_EMAIL}" 2>/dev/null || echo "[monitoring] Subscription may already exist"
fi

# ── 2. OCI Health Check ──────────────────────────────────────────
HC_NAME="octo-drone-shop-ready"
# Extract hostname from SHOP_PUBLIC_URL
SHOP_HOST=$(echo "$SHOP_PUBLIC_URL" | sed 's|https\?://||' | cut -d/ -f1)
echo "[monitoring] Ensuring health check for ${SHOP_HOST}/ready..."

existing_hc=$(oci health-checks http-monitor list \
    --compartment-id "${COMPARTMENT_ID}" \
    --display-name "${HC_NAME}" \
    --query "data[0].id" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_hc" && "$existing_hc" != "null" ]]; then
    echo "[monitoring] Health check exists: ${existing_hc}"
else
    oci health-checks http-monitor create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${HC_NAME}" \
        --targets "[\"${SHOP_HOST}\"]" \
        --protocol HTTPS \
        --port 443 \
        --path "/ready" \
        --method GET \
        --interval-in-seconds 30 \
        --timeout-in-seconds 10 \
        --is-enabled true 2>/dev/null || echo "[monitoring] Health check creation may have failed"
    echo "[monitoring] Health check created for ${SHOP_HOST}"
fi

# ── 3. OCI Alarms ────────────────────────────────────────────────
if [[ -z "$TOPIC_OCID" || "$TOPIC_OCID" == "null" ]]; then
    echo "[monitoring] Skipping alarms — no notification topic available"
    exit 0
fi

create_alarm() {
    local name="$1"
    local query="$2"
    local severity="$3"
    local message="$4"

    existing=$(oci monitoring alarm list \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "$name" \
        --query "data[0].id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -n "$existing" && "$existing" != "null" ]]; then
        echo "[monitoring] Alarm '${name}' exists"
        return
    fi

    oci monitoring alarm create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "$name" \
        --namespace "${METRIC_NAMESPACE}" \
        --query-text "$query" \
        --severity "$severity" \
        --destinations "[\"${TOPIC_OCID}\"]" \
        --is-enabled true \
        --pending-duration "PT5M" \
        --body "$message" \
        --metric-compartment-id "${COMPARTMENT_ID}" 2>/dev/null || echo "[monitoring] Alarm '${name}' creation may have failed"

    echo "[monitoring] Alarm '${name}' created"
}

echo "[monitoring] Creating alarms..."

create_alarm "octo-shop-high-error-rate" \
    "app.errors.rate[1m]{serviceName = \"octo-drone-shop\"}.rate() > 5" \
    "CRITICAL" \
    "Drone Shop error rate exceeds 5/min — check APM traces and Log Analytics"

create_alarm "octo-shop-db-latency" \
    "app.db.latency_ms[1m]{serviceName = \"octo-drone-shop\"}.percentile(0.95) > 2000" \
    "WARNING" \
    "Drone Shop ATP p95 latency > 2s — check DB Management Performance Hub"

create_alarm "octo-shop-health-down" \
    "app.health[1m]{serviceName = \"octo-drone-shop\"}.min() < 1" \
    "CRITICAL" \
    "Drone Shop health check failed — app may be down"

create_alarm "octo-shop-crm-sync-stale" \
    "app.crm.sync_age_s[5m]{serviceName = \"octo-drone-shop\"}.max() > 600" \
    "WARNING" \
    "CRM customer sync hasn't run in >10 minutes — check integration health"

create_alarm "octo-shop-low-stock" \
    "app.inventory.low_stock_products[5m]{serviceName = \"octo-drone-shop\"}.max() > 3" \
    "WARNING" \
    "More than 3 products have stock < 10 — replenishment needed"

echo "[monitoring] Done. Alarms and health checks configured."
echo ""
echo "Outputs:"
echo "  TOPIC_OCID=${TOPIC_OCID}"
echo "  Metric namespace: ${METRIC_NAMESPACE}"
echo "  Health check target: ${SHOP_HOST}/ready"
