# Deployment

## Automated Deploy Script

```bash
./deploy/deploy.sh                  # Build + push + rollout
./deploy/deploy.sh --build-only     # Build + push, no rollout
./deploy/deploy.sh --rollout-only   # Rollout existing latest tag
```

## Manual Workflow

### 1. Sync to Build VM

```bash
rsync -az --exclude '.git' --exclude '__pycache__' \
  . remote-builder:/tmp/octo-drone-shop/
```

### 2. Build (Native x86_64)

```bash
TAG=$(date +%Y%m%d%H%M%S)
ssh remote-builder "cd /tmp/octo-drone-shop && \
  docker build -t ${OCIR_REPO}/octo-drone-shop:${TAG} \
               -t ${OCIR_REPO}/octo-drone-shop:latest ."
```

### 3. Push to OCIR

```bash
ssh remote-builder "docker push ${OCIR_REPO}/octo-drone-shop:${TAG} && \
  docker push ${OCIR_REPO}/octo-drone-shop:latest"
```

### 4. Rollout on OKE

```bash
kubectl set image deployment/octo-drone-shop \
  app=${OCIR_REPO}/octo-drone-shop:${TAG} -n octo-drone-shop

kubectl rollout status deployment/octo-drone-shop -n octo-drone-shop
```

## K8s Configuration

- **Replicas**: 2
- **Resources**: 250m CPU / 512Mi (request), 1 CPU / 1Gi (limit)
- **Liveness**: `/health` every 15s (12s initial delay)
- **Readiness**: `/ready` every 12s (18s initial delay)
- **Image pull**: OCIR with `ocir-pull-secret`
- **ATP wallet**: Mounted as read-only volume
