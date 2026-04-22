#!/usr/bin/env bash
# Apply the OKE manifests for octo-apm-demo.
#
# Order matters:
#   1. Namespaces
#   2. Secrets (bootstrapped by deploy/init-tenancy.sh into each ns)
#   3. SecretProviderClass (if OCI Vault CSI is installed)
#   4. Deployments + Services + LB + HPA + PDB
#   5. NetworkPolicies (last — otherwise they race with Service creation)
#
# Usage:
#   DNS_DOMAIN=octodemo.cloud \
#   OCIR_REGION=eu-frankfurt-1 \
#   OCIR_TENANCY=<namespace> \
#   OCI_LB_SUBNET_OCID=ocid1.subnet.oc1..xxx \
#   WAF_POLICY_SHOP_OCID=ocid1.webappfirewallpolicy.oc1..xxx \
#   WAF_POLICY_CRM_OCID=ocid1.webappfirewallpolicy.oc1..xxx \
#   IMAGE_TAG=latest \
#   ./deploy/oke/deploy-oke.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OKE_DIR="${REPO_ROOT}/k8s/oke"

: "${DNS_DOMAIN:?Set DNS_DOMAIN (e.g. octodemo.cloud)}"
: "${OCIR_REGION:?Set OCIR_REGION}"
: "${OCIR_TENANCY:?Set OCIR_TENANCY}"
: "${OCI_LB_SUBNET_OCID:?Set OCI_LB_SUBNET_OCID}"
: "${IMAGE_TAG:=latest}"
: "${WAF_POLICY_SHOP_OCID:=}"
: "${WAF_POLICY_CRM_OCID:=}"

export DNS_DOMAIN OCIR_REGION OCIR_TENANCY OCI_LB_SUBNET_OCID IMAGE_TAG \
    WAF_POLICY_SHOP_OCID WAF_POLICY_CRM_OCID

echo "================================================================"
echo " OKE deploy — octo-apm-demo"
echo "   DNS_DOMAIN:          ${DNS_DOMAIN}"
echo "   Shop URL:            https://drone.${DNS_DOMAIN}"
echo "   CRM URL:             https://backend.${DNS_DOMAIN}"
echo "   OCIR:                ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}"
echo "   IMAGE_TAG:           ${IMAGE_TAG}"
echo "   LB subnet:           ${OCI_LB_SUBNET_OCID:0:24}..."
echo "   WAF policy (shop):   ${WAF_POLICY_SHOP_OCID:0:24}${WAF_POLICY_SHOP_OCID:+...}"
echo "   WAF policy (crm):    ${WAF_POLICY_CRM_OCID:0:24}${WAF_POLICY_CRM_OCID:+...}"
echo "================================================================"

echo
echo "[1/5] Applying namespaces..."
kubectl apply -f "${OKE_DIR}/common/namespaces.yaml"

echo
echo "[2/5] Checking bootstrap Secrets..."
for ns in octo-shop-prod octo-backend-prod; do
    for sec in octo-auth octo-atp octo-atp-wallet octo-oci-config; do
        if ! kubectl get secret "${sec}" -n "${ns}" >/dev/null 2>&1; then
            echo "  ⚠  Missing Secret ${sec} in ${ns} — run deploy/init-tenancy.sh with K8S_NAMESPACE=${ns}"
        fi
    done
done

echo
echo "[3/5] Applying SecretProviderClass (optional; needs OCI Vault CSI driver)..."
if kubectl get crd secretproviderclasses.secrets-store.csi.x-k8s.io >/dev/null 2>&1; then
    for ns in octo-shop-prod octo-backend-prod; do
        NAMESPACE=$ns envsubst < "${OKE_DIR}/common/secret-provider-class.yaml" | kubectl apply -f -
    done
else
    echo "  ⊘ OCI Secrets Store CSI driver not installed — skipping. Using Kubernetes Secrets instead."
fi

echo
echo "[4/5] Applying Deployments + Services + HPA + PDB..."
envsubst < "${OKE_DIR}/shop/deployment.yaml" | kubectl apply -f -
envsubst < "${OKE_DIR}/crm/deployment.yaml"  | kubectl apply -f -

echo
echo "[5/5] Applying NetworkPolicies..."
kubectl apply -f "${OKE_DIR}/common/network-policies.yaml"

echo
echo "Waiting for rollouts..."
kubectl rollout status deployment/octo-drone-shop        -n octo-shop-prod    --timeout=240s
kubectl rollout status deployment/enterprise-crm-portal  -n octo-backend-prod --timeout=240s

echo
echo "LoadBalancer public IPs (may take 1–2 min to populate):"
kubectl get svc octo-drone-shop-lb        -n octo-shop-prod
kubectl get svc enterprise-crm-portal-lb  -n octo-backend-prod

echo
echo "================================================================"
echo " Done. Point DNS:"
echo "   drone.${DNS_DOMAIN}    → shop LB public IP"
echo "   backend.${DNS_DOMAIN}  → crm  LB public IP"
echo
echo "Validate:"
echo "   curl -s https://drone.${DNS_DOMAIN}/ready   | jq"
echo "   curl -s https://backend.${DNS_DOMAIN}/ready | jq"
echo "================================================================"
