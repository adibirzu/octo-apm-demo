# OKE Deployment

## 1. Set Environment

```bash
export DNS_DOMAIN="yourcompany.cloud"
export AUTH_TOKEN_SECRET="$(openssl rand -hex 32)"
export ORACLE_DSN="myatp_low"
export ORACLE_PASSWORD="<your-atp-password>"
export OCI_APM_ENDPOINT="https://<apm-data-upload-endpoint>"
export OCI_APM_PRIVATE_DATAKEY="<private-data-key>"
export OCI_LB_SUBNET_OCID="ocid1.subnet.oc1.<region>...."
export OCIR_REPO="<region>.ocir.io/<namespace>"
```

## 2. Build and Push

!!! warning "ARM Machines"
    Never build locally on Apple Silicon. Use an x86_64 build VM.

```bash
# Sync to build VM
rsync -az --exclude '.git' --exclude '__pycache__' . control-plane:/tmp/octo-drone-shop/

# Build + push on VM
ssh control-plane "cd /tmp/octo-drone-shop && \
  docker build -t ${OCIR_REPO}/octo-drone-shop:latest . && \
  docker push ${OCIR_REPO}/octo-drone-shop:latest"
```

Or use the deploy script:

```bash
./deploy/deploy.sh
```

## 3. Create K8s Secrets

```bash
NAMESPACE="octo-drone-shop"
kubectl create namespace $NAMESPACE

# Required
kubectl -n $NAMESPACE create secret generic octo-auth \
  --from-literal=token-secret="${AUTH_TOKEN_SECRET}"

kubectl -n $NAMESPACE create secret generic octo-atp \
  --from-literal=dsn="${ORACLE_DSN}" \
  --from-literal=username="ADMIN" \
  --from-literal=password="${ORACLE_PASSWORD}" \
  --from-literal=wallet-password="${ORACLE_WALLET_PASSWORD}"

kubectl -n $NAMESPACE create secret generic octo-apm \
  --from-literal=endpoint="${OCI_APM_ENDPOINT}" \
  --from-literal=private-key="${OCI_APM_PRIVATE_DATAKEY}" \
  --from-literal=public-key="${OCI_APM_PUBLIC_DATAKEY}" \
  --from-literal=rum-endpoint="${OCI_APM_RUM_ENDPOINT}"

# ATP wallet
kubectl -n $NAMESPACE create secret generic octo-atp-wallet \
  --from-file=cwallet.sso --from-file=tnsnames.ora --from-file=sqlnet.ora
```

## 4. Deploy

```bash
envsubst < deploy/k8s/deployment.yaml | kubectl apply -f -
kubectl rollout status deployment/octo-drone-shop -n $NAMESPACE
```

## 5. Provision OCI Services

```bash
export COMPARTMENT_ID="<compartment-ocid>"
export SHOP_PUBLIC_URL="https://shop.${DNS_DOMAIN}"

# Monitoring (alarms + health checks)
./deploy/oci/ensure_monitoring.sh

# WAF protection rules
LOAD_BALANCER_OCID="<lb-ocid>" ./deploy/oci/ensure_waf.sh

# Cloud Guard
./deploy/oci/ensure_cloud_guard.sh

# Security Zones
./deploy/oci/ensure_security_zones.sh

# Vault
./deploy/oci/ensure_vault.sh

# DB Observability
AUTONOMOUS_DATABASE_ID="<atp-ocid>" ./deploy/oci/ensure_db_observability.sh
```

## 6. Verify

```bash
curl https://shop.${DNS_DOMAIN}/ready | python3 -m json.tool
curl https://shop.${DNS_DOMAIN}/api/observability/360 | python3 -m json.tool
```
