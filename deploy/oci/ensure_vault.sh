#!/usr/bin/env bash
# Ensure OCI Vault for OCTO Drone Shop (Shop service) secret management.
#
# Creates (idempotently):
#   1. OCI Vault (or reuses existing)
#   2. Master Encryption Key (AES-256)
#   3. Vault secrets for: AUTH_TOKEN_SECRET, INTERNAL_SERVICE_KEY
#
# Existing K8s secrets remain functional — this script adds Vault as the
# authoritative secret store. A future iteration can wire K8s ExternalSecrets
# or OCI Secrets Store CSI driver to pull from Vault automatically.
#
# Prerequisites:
#   - OCI CLI configured (instance_principal or config file)
#   - COMPARTMENT_ID set
#
# Usage:
#   COMPARTMENT_ID="ocid1.compartment...." \
#   AUTH_TOKEN_SECRET_VALUE="<secret>" \
#   INTERNAL_SERVICE_KEY_VALUE="<key>" \
#   ./deploy/oci/ensure_vault.sh

set -euo pipefail

: "${COMPARTMENT_ID:?COMPARTMENT_ID is required}"
VAULT_NAME="${VAULT_NAME:-octo-drone-shop-vault}"
KEY_NAME="${KEY_NAME:-octo-drone-shop-master-key}"

echo "[vault] Compartment: ${COMPARTMENT_ID}"
echo "[vault] Vault name: ${VAULT_NAME}"

# ── 1. Vault ────────────────────────────────────────────────────
echo "[vault] Checking for existing vault '${VAULT_NAME}'..."

existing_vault=$(oci kms management vault list \
    --compartment-id "${COMPARTMENT_ID}" \
    --query "data[?\"display-name\"=='${VAULT_NAME}' && \"lifecycle-state\"=='ACTIVE'].id | [0]" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_vault" && "$existing_vault" != "null" && "$existing_vault" != "None" ]]; then
    VAULT_OCID="$existing_vault"
    echo "[vault] Vault exists: ${VAULT_OCID}"
else
    echo "[vault] Creating vault (this may take 1-2 minutes)..."
    VAULT_OCID=$(oci kms management vault create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${VAULT_NAME}" \
        --vault-type "DEFAULT" \
        --wait-for-state "ACTIVE" \
        --query "data.id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -z "$VAULT_OCID" || "$VAULT_OCID" == "null" ]]; then
        echo "[vault] Vault creation failed — check OCI permissions (manage vaults)"
        exit 1
    fi
    echo "[vault] Vault created: ${VAULT_OCID}"
fi

# Get management endpoint
MGMT_ENDPOINT=$(oci kms management vault get \
    --vault-id "${VAULT_OCID}" \
    --query "data.\"management-endpoint\"" \
    --raw-output 2>/dev/null || echo "")

echo "[vault] Management endpoint: ${MGMT_ENDPOINT}"

# ── 2. Master Encryption Key ───────────────────────────────────
echo "[vault] Checking for master key '${KEY_NAME}'..."

existing_key=$(oci kms management key list \
    --compartment-id "${COMPARTMENT_ID}" \
    --endpoint "${MGMT_ENDPOINT}" \
    --query "data[?\"display-name\"=='${KEY_NAME}' && \"lifecycle-state\"=='ENABLED'].id | [0]" \
    --raw-output 2>/dev/null || echo "")

if [[ -n "$existing_key" && "$existing_key" != "null" && "$existing_key" != "None" ]]; then
    KEY_OCID="$existing_key"
    echo "[vault] Master key exists: ${KEY_OCID}"
else
    echo "[vault] Creating AES-256 master encryption key..."
    KEY_OCID=$(oci kms management key create \
        --compartment-id "${COMPARTMENT_ID}" \
        --display-name "${KEY_NAME}" \
        --endpoint "${MGMT_ENDPOINT}" \
        --key-shape '{"algorithm":"AES","length":32}' \
        --protection-mode "HSM" \
        --wait-for-state "ENABLED" \
        --query "data.id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -z "$KEY_OCID" || "$KEY_OCID" == "null" ]]; then
        echo "[vault] Key creation failed"
        exit 1
    fi
    echo "[vault] Master key created: ${KEY_OCID}"
fi

# ── 3. Create Secrets ──────────────────────────────────────────
create_secret() {
    local secret_name="$1"
    local secret_value="$2"
    local description="$3"

    if [[ -z "$secret_value" ]]; then
        echo "[vault] Skipping '${secret_name}' — no value provided"
        return
    fi

    existing_secret=$(oci vault secret list \
        --compartment-id "${COMPARTMENT_ID}" \
        --name "${secret_name}" \
        --vault-id "${VAULT_OCID}" \
        --lifecycle-state "ACTIVE" \
        --query "data.items[0].id" \
        --raw-output 2>/dev/null || echo "")

    if [[ -n "$existing_secret" && "$existing_secret" != "null" && "$existing_secret" != "None" ]]; then
        echo "[vault] Secret '${secret_name}' exists — updating version..."
        # Encode value to base64
        encoded=$(echo -n "$secret_value" | base64)
        oci vault secret update-secret-version \
            --secret-id "${existing_secret}" \
            --secret-content-content "${encoded}" \
            --secret-content-content-type "BASE64" \
            --secret-content-stage "CURRENT" 2>/dev/null || \
            echo "[vault] Secret version update may have failed (check manually)"
        return
    fi

    echo "[vault] Creating secret '${secret_name}'..."
    encoded=$(echo -n "$secret_value" | base64)
    oci vault secret create-base64 \
        --compartment-id "${COMPARTMENT_ID}" \
        --secret-name "${secret_name}" \
        --vault-id "${VAULT_OCID}" \
        --key-id "${KEY_OCID}" \
        --description "${description}" \
        --secret-content-content "${encoded}" \
        --secret-content-content-type "BASE64" \
        --secret-content-stage "CURRENT" 2>/dev/null || \
        echo "[vault] Secret creation may have failed for '${secret_name}'"

    echo "[vault] Secret '${secret_name}' created"
}

create_secret "octo-auth-token-secret" \
    "${AUTH_TOKEN_SECRET_VALUE:-}" \
    "Bearer token signing key for OCTO Drone Shop"

create_secret "octo-internal-service-key" \
    "${INTERNAL_SERVICE_KEY_VALUE:-}" \
    "Service-to-service auth key for CRM-Shop integration"

create_secret "octo-atp-password" \
    "${ATP_PASSWORD_VALUE:-}" \
    "Oracle ATP ADMIN password"

create_secret "octo-atp-wallet-password" \
    "${ATP_WALLET_PASSWORD_VALUE:-}" \
    "Oracle ATP wallet password"

cat <<'EOF'

Vault configuration complete.

Secret rotation:
  Vault secrets support automatic rotation via OCI Functions.
  See: https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/managingsecrets.htm

K8s integration (next step):
  Install the OCI Secrets Store CSI driver to pull Vault secrets into K8s pods:
    1. Deploy secrets-store-csi-driver
    2. Create SecretProviderClass referencing Vault secrets
    3. Mount as volumes or env vars in deployment.yaml

Cloud Guard correlation:
  Cloud Guard will now show Vault as the secret store (no more K8s-only secrets warning).
  Cloud Guard recipe → Security Zone → "secrets must be in Vault" policy.

EOF

echo "Outputs:"
echo "  VAULT_OCID=${VAULT_OCID}"
echo "  KEY_OCID=${KEY_OCID}"
echo "  MGMT_ENDPOINT=${MGMT_ENDPOINT}"
