# Tomorrow's Deploy Runbook

Target: a fresh, E2E-ready tenancy using the current unified bootstrap
surface plus the optional OCI 360 platform services.

## 0. Preflight

```bash
cd /opt/octo || git clone https://github.com/example-org/octo-apm-demo.git /opt/octo && cd /opt/octo

python3 -m pytest -q tests/test_unified_deploy_surface.py
bash deploy/verify.sh
```

Expected result: `VERIFY PASSED` and no failing repo-surface tests.

## 1. Bootstrap the base tenancy

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=<ocid> \
DNS_BASE_DOMAIN=<your-domain> \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh
```

`deploy/bootstrap.sh` owns the current canonical first run. It validates
the OCI profile, reuses or discovers the cluster, provisions or
reconnects ATP, seeds the shared secrets, deploys Shop + CRM into
`octo-drone-shop` and `enterprise-crm`, and publishes `shop.<domain>`
plus `crm.<domain>`.

## 2. Optional OCI 360 platform services

Build and deploy the extra services only after the base bootstrap is
green.

```bash
for svc in otel-gateway load-control browser-runner async-worker remediator object-pipeline edge-fuzz; do
  docker build --platform linux/amd64 \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-${svc}:$(date +%Y%m%d%H%M%S) \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-${svc}:latest \
    services/${svc}/
  docker push --all-tags ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-${svc}
done

for d in services/otel-gateway services/load-control services/async-worker services/cache services/object-pipeline services/remediator; do
  envsubst < $d/k8s/deployment.yaml | kubectl apply -f -
done
```

`browser-runner` and `container-lab` stay on-demand. `edge-fuzz` is
invoked by `octo-load-control`.

## 3. Validate the rollout

```bash
for ns in octo-drone-shop enterprise-crm octo-otel octo-load-control octo-async octo-cache octo-remediator octo-object; do
  kubectl -n $ns rollout status deployment --timeout=120s
done

python tools/rollout-validator/validate.py \
  --namespace octo-drone-shop \
  --label-selector app=octo-drone-shop \
  --expected-tag <your-tag>
```

Then validate the public tenancy surface:

```bash
curl -sS https://shop.<your-domain>/ready | jq
curl -sS https://crm.<your-domain>/ready | jq
curl -sS https://shop.<your-domain>/api/version | jq
curl -sS https://shop.<your-domain>/api/integrations/schema | jq .info.title
```

## 4. Turn on background signal

```bash
DNS_DOMAIN=<your-domain> \
OCIR_REGION=<region> \
OCIR_TENANCY=<namespace> \
IMAGE_TAG=latest \
kubectl -n octo-traffic apply -f tools/traffic-generator/k8s/deployment.yaml
```

This keeps traces, logs, and metrics warm for the workshops and smoke
tests.

## 5. Hand off to E2E

```bash
FULL_PLATFORM_E2E_ENABLED=1 \
SHOP_BASE_URL=https://shop.<your-domain> \
CRM_BASE_URL=https://crm.<your-domain> \
LOAD_CONTROL_URL=http://load-control.octo-load-control:8080 \
REMEDIATOR_URL=http://remediator.octo-remediator:8080 \
OBJECT_PIPELINE_URL=http://object-pipeline.octo-object:8080 \
INTERNAL_SERVICE_KEY=<shared-key> \
npx playwright test tests/e2e/full-platform-smoke.spec.ts
```

If SSO is wired, follow with:

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
OCTO_E2E_TEST_USER_EMAIL=e2e@example.com \
OCTO_E2E_TEST_USER_PASSWORD='***' \
SSO_E2E_ENABLED=1 \
npx playwright test tests/e2e/sso-oidc-pkce.spec.ts
```

## Rollback

```bash
kubectl rollout undo deployment/<name> -n <ns>

# For a targeted teardown of the workloads created by bootstrap:
./deploy/destroy.sh
```

## If Something Misbehaves

| Symptom | First check |
|---|---|
| `/ready` returns `database.reachable=false` | Wallet mount + `ORACLE_DSN` + ATP state |
| APM Trace Explorer empty | OTel gateway logs; `OCI_APM_ENDPOINT` + `PRIVATE_DATAKEY` on the gateway Secret |
| LA search returns 0 rows | Service Connector `la-pipeline-octo-shop-app` and `tools/create_la_source.py --apply` |
| Alarm never fires | Notifications topic OCID and subscription status |
| Ingress is `0/2` or has no endpoints | `kubectl -n ingress-nginx get deploy,pods,endpoints -o wide` |
