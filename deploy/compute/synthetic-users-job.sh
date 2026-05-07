#!/usr/bin/env bash
# Scheduled synthetic user/order generator for private demo Compute hosts.

set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/octo/runtime.env}"

usage() {
    cat <<'EOF'
Usage: synthetic-users-job.sh [--help]

Run the scheduled synthetic user/order generator on a private demo Compute host.
Configuration is loaded from ENV_FILE, which defaults to /opt/octo/runtime.env.
EOF
}

log() {
    printf '[octo-synthetic-users] %s\n' "$*" >&2
}

case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
esac

if [[ ! -f "${ENV_FILE}" ]]; then
    log "missing ${ENV_FILE}; skipping"
    exit 0
fi

# shellcheck disable=SC1090
set -a; . "${ENV_FILE}"; set +a

case "${SYNTHETIC_USERS_ENABLED:-false}" in
    true|1|yes|on)
        ;;
    *)
        log "disabled"
        exit 0
        ;;
esac

if [[ -z "${INTERNAL_SERVICE_KEY:-}" ]]; then
    log "INTERNAL_SERVICE_KEY is not set; skipping"
    exit 0
fi

case "${OCTO_COMPUTE_ROLE:-}" in
    shop)
        target_base="http://127.0.0.1:${APP_PORT:-${PORT:-8080}}"
        ;;
    crm)
        target_base="${SERVICE_SHOP_URL:-}"
        if [[ -z "${target_base}" ]]; then
            log "SERVICE_SHOP_URL is not configured on CRM host; skipping"
            exit 0
        fi
        ;;
    *)
        log "OCTO_COMPUTE_ROLE must be shop or crm; skipping"
        exit 0
        ;;
esac

payload="$(
python3 - <<'PY'
import json
import os

def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default

print(json.dumps({
    "domain": os.environ.get("SYNTHETIC_USER_EMAIL_DOMAIN", "apex.example.test"),
    "count": env_int("SYNTHETIC_USER_COUNT", 12),
    "order_count": env_int("SYNTHETIC_USER_ORDER_COUNT", 6),
    "delete_after_days": env_int("SYNTHETIC_USER_DELETE_AFTER_DAYS", 7),
}))
PY
)"

target="${target_base%/}/api/synthetic/users/run"
log "posting synthetic activity to ${target}"

curl -fsS --max-time "${SYNTHETIC_USER_JOB_TIMEOUT_SECONDS:-30}" \
    -H "Content-Type: application/json" \
    -H "X-Internal-Service-Key: ${INTERNAL_SERVICE_KEY}" \
    -H "X-Operator: vm-scheduler" \
    -d "${payload}" \
    "${target}" >/tmp/octo-synthetic-users.last.json

log "completed"
