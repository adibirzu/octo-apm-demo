#!/usr/bin/env bash
# Create OCI APM Availability Monitoring checks for the private demo lab.
#
# Dry-run by default. Set --apply after DNS or DNS override validation.
#
# Usage:
#   APM_DOMAIN_ID=ocid1.apmdomain... ./deploy/oci/ensure_availability_monitors.sh
#   OCI_CLI_PROFILE=<profile> \
#   APM_DOMAIN_ID=ocid1.apmdomain... \
#   OVERRIDE_DNS_IP=203.0.113.10 \
#   ./deploy/oci/ensure_availability_monitors.sh --apply

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

APPLY=false
case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
    --apply)
        APPLY=true
        ;;
    --dry-run|"")
        APPLY=false
        ;;
    *)
        echo "Unknown argument: $1" >&2
        show_usage >&2
        exit 2
        ;;
esac

: "${APM_DOMAIN_ID:?APM_DOMAIN_ID is required}"

SHOP_READY_URL="${SHOP_READY_URL:-https://shop.example.test/ready}"
ADMIN_READY_URL="${ADMIN_READY_URL:-https://admin.example.test/ready}"
MONITOR_PREFIX="${MONITOR_PREFIX:-octo-demo}"
REPEAT_INTERVAL_SECONDS="${REPEAT_INTERVAL_SECONDS:-300}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-60}"
OVERRIDE_DNS_IP="${OVERRIDE_DNS_IP:-}"
VANTAGE_POINTS_CSV="${VANTAGE_POINTS_CSV:-OraclePublic-us-phoenix-1,OraclePublic-us-ashburn-1,OraclePublic-eu-frankfurt-1,OraclePublic-uk-london-1,OraclePublic-ap-tokyo-1,OraclePublic-ap-sydney-1}"

oci_cli() {
    if [[ -n "${OCI_CLI_PROFILE:-}" ]]; then
        oci --profile "${OCI_CLI_PROFILE}" "$@"
    else
        oci "$@"
    fi
}

json_array_from_csv() {
    python3 - "$1" <<'PY'
import json
import sys
print(json.dumps([item.strip() for item in sys.argv[1].split(",") if item.strip()]))
PY
}

vantage_points_json="$(json_array_from_csv "${VANTAGE_POINTS_CSV}")"
dns_config_json="{}"
if [[ -n "${OVERRIDE_DNS_IP}" ]]; then
    dns_config_json="$(python3 - "${OVERRIDE_DNS_IP}" <<'PY'
import json
import sys
print(json.dumps({"isOverrideDns": True, "overrideDnsIp": sys.argv[1]}))
PY
)"
fi

create_monitor() {
    local display_name="$1"
    local target="$2"
    local existing

    existing="$(oci_cli apm-synthetics monitor-collection list-monitors \
        --apm-domain-id "${APM_DOMAIN_ID}" \
        --display-name "${display_name}" \
        --all \
        --query 'data.items[0].id' \
        --raw-output 2>/dev/null || true)"
    if [[ -n "${existing}" && "${existing}" != "null" && "${existing}" != "None" ]]; then
        echo "[availability] Monitor exists: ${display_name} (${existing})"
        return 0
    fi

    if [[ "${APPLY}" != "true" ]]; then
        cat <<EOF
[DRY RUN] Would create REST monitor:
  name:          ${display_name}
  target:        ${target}
  interval:      ${REPEAT_INTERVAL_SECONDS}s
  timeout:       ${TIMEOUT_SECONDS}s
  vantagePoints: ${vantage_points_json}
  dnsOverride:   ${OVERRIDE_DNS_IP:-none}
EOF
        return 0
    fi

    oci_cli apm-synthetics monitor create-rest-monitor \
        --apm-domain-id "${APM_DOMAIN_ID}" \
        --display-name "${display_name}" \
        --monitor-type REST \
        --target "${target}" \
        --vantage-points "${vantage_points_json}" \
        --repeat-interval-in-seconds "${REPEAT_INTERVAL_SECONDS}" \
        --timeout-in-seconds "${TIMEOUT_SECONDS}" \
        --status ENABLED \
        --is-run-now true \
        --is-failure-retried true \
        --is-redirection-enabled true \
        --is-certificate-validation-enabled true \
        --dns-configuration "${dns_config_json}" \
        --request-method GET \
        --verify-response-codes '["2xx"]' \
        --verify-response-content 'ready' \
        --availability-configuration '{"maxAllowedFailuresPerInterval":1,"minAllowedRunsPerInterval":3}' \
        --freeform-tags '{"project":"octo-apm-demo","deployment":"private-demo","lab":"availability-monitoring"}' >/dev/null
    echo "[availability] Monitor created: ${display_name}"
}

echo "[availability] APM domain: ${APM_DOMAIN_ID}"
echo "[availability] Apply:      ${APPLY}"
echo "[availability] Vantage points:"
printf '  - %s\n' ${VANTAGE_POINTS_CSV//,/ }

create_monitor "${MONITOR_PREFIX}-drones-ready-global" "${SHOP_READY_URL}"
create_monitor "${MONITOR_PREFIX}-admin-ready-global" "${ADMIN_READY_URL}"

cat <<EOF

Availability monitor setup complete.

Console:
  OCI Console -> Observability & Management -> Application Performance Monitoring -> Availability Monitoring

Validation:
  oci apm-synthetics monitor-collection list-monitors --apm-domain-id "${APM_DOMAIN_ID}" --all
EOF
