#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Enterprise CRM Portal — Standalone OKE Deployment
#
# Deploys the CRM portal to any OCI tenancy with Oracle ATP.
#
# Prerequisites:
#   - kubectl configured for your OKE cluster
#   - Oracle ATP provisioned with a wallet downloaded
#     (use deploy/oci/ensure_atp.sh to create one if needed)
#   - OCIR login configured (docker login <region>.ocir.io)
#   - Docker available for building (or use a pre-built image)
#
# Optional post-deploy:
#   deploy/oci/ensure_db_observability.sh — enables DB Management + OPSI
#
# Required env vars:
#   DNS_DOMAIN          — your DNS domain (e.g., <your-domain>)
#   ORACLE_DSN          — ATP TNS name (e.g., myatp_low)
#   ORACLE_PASSWORD     — ATP admin password
#   ORACLE_WALLET_DIR   — local path to unzipped wallet
#   ORACLE_WALLET_PASSWORD — wallet password
#   OCIR_REGION         — OCI region (e.g., <region-key>)
#   OCIR_TENANCY        — OCIR tenancy namespace
#
# Optional env vars:
#   IDCS_DOMAIN_URL, IDCS_CLIENT_ID, IDCS_CLIENT_SECRET — enables SSO
#   OCI_APM_ENDPOINT, OCI_APM_PRIVATE_DATAKEY — enables OTel/APM
#   OCTO_DRONE_SHOP_URL — enables order sync integration
#   INTERNAL_SERVICE_KEY — enables simulation proxy (must match the shop)
#   NAMESPACE           — k8s namespace (default: enterprise-crm)
#   IMAGE_TAG           — image tag (default: timestamp)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

_require() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        echo "ERROR: $name is required but not set." >&2
        exit 1
    fi
}

_resolve_secret() {
    local name="$1"
    local file_var="${name}_FILE"
    local current="${!name:-}"
    if [[ -n "$current" ]]; then
        return
    fi
    local file_path="${!file_var:-}"
    if [[ -n "$file_path" ]]; then
        export "$name"="$(python3 - "$file_path" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).read_text(encoding="utf-8").strip())
PY
)"
    fi
}

_generate_secret() {
    openssl rand -hex 32 2>/dev/null || python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
}

_resolve_secret ORACLE_PASSWORD
_resolve_secret ORACLE_WALLET_PASSWORD
_resolve_secret APP_SECRET_KEY
_resolve_secret INTERNAL_SERVICE_KEY
_resolve_secret IDCS_CLIENT_SECRET
_resolve_secret SPLUNK_HEC_TOKEN
_resolve_secret OCI_APM_PRIVATE_DATAKEY
_resolve_secret OCI_APM_PUBLIC_DATAKEY
_resolve_secret OCI_APM_RUM_PUBLIC_DATAKEY

# ── Validate required inputs ──────────────────────────────────────
_require DNS_DOMAIN
_require ORACLE_DSN
_require ORACLE_PASSWORD
_require ORACLE_WALLET_DIR
_require ORACLE_WALLET_PASSWORD
_require OCIR_REGION
_require OCIR_TENANCY

NAMESPACE="${NAMESPACE:-enterprise-crm}"
ORACLE_USER="${ORACLE_USER:-ADMIN}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d%H%M%S)}"
IMAGE="${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal"
CRM_URL="https://crm.${DNS_DOMAIN}"
APP_SECRET_KEY="${APP_SECRET_KEY:-$(_generate_secret)}"

if [[ -n "${OCTO_DRONE_SHOP_URL:-}" && -z "${INTERNAL_SERVICE_KEY:-}" ]]; then
    echo "ERROR: INTERNAL_SERVICE_KEY (or INTERNAL_SERVICE_KEY_FILE) is required when OCTO_DRONE_SHOP_URL is set." >&2
    exit 1
fi

# Auto-derive IDCS redirect URI
IDCS_REDIRECT_URI="${IDCS_REDIRECT_URI:-${CRM_URL}/api/auth/sso/callback}"

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Enterprise CRM Portal — Standalone Deploy                      ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  Domain:    ${DNS_DOMAIN}"
echo "║  CRM URL:   ${CRM_URL}"
echo "║  Image:     ${IMAGE}:${IMAGE_TAG}"
echo "║  Namespace: ${NAMESPACE}"
echo "║  ATP DSN:   ${ORACLE_DSN}"
echo "║  SSO:       ${IDCS_DOMAIN_URL:+enabled}${IDCS_DOMAIN_URL:-disabled (local auth only)}"
echo "║  APM:       ${OCI_APM_ENDPOINT:+enabled}${OCI_APM_ENDPOINT:-disabled}"
echo "║  Shop URL:  ${OCTO_DRONE_SHOP_URL:-not configured}"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ── Create namespace ──────────────────────────────────────────────
kubectl create namespace "$NAMESPACE" 2>/dev/null || true

# ── Create wallet secret ──────────────────────────────────────────
echo "[standalone] Creating wallet secret..."
kubectl create secret generic crm-wallet \
    --from-file="${ORACLE_WALLET_DIR}" \
    --namespace="$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

# ── Create secrets ────────────────────────────────────────────────
echo "[standalone] Creating secrets..."
kubectl create secret generic crm-secrets \
    --namespace="$NAMESPACE" \
    --from-literal="ORACLE_PASSWORD=${ORACLE_PASSWORD}" \
    --from-literal="ORACLE_WALLET_PASSWORD=${ORACLE_WALLET_PASSWORD}" \
    --from-literal="APP_SECRET_KEY=${APP_SECRET_KEY}" \
    ${INTERNAL_SERVICE_KEY:+--from-literal="INTERNAL_SERVICE_KEY=${INTERNAL_SERVICE_KEY}"} \
    ${IDCS_CLIENT_SECRET:+--from-literal="IDCS_CLIENT_SECRET=${IDCS_CLIENT_SECRET}"} \
    ${SPLUNK_HEC_TOKEN:+--from-literal="SPLUNK_HEC_TOKEN=${SPLUNK_HEC_TOKEN}"} \
    ${OCI_APM_PRIVATE_DATAKEY:+--from-literal="OCI_APM_PRIVATE_DATAKEY=${OCI_APM_PRIVATE_DATAKEY}"} \
    ${OCI_APM_PUBLIC_DATAKEY:+--from-literal="OCI_APM_PUBLIC_DATAKEY=${OCI_APM_PUBLIC_DATAKEY}"} \
    ${OCI_APM_RUM_PUBLIC_DATAKEY:+--from-literal="OCI_APM_RUM_PUBLIC_DATAKEY=${OCI_APM_RUM_PUBLIC_DATAKEY}"} \
    --dry-run=client -o yaml | kubectl apply -f -

# ── Create configmap ──────────────────────────────────────────────
echo "[standalone] Creating configmap..."
cat <<CONFIGMAP_EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: crm-config
  namespace: ${NAMESPACE}
data:
  APP_NAME: "enterprise-crm-portal"
  BRAND_NAME: "${BRAND_NAME:-Enterprise CRM}"
  APP_VERSION: "1.1.0"
  APP_PORT: "8080"
  APP_ENV: "production"
  APP_RUNTIME: "oke"
  SERVICE_NAMESPACE: "crm"
  DNS_DOMAIN: "${DNS_DOMAIN}"
  CRM_BASE_URL: "${CRM_URL}"
  ORACLE_DSN: "${ORACLE_DSN}"
  ORACLE_USER: "${ORACLE_USER}"
  ORACLE_WALLET_DIR: "/app/wallet"
  DATABASE_OBSERVABILITY_ENABLED: "true"
  OTEL_SERVICE_NAME: "enterprise-crm-portal"
  OCI_APM_ENDPOINT: "${OCI_APM_ENDPOINT:-}"
  OCI_APM_RUM_ENDPOINT: "${OCI_APM_RUM_ENDPOINT:-}"
  OCI_AUTH_MODE: "${OCI_AUTH_MODE:-instance_principal}"
  OCTO_DRONE_SHOP_URL: "${OCTO_DRONE_SHOP_URL:-}"
  EXTERNAL_ORDERS_URL: "${OCTO_DRONE_SHOP_URL:-}"
  EXTERNAL_ORDERS_PATH: "/api/orders"
  ORDERS_SYNC_ENABLED: "${ORDERS_SYNC_ENABLED:-true}"
  ORDERS_SYNC_INTERVAL_SECONDS: "300"
  IDCS_DOMAIN_URL: "${IDCS_DOMAIN_URL:-}"
  IDCS_CLIENT_ID: "${IDCS_CLIENT_ID:-}"
  IDCS_REDIRECT_URI: "${IDCS_REDIRECT_URI}"
  SECURITY_LOG_ENABLED: "true"
  OTLP_LOG_EXPORT_ENABLED: "false"
CONFIGMAP_EOF

# ── Build + push image ───────────────────────────────────────────
if [[ "${SKIP_BUILD:-}" != "true" ]]; then
    echo "[standalone] Building image ${IMAGE}:${IMAGE_TAG}..."
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="${SCRIPT_DIR}/../.."
    docker build -t "${IMAGE}:${IMAGE_TAG}" -t "${IMAGE}:latest" "${PROJECT_ROOT}"
    echo "[standalone] Pushing to OCIR..."
    docker push "${IMAGE}:${IMAGE_TAG}"
    docker push "${IMAGE}:latest"
fi

# ── Deploy ────────────────────────────────────────────────────────
echo "[standalone] Applying deployment..."
cat <<DEPLOY_EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: enterprise-crm-portal
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: enterprise-crm-portal
  template:
    metadata:
      labels:
        app: enterprise-crm-portal
    spec:
      containers:
      - name: crm
        image: ${IMAGE}:${IMAGE_TAG}
        ports:
        - containerPort: 8080
        envFrom:
        - configMapRef:
            name: crm-config
        - secretRef:
            name: crm-secrets
        volumeMounts:
        - name: wallet
          mountPath: /app/wallet
          readOnly: true
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 30
      volumes:
      - name: wallet
        secret:
          secretName: crm-wallet
---
apiVersion: v1
kind: Service
metadata:
  name: enterprise-crm-portal
  namespace: ${NAMESPACE}
spec:
  selector:
    app: enterprise-crm-portal
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
DEPLOY_EOF

# ── Wait for rollout ──────────────────────────────────────────────
echo "[standalone] Waiting for rollout..."
kubectl rollout status deployment/enterprise-crm-portal -n "$NAMESPACE" --timeout=120s

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Deployment complete!                                           ║"
echo "║                                                                 ║"
echo "║  Service: ClusterIP/enterprise-crm-portal in namespace ${NAMESPACE} ║"
echo "║  Health:  kubectl exec -n ${NAMESPACE} deploy/enterprise-crm-portal -- curl -s localhost:8080/health"
echo "║                                                                 ║"
echo "║  Next steps:                                                    ║"
echo "║  1. Create an OKE Ingress or LB Service pointing to port 80    ║"
echo "║  2. Configure DNS: crm.${DNS_DOMAIN} → LB IP                   ║"
echo "║  3. (Optional) Add TLS cert via cert-manager or OCI LB cert    ║"
echo "║  4. Login with the bootstrap admin credential from your secret ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
