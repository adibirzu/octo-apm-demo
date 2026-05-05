#!/usr/bin/env bash
# Install or reconcile one OCTO Compute application instance.
#
# Runs on either the shop or CRM Compute VM after Terraform creates the host.
# It does not provision OCI resources. It validates the runtime env, wallet,
# selected container runtime, and Oracle Cloud Agent presence before starting
# the app on the private host port consumed by the OCI Load Balancer.
#
# Usage:
#   sudo ./deploy/compute/install.sh --check
#   sudo ./deploy/compute/install.sh
#   sudo ENV_FILE=/opt/octo/runtime.env ./deploy/compute/install.sh

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

MODE="apply"
case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
    --check)
        MODE="check"
        ;;
    "")
        ;;
    *)
        echo "Unknown argument: $1" >&2
        show_usage >&2
        exit 2
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-/opt/octo/runtime.env}"
CONTAINER_ENV_FILE="${CONTAINER_ENV_FILE:-/opt/octo/container.env}"
COMPOSE_FILE="${COMPOSE_FILE:-${SCRIPT_DIR}/app-compose.yml}"
NGINX_TEMPLATE="${SCRIPT_DIR}/nginx/app.conf.template"
NGINX_OUT="/etc/nginx/nginx.conf"
WALLET_DIR="${WALLET_DIR:-/opt/octo/wallet}"
TLS_DIR="${TLS_DIR:-/etc/nginx/tls}"

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

if [[ "${EUID}" -ne 0 ]]; then
    red "install.sh must run as root (or via sudo)"
    exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    red "Missing ${ENV_FILE}. Copy runtime.env.template and fill it first."
    exit 1
fi

# shellcheck disable=SC1090
set -a; . "${ENV_FILE}"; set +a

required_vars=(
    OCTO_COMPUTE_ROLE APP_IMAGE APP_NAME OTEL_SERVICE_NAME SERVICE_INSTANCE_ID
    DNS_DOMAIN OCI_COMPARTMENT_ID INTERNAL_SERVICE_KEY ORACLE_DSN ORACLE_PASSWORD
    ORACLE_WALLET_PASSWORD OCI_APM_ENDPOINT OCI_APM_PRIVATE_DATAKEY OCI_LOG_GROUP_ID
    OCI_LOG_ID
)

case "${OCTO_COMPUTE_ROLE:-}" in
    shop)
        required_vars+=(AUTH_TOKEN_SECRET SERVICE_CRM_URL CRM_PUBLIC_URL)
        OCTO_PUBLIC_HOSTNAME="shop.${DNS_DOMAIN}"
        ;;
    crm)
        required_vars+=(APP_SECRET_KEY BOOTSTRAP_ADMIN_PASSWORD CRM_BASE_URL SERVICE_SHOP_URL)
        OCTO_PUBLIC_HOSTNAME="crm.${DNS_DOMAIN}"
        ;;
    *)
        red "OCTO_COMPUTE_ROLE must be 'shop' or 'crm'"
        exit 1
        ;;
esac

CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-podman}"
ENABLE_HOST_NGINX="${ENABLE_HOST_NGINX:-false}"
APP_IMAGE_BUILD_ENABLED="${APP_IMAGE_BUILD_ENABLED:-false}"
APP_IMAGE_PULL_POLICY="${APP_IMAGE_PULL_POLICY:-if-not-present}"
APP_CONTAINER_UID="${APP_CONTAINER_UID:-1000}"
APP_CONTAINER_GID="${APP_CONTAINER_GID:-1000}"

container_env_vars=(
    APP_IMAGE APP_NAME APP_RUNTIME ENVIRONMENT PORT APP_PORT DNS_DOMAIN
    SERVICE_NAMESPACE SERVICE_INSTANCE_ID DEMO_STACK_NAME OTEL_SERVICE_NAME
    OTEL_TRACES_SAMPLER OTEL_PYTHON_LOG_CORRELATION SERVICE_CRM_URL
    CRM_PUBLIC_URL CRM_BASE_URL SERVICE_SHOP_URL INTERNAL_SERVICE_KEY
    AUTH_TOKEN_SECRET AUTH_TOKEN_SECRET_FILE APP_SECRET_KEY APP_SECRET_KEY_FILE
    BOOTSTRAP_ADMIN_PASSWORD BOOTSTRAP_ADMIN_PASSWORD_FILE ORACLE_DSN
    ORACLE_USER ORACLE_PASSWORD ORACLE_PASSWORD_FILE ORACLE_WALLET_PASSWORD
    ORACLE_WALLET_PASSWORD_FILE ORACLE_WALLET_DIR ATP_OCID
    DATABASE_OBSERVABILITY_ENABLED OCI_AUTH_MODE OCI_COMPARTMENT_ID
    OCI_APM_ENDPOINT OCI_APM_PRIVATE_DATAKEY OCI_APM_PRIVATE_DATAKEY_FILE
    OCI_APM_PUBLIC_DATAKEY OCI_APM_RUM_ENDPOINT OCI_APM_WEB_APPLICATION
    OCI_APM_RUM_PUBLIC_DATAKEY OTLP_LOG_EXPORT_ENABLED OCI_LOG_ID
    OCI_LOG_GROUP_ID OCI_LOG_CHAOS_AUDIT_ID OCI_LOG_SECURITY_ID
    IDCS_DOMAIN_URL IDCS_CLIENT_ID IDCS_CLIENT_SECRET IDCS_CLIENT_SECRET_FILE
)

render_container_env_file() {
    local tmp_env
    tmp_env="$(mktemp "${CONTAINER_ENV_FILE}.XXXXXX")"
    chmod 0600 "${tmp_env}"

    local name value
    for name in "${container_env_vars[@]}"; do
        value="${!name:-}"
        if [[ "${value}" == *$'\n'* || "${value}" == *$'\r'* ]]; then
            rm -f "${tmp_env}"
            red "${name} contains a newline; container env files cannot represent multi-line values"
            exit 1
        fi
        printf '%s=%s\n' "${name}" "${value}" >>"${tmp_env}"
    done

    mv "${tmp_env}" "${CONTAINER_ENV_FILE}"
    chmod 0600 "${CONTAINER_ENV_FILE}"
}

missing=()
for name in "${required_vars[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        missing+=("${name}")
    fi
done
if [[ "${#missing[@]}" -gt 0 ]]; then
    red "Missing required runtime env value(s): ${missing[*]}"
    exit 1
fi

install -d -m 0755 "$(dirname "${CONTAINER_ENV_FILE}")"
install -d -m 0700 /opt/octo/secrets
render_container_env_file

if [[ ! -d "${WALLET_DIR}" ]] || ! ls "${WALLET_DIR}"/*.sso >/dev/null 2>&1; then
    red "ATP wallet not found in ${WALLET_DIR}; expected cwallet.sso/ewallet.p12/tnsnames.ora"
    exit 1
fi
chown -R "${APP_CONTAINER_UID}:${APP_CONTAINER_GID}" "${WALLET_DIR}"
find "${WALLET_DIR}" -type d -exec chmod 0750 {} \;
find "${WALLET_DIR}" -type f -exec chmod 0640 {} \;

if [[ "${ENABLE_HOST_NGINX}" == "true" ]]; then
    if [[ ! -f "${TLS_DIR}/fullchain.pem" || ! -f "${TLS_DIR}/privkey.pem" ]]; then
        red "TLS material missing in ${TLS_DIR}; install fullchain.pem and privkey.pem first"
        exit 1
    fi
fi

if ! systemctl list-unit-files oracle-cloud-agent.service >/dev/null 2>&1; then
    yellow "oracle-cloud-agent.service was not found; OCI OS/custom log ingestion will not start until the agent is installed"
fi

install_podman() {
    if command -v podman >/dev/null 2>&1; then
        return 0
    fi
    if [[ "${MODE}" == "check" ]]; then
        red "podman is not installed"
        exit 1
    fi
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y podman
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get update
        apt-get install -y podman
    else
        red "Unsupported package manager; install podman manually"
        exit 1
    fi
}

install_docker() {
    if command -v docker >/dev/null 2>&1; then
        return 0
    fi
    if [[ "${MODE}" == "check" ]]; then
        red "docker is not installed"
        exit 1
    fi
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y dnf-plugins-core
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get update
        apt-get install -y docker.io docker-compose-v2
    else
        red "Unsupported package manager; install docker compose v2 manually"
        exit 1
    fi
}

case "${CONTAINER_RUNTIME}" in
    podman)
        install_podman
        if ! podman --version >/dev/null 2>&1; then
            red "podman is not usable"
            exit 1
        fi
        ;;
    docker)
        install_docker
        if ! docker compose version >/dev/null 2>&1; then
            red "docker compose v2 is required"
            exit 1
        fi
        if ! docker compose -f "${COMPOSE_FILE}" --env-file "${CONTAINER_ENV_FILE}" config >/dev/null; then
            red "Docker Compose config failed"
            exit 1
        fi
        ;;
    *)
        red "CONTAINER_RUNTIME must be 'podman' or 'docker'"
        exit 1
        ;;
esac

case "${APP_IMAGE_PULL_POLICY}" in
    always|if-not-present|never)
        ;;
    *)
        red "APP_IMAGE_PULL_POLICY must be 'always', 'if-not-present', or 'never'"
        exit 1
        ;;
esac

build_app_image() {
    case "${APP_IMAGE_BUILD_ENABLED}" in
        true|1|yes)
            ;;
        false|0|no|"")
            return 0
            ;;
        *)
            red "APP_IMAGE_BUILD_ENABLED must be true or false"
            exit 1
            ;;
    esac

    local context="${APP_IMAGE_BUILD_CONTEXT:-/opt/octo/repo}"
    local dockerfile="${APP_IMAGE_DOCKERFILE:-}"
    if [[ -z "${dockerfile}" ]]; then
        case "${OCTO_COMPUTE_ROLE}" in
            shop) dockerfile="shop/Dockerfile" ;;
            crm) dockerfile="crm/Dockerfile" ;;
        esac
    fi

    if [[ ! -d "${context}" ]]; then
        red "APP_IMAGE_BUILD_CONTEXT does not exist: ${context}"
        exit 1
    fi
    if [[ ! -f "${context}/${dockerfile}" ]]; then
        red "APP_IMAGE_DOCKERFILE does not exist: ${context}/${dockerfile}"
        exit 1
    fi

    if [[ "${MODE}" == "check" ]]; then
        return 0
    fi

    case "${CONTAINER_RUNTIME}" in
        podman)
            podman build -f "${context}/${dockerfile}" -t "${APP_IMAGE}" "${context}"
            ;;
        docker)
            docker build -f "${context}/${dockerfile}" -t "${APP_IMAGE}" "${context}"
            ;;
    esac
}

build_app_image

registry_host="${APP_IMAGE%%/*}"
if [[ "${registry_host}" == "${APP_IMAGE}" ]]; then
    registry_host=""
fi
if [[ -n "${OCIR_REGISTRY:-}" ]]; then
    registry_host="${OCIR_REGISTRY}"
fi
if [[ -n "${registry_host}" && -n "${OCIR_USERNAME:-}" && -n "${OCIR_AUTH_TOKEN:-}" ]]; then
    case "${CONTAINER_RUNTIME}" in
        podman)
            printf '%s' "${OCIR_AUTH_TOKEN}" | podman login "${registry_host}" --username "${OCIR_USERNAME}" --password-stdin
            ;;
        docker)
            printf '%s' "${OCIR_AUTH_TOKEN}" | docker login "${registry_host}" --username "${OCIR_USERNAME}" --password-stdin
            ;;
    esac
fi

if [[ "${ENABLE_HOST_NGINX}" == "true" ]]; then
    if ! command -v nginx >/dev/null 2>&1; then
        if [[ "${MODE}" == "check" ]]; then
            red "nginx is not installed"
            exit 1
        fi
        if command -v dnf >/dev/null 2>&1; then
            dnf install -y nginx
        elif command -v apt-get >/dev/null 2>&1; then
            apt-get update && apt-get install -y nginx
        fi
    fi
    export OCTO_PUBLIC_HOSTNAME
    envsubst '${OCTO_PUBLIC_HOSTNAME}' < "${NGINX_TEMPLATE}" > /tmp/octo-nginx.conf
    if ! nginx -t -c /tmp/octo-nginx.conf >/dev/null; then
        red "Rendered nginx config failed validation"
        exit 1
    fi
fi

if [[ "${MODE}" == "check" ]]; then
    green "OCTO Compute ${OCTO_COMPUTE_ROLE} pre-flight passed (${CONTAINER_RUNTIME})"
    exit 0
fi

if [[ "${ENABLE_HOST_NGINX}" == "true" ]]; then
    install -d -m 0755 /etc/nginx/tls
    install -m 0644 /tmp/octo-nginx.conf "${NGINX_OUT}"
    systemctl enable --now nginx
    systemctl reload nginx
fi

if systemctl is-active --quiet firewalld 2>/dev/null; then
    firewall-cmd --permanent --add-port=8080/tcp
    firewall-cmd --reload
fi

case "${CONTAINER_RUNTIME}" in
    podman)
        systemctl enable --now podman-restart || true
        install -m 0644 "${SCRIPT_DIR}/systemd/octo-podman.service" /etc/systemd/system/octo-compute.service
        ;;
    docker)
        systemctl enable --now docker
        install -m 0644 "${SCRIPT_DIR}/systemd/octo-compute.service" /etc/systemd/system/octo-compute.service
        ;;
esac

systemctl daemon-reload
systemctl enable --now octo-compute.service

green "OCTO Compute ${OCTO_COMPUTE_ROLE} is configured on private port 8080 for the OCI Load Balancer"
