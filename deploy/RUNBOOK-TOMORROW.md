# Tomorrow's Deploy Runbook

Target: latest everything on OCI (OKE or unified VM), all telemetry
into OCI Observability, validated in 60–90 minutes.

## 0. Preflight (5 min)

```bash
cd /opt/octo || git clone https://github.com/adibirzu/octo-apm-demo.git /opt/octo && cd /opt/octo

# Verify repo + scripts
./deploy/verify.sh
# Expected: VERIFY PASSED — 0 warnings

# Pin deploy scope
export DNS_DOMAIN=example.tld
export OCIR_REGION=eu-frankfurt-1
export OCIR_TENANCY=<your-tenancy-namespace>
export OCI_COMPARTMENT_ID=<ocid>
```

## 1. Tenancy bootstrap (10 min)

```bash
export K8S_NAMESPACE=octo-shop-prod
./deploy/pre-flight-check.sh
./deploy/init-tenancy.sh
```

Repeat `init-tenancy.sh` with `K8S_NAMESPACE=octo-backend-prod` for CRM.

## 2. Observability plane (15 min)

```bash
# APM Domain + RUM Web App
PLAN_ONLY=false ./deploy/oci/ensure_apm.sh --apply

# Export the APM outputs into env
eval "$(./deploy/oci/ensure_apm.sh --print | grep ^export)"

# Stack Monitoring on ATP
DRY_RUN=false AUTONOMOUS_DATABASE_ID=<atp-ocid> \
  ./deploy/oci/ensure_stack_monitoring.sh

# Log Analytics source + parser
python3 tools/create_la_source.py \
  --la-namespace <la-ns> \
  --la-log-group-id <la-lg-ocid> \
  --apply

# Saved searches (APM↔LA round-trip)
LA_NAMESPACE=<la-ns> LA_LOG_GROUP_ID=<la-lg-ocid> \
  ./tools/la-saved-searches/apply.sh
```

## 3. Image builds (20 min, remote x86_64 builder)

```bash
# Shop + CRM (app tier)
OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop      ./deploy/deploy-shop.sh --build-only
OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal ./deploy/deploy-crm.sh  --build-only

# Platform services (OCI 360)
for svc in otel-gateway load-control browser-runner async-worker remediator object-pipeline edge-fuzz; do
  docker build --platform linux/amd64 \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-${svc}:$(date +%Y%m%d%H%M%S) \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-${svc}:latest \
    services/${svc}/
  docker push --all-tags ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-${svc}
done
```

## 4a. Runtime option A — OKE (30 min)

```bash
OCI_LB_SUBNET_OCID=<subnet-ocid> \
WAF_POLICY_SHOP_OCID=<waf-ocid> \
WAF_POLICY_CRM_OCID=<waf-ocid> \
IMAGE_TAG=latest \
./deploy/oke/deploy-oke.sh

# Platform services — 11 manifests, one envsubst each
for d in services/otel-gateway services/load-control services/async-worker services/cache services/object-pipeline services/remediator; do
  envsubst < $d/k8s/deployment.yaml | kubectl apply -f -
done

# browser-runner + container-lab launched on demand via load-control
# edge-fuzz runs as subprocess of load-control

# Verify all rollouts
for ns in octo-shop-prod octo-backend-prod octo-otel octo-load-control octo-async octo-cache octo-remediator octo-object; do
  kubectl -n $ns rollout status deployment --timeout=120s
done
```

## 4b. Runtime option B — Unified VM (15 min)

```bash
cd deploy/vm
cp .env.template .env
${EDITOR:-vi} .env       # fill DNS_DOMAIN, OCIR, ATP, keys
unzip /path/to/Wallet_<DB>.zip -d wallet
sudo certbot certonly --standalone -d shop.example.tld -d crm.example.tld
sudo cp /etc/letsencrypt/live/shop.example.tld/*.pem nginx/tls/shop/
sudo cp /etc/letsencrypt/live/crm.example.tld/*.pem nginx/tls/crm/
sudo ./install.sh
```

## 5. DNS + validate (5 min)

Point `shop.example.tld` + `crm.example.tld` at the LB or VM IP.

```bash
curl -sS https://shop.example.tld/ready | jq
curl -sS https://crm.example.tld/ready | jq
curl -sS https://shop.example.tld/api/version | jq
curl -sS https://shop.example.tld/api/integrations/schema | jq .info.title

# Rollout validator
python tools/rollout-validator/validate.py \
  --namespace octo-shop-prod --label-selector app=octo-drone-shop \
  --expected-tag <your-tag>
```

## 6. Turn on signal (5 min)

```bash
# Traffic generator (continuous — demos)
OCTO_TRAFFIC_RUN_DURATION_SECONDS=0 \
OCTO_TRAFFIC_SHOP_BASE_URL=https://shop.example.tld \
OCTO_TRAFFIC_TARGET_RPS=2 \
OCTO_TRAFFIC_OTEL_EXPORTER_OTLP_ENDPOINT=http://gateway.octo-otel.svc.cluster.local:4318 \
kubectl -n octo-traffic apply -f tools/traffic-generator/k8s/deployment.yaml
```

## 7. E2E smoke (5 min)

```bash
FULL_PLATFORM_E2E_ENABLED=1 \
SHOP_BASE_URL=https://shop.example.tld \
CRM_BASE_URL=https://crm.example.tld \
LOAD_CONTROL_URL=http://load-control.octo-load-control:8080 \
REMEDIATOR_URL=http://remediator.octo-remediator:8080 \
OBJECT_PIPELINE_URL=http://object-pipeline.octo-object:8080 \
INTERNAL_SERVICE_KEY=<shared-key> \
npx playwright test tests/e2e/full-platform-smoke.spec.ts
```

Green = done. Next: workshop Lab 01 to verify the APM trace pivot.

## Rollback

```bash
# Image was bad
kubectl rollout undo deployment/<name> -n <ns>

# Wanted a clean start
kubectl delete namespace octo-shop-prod octo-backend-prod octo-otel octo-load-control octo-async octo-cache octo-remediator octo-object
# ... then re-run from §1
```

## If something misbehaves

| Symptom | First check |
|---|---|
| `/ready` returns `database.reachable=false` | Wallet mount + `ORACLE_DSN`; see `KB.md` if your project has one |
| APM Trace Explorer empty | OTel gateway pod logs; `OCI_APM_ENDPOINT` + `PRIVATE_DATAKEY` on the gateway Secret |
| LA search returns 0 rows | Service Connector `la-pipeline-octo-shop-app` — Console → Logging → Service Connectors |
| Alarm never fires | Notifications topic OCID on the alarm definition; subscribe a test email to confirm the topic itself works |
| K8s Job never starts | PodAffinity — check at least one target-labelled pod is running in the target namespace |
