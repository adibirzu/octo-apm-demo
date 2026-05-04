# Deployment

For the `DEFAULT` profile, use `cyber-sec.ro` as both the bootstrap base
domain (`DNS_BASE_DOMAIN`) and the rollout host domain (`DNS_DOMAIN`).
Check [Current Status](current-status.md) before relying on the shared
tenancy; it is not E2E-ready as of April 25, 2026.

## First-time tenancy bootstrap

Use `deploy/bootstrap.sh` for a fresh tenancy or a newly selected
compartment:

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
DNS_BASE_DOMAIN=cyber-sec.ro \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh
```

This is the canonical end-to-end path: OCIR repos, kubeconfig, ATP,
wallet/secret seeding, shared ingress, TLS loading, DNS, and initial
Shop+CRM rollout.

## Ongoing rollouts

```bash
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
DNS_DOMAIN=cyber-sec.ro \
./deploy/deploy.sh                  # Build + push + rollout

./deploy/deploy.sh --build-only     # Build + push, no rollout
./deploy/deploy.sh --rollout-only   # Roll out the existing latest tag
./deploy/deploy.sh --shop-only      # Only the shop service
./deploy/deploy.sh --crm-only       # Only the CRM service
```

Use `deploy/init-tenancy.sh` only when the cluster, ATP, and ingress are
already managed out-of-band and you want the repo to seed namespaces,
repos, and secrets without running the full lifecycle wrapper.

## Manual Workflow

### 1. Sync to Build VM

```bash
rsync -az --exclude '.git' --exclude '__pycache__' \
  . remote-builder:/tmp/octo-apm-demo-shop/
```

### 2. Build (Native x86_64)

```bash
TAG=$(date +%Y%m%d%H%M%S)
ssh remote-builder "cd /tmp/octo-apm-demo-shop && \
  docker build -f shop/Dockerfile \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${TAG} \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:latest ."
```

### 3. Push to OCIR

```bash
ssh remote-builder "docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${TAG} && \
  docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:latest"
```

### 4. Rollout on OKE

```bash
kubectl set image deployment/octo-drone-shop \
  app=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${TAG} -n octo-drone-shop

kubectl rollout status deployment/octo-drone-shop -n octo-drone-shop
```

## Verification

```bash
kubectl -n ingress-nginx get deploy,svc,pods,endpoints -o wide
kubectl get deploy -n octo-drone-shop octo-drone-shop
kubectl get deploy -n enterprise-crm enterprise-crm-portal
```

Both app deployments must show `2/2` before root Playwright E2E is
considered runnable.

## K8s Configuration

- **Replicas**: 2
- **Resources**: 250m CPU / 512Mi (request), 1 CPU / 1Gi (limit)
- **Liveness**: `/health` every 15s (12s initial delay)
- **Readiness**: `/ready` every 12s (18s initial delay)
- **Image pull**: OCIR with `ocir-pull-secret`
- **ATP wallet**: Mounted as read-only volume
