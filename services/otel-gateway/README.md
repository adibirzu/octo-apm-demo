# octo-otel-gateway

Central OpenTelemetry Collector for `octo-apm-demo`. Single ingress for
every service's OTLP export, single egress to OCI APM + Monitoring +
Logging. Sits between apps and OCI so sampling, batching, enrichment,
and redaction policies change in one place without app redeploys.

## Why a gateway instead of direct export

| Problem | Direct OTLP → OCI | Gateway → OCI |
|---|---|---|
| Sampling policy change | redeploy every app | edit ConfigMap, kubectl rollout restart deployment/otel-gateway |
| Add a new exporter (e.g., Splunk) | redeploy every app | add to gateway pipeline only |
| Bad data leaks (PII in span attribute) | already at OCI | redact at the gateway processor before egress |
| Outage at OCI APM | every app blocks on export | gateway absorbs with retry queue, apps see no impact |
| Add a new field to every span | hand-edit every app | one `resource` processor entry |

## Components

| File | Purpose |
|---|---|
| `config/otel-collector.yaml` | Pipelines + processors + exporters. The single source of truth. |
| `Dockerfile` | Pins `otel/opentelemetry-collector-contrib` and bakes the default config. |
| `k8s/deployment.yaml` | OKE Deployment + Service + PDB in dedicated `octo-otel` namespace. |

## Pipelines

| Signal | Receiver | Processors | Exporter |
|---|---|---|---|
| Traces | OTLP gRPC + HTTP | `memory_limiter` → `resource` (stamp `service.namespace=octo`, `deployment.environment`) → `attributes/run_id` (promote `chaos.run_id`, `workflow.id`) → `attributes/redact` (strip CC-shaped strings) → `batch` | OCI APM via `otlphttp` |
| Metrics | OTLP + Prometheus scrape (workflow-gateway) | `memory_limiter` → `resource` → `batch` | stdout (debug) — OCI Monitoring exporter wires in v2 |
| Logs | OTLP | `memory_limiter` → `resource` → `attributes/run_id` → `attributes/redact` → `batch` | stdout (debug) — OCI Logging exporter wires in v2 |

## Ports

| Port | Purpose |
|---|---|
| 4317 | OTLP gRPC |
| 4318 | OTLP HTTP |
| 13133 | health check |
| 1777 | pprof |
| 55679 | zpages (per-pipeline diagnostics) |
| 8888 | collector self-metrics (Prometheus format) |

## Apps point here, not at OCI directly

In each app Deployment, set:

```yaml
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: "http://gateway.octo-otel.svc.cluster.local:4318"
# Remove OCI_APM_ENDPOINT + OCI_APM_PRIVATE_DATAKEY from app pods —
# they live on the gateway only.
```

## Build + push

```bash
docker build --platform linux/amd64 \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-otel-gateway:latest \
    services/otel-gateway/

docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-otel-gateway:latest
```

## Deploy (OKE)

```bash
# 1. Create the ConfigMap from the source-of-truth yaml
kubectl create configmap otel-collector-config \
    --from-file=otel-collector.yaml=services/otel-gateway/config/otel-collector.yaml \
    -n octo-otel \
    --dry-run=client -o yaml | kubectl apply -f -

# 2. Apply the namespace + deployment
DNS_DOMAIN=octodemo.cloud \
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
IMAGE_TAG=latest \
envsubst < services/otel-gateway/k8s/deployment.yaml | kubectl apply -f -

# 3. Verify
kubectl rollout status deployment/otel-gateway -n octo-otel
kubectl port-forward -n octo-otel svc/gateway 13133:13133
curl -s http://localhost:13133/  # → 200 OK
```

## Deploy (VM / docker-compose)

Add to `deploy/vm/docker-compose-unified.yml`:

```yaml
  otel-gateway:
    image: ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-otel-gateway:${TAG:-latest}
    restart: unless-stopped
    networks: [octo]
    environment:
      DNS_DOMAIN: "${DNS_DOMAIN}"
      OTEL_DEPLOYMENT_ENVIRONMENT: "production"
      OCI_APM_ENDPOINT: "${OCI_APM_ENDPOINT}"
      OCI_APM_PRIVATE_DATAKEY: "${OCI_APM_PRIVATE_DATAKEY}"
    ports:
      - "4317:4317"
      - "4318:4318"
      - "13133:13133"
```

Then update shop + crm services to point at `http://otel-gateway:4318`
instead of OCI APM directly.

## Verify the gateway is enriching spans

```bash
# Send a test span via OTLP HTTP
curl -X POST http://gateway.octo-otel.svc.cluster.local:4318/v1/traces \
    -H "Content-Type: application/json" \
    -d @- <<'EOF'
{
  "resourceSpans": [{
    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "test-emitter"}}]},
    "scopeSpans": [{
      "spans": [{
        "traceId": "00000000000000000000000000000001",
        "spanId":  "0000000000000001",
        "name": "verify",
        "kind": 1,
        "startTimeUnixNano": "1700000000000000000",
        "endTimeUnixNano":   "1700000000100000000"
      }]
    }]
  }]
}
EOF
```

Check OCI APM Trace Explorer for `traceId = '00000000000000000000000000000001'`.
The span's resource attributes should include `service.namespace=octo`
and `deployment.environment=production` — added by the `resource`
processor.

## Operational notes

- **Memory limiter at 80% percent** prevents OOM kills under burst.
- **Sending queue size 5000** absorbs ~5 minutes of OCI APM unavailability
  at typical demo load.
- **PDB minAvailable: 1** means rolling restarts never drop telemetry
  on the floor.
- **zpages on :55679** — `/debug/tracez` shows the last N spans per
  pipeline; invaluable when diagnosing "why is OCI not seeing my
  trace?".

## What's next

KG-023 (planned): swap `debug/metrics` and `debug/logs` exporters for
OCI Monitoring + OCI Logging native exporters once they reach GA in
opentelemetry-collector-contrib.
