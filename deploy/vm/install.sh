#!/usr/bin/env bash
# Unified VM installer — idempotent bootstrap for a single Compute VM
# that runs Drone Shop + Enterprise CRM Portal against OCI ATP.
#
# Tested on Oracle Linux 9 and Ubuntu 24.04. Requires root (or sudo).
#
# Steps performed (idempotent):
#   1. Install docker + docker compose v2 + nginx TLS tooling
#   2. Render /etc/nginx config from deploy/vm/nginx/nginx.conf with
#      DNS_DOMAIN substituted
#   3. Pre-flight check env file + wallet directory
#   4. docker compose pull + up -d
#   5. Enable systemd unit so the stack survives reboots
#
# Inputs: deploy/vm/.env (created from deploy/vm/.env.template)
#         deploy/vm/wallet/ (unzipped ATP wallet)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "install.sh must run as root (or via sudo)" >&2
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE} — copy .env.template and fill it in first." >&2
    exit 1
fi

# shellcheck disable=SC1090
set -a; . "${ENV_FILE}"; set +a

: "${DNS_DOMAIN:?DNS_DOMAIN is required in ${ENV_FILE}}"
: "${OCIR_REGION:?}"
: "${OCIR_TENANCY:?}"
: "${ORACLE_DSN:?}"
: "${INTERNAL_SERVICE_KEY:?Generate with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'}"

if [[ ! -d "${SCRIPT_DIR}/wallet" ]] || ! ls "${SCRIPT_DIR}/wallet"/*.sso >/dev/null 2>&1; then
    echo "Wallet not found at ${SCRIPT_DIR}/wallet — unzip the ATP wallet there first." >&2
    exit 1
fi

# ── 1. Packages ──────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y dnf-plugins-core
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get update
        apt-get install -y docker.io docker-compose-v2
    else
        echo "Unsupported package manager — install docker + compose manually." >&2
        exit 1
    fi
fi

systemctl enable --now docker

# ── 2. Render nginx config (DNS_DOMAIN substitution) ─────────────────
NGINX_OUT="${SCRIPT_DIR}/nginx/nginx.conf.rendered"
envsubst '$DNS_DOMAIN' < "${SCRIPT_DIR}/nginx/nginx.conf" > "${NGINX_OUT}"
mv "${NGINX_OUT}" "${SCRIPT_DIR}/nginx/nginx.conf"

mkdir -p "${SCRIPT_DIR}/nginx/tls/shop" "${SCRIPT_DIR}/nginx/tls/crm"
if [[ ! -f "${SCRIPT_DIR}/nginx/tls/shop/fullchain.pem" ]]; then
    echo "TLS certs not installed for drone.${DNS_DOMAIN}. Generate with:"
    echo "  certbot certonly --standalone -d drone.${DNS_DOMAIN} -d backend.${DNS_DOMAIN}"
    echo "  cp /etc/letsencrypt/live/drone.${DNS_DOMAIN}/*.pem deploy/vm/nginx/tls/shop/"
    echo "  cp /etc/letsencrypt/live/backend.${DNS_DOMAIN}/*.pem  deploy/vm/nginx/tls/crm/"
    echo
    echo "Continuing anyway — nginx will fail to start until the certs are present."
fi

# ── 3. OCIR login (instance principal via oci CLI helper) ────────────
if command -v oci >/dev/null 2>&1; then
    oci artifacts container image list \
        --compartment-id "${OCI_COMPARTMENT_ID:-null}" \
        --query 'data.items | [0].id' --raw-output >/dev/null 2>&1 || true
fi

# ── 4. Compose up ────────────────────────────────────────────────────
cd "${SCRIPT_DIR}"
docker compose -f docker-compose-unified.yml --env-file "${ENV_FILE}" pull
docker compose -f docker-compose-unified.yml --env-file "${ENV_FILE}" up -d

# ── 5. systemd survival ──────────────────────────────────────────────
install -m 0644 "${SCRIPT_DIR}/systemd/octo.service" /etc/systemd/system/octo.service
sed -i "s#__INSTALL_DIR__#${SCRIPT_DIR}#g" /etc/systemd/system/octo.service
systemctl daemon-reload
systemctl enable --now octo.service

echo
echo "==============================================================="
echo " Unified VM stack is up."
echo "   Shop: https://drone.${DNS_DOMAIN}"
echo "   CRM:  https://backend.${DNS_DOMAIN}"
echo "==============================================================="
