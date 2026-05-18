# octo-traffic-generator

Realistic synthetic traffic for `octo-apm-demo`. **Not a load tool** —
this is a user-population simulator that emits HTTP requests + OTLP
traces shaped like real visitors so APM, RUM, and Log Analytics have
real signal instead of demo noise.

## Why it exists

- Observability stacks are boring (and broken) without traffic. Empty
  APM widgets don't prove anything during a demo.
- `k6` generates load; this generates **behaviour**: browsing depth
  (Pareto), session duration (log-normal), funnel conversion (Bernoulli),
  arrival times (Poisson). The result looks indistinguishable from a
  real userbase in Trace Explorer.
- Failure injection (default 5%) keeps error widgets non-empty so
  operators can practice triage on live-ish data.

## Run

### Local one-shot

```bash
cd tools/traffic-generator
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
OCTO_TRAFFIC_SHOP_BASE_URL=https://shop.example.test \
  OCTO_TRAFFIC_TARGET_RPS=2.0 \
  OCTO_TRAFFIC_RUN_DURATION_SECONDS=60 \
  octo-traffic
```

### Continuous (Kubernetes)

```bash
# Build + push
docker build --platform linux/amd64 \
  -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-traffic-generator:latest .
docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-traffic-generator:latest

# Deploy
envsubst < k8s/deployment.yaml | kubectl apply -f -
```

### Continuous (Docker Compose, VM path)

Add to the root `deploy/vm/docker-compose-unified.yml`:

```yaml
  traffic:
    image: ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-traffic-generator:${TAG:-latest}
    restart: unless-stopped
    environment:
      OCTO_TRAFFIC_SHOP_BASE_URL: "https://shop.${DNS_DOMAIN}"
      OCTO_TRAFFIC_CRM_BASE_URL: "https://crm.${DNS_DOMAIN}"
      OCTO_TRAFFIC_TARGET_RPS: "1.0"
      OCTO_TRAFFIC_OTEL_EXPORTER_OTLP_ENDPOINT: "${OCI_APM_ENDPOINT}"
      OCI_APM_PRIVATE_DATAKEY: "${OCI_APM_PRIVATE_DATAKEY}"
    depends_on:
      shop:
        condition: service_healthy
      crm:
        condition: service_healthy
```

## Configuration (all via env vars)

| Var | Default | Purpose |
|---|---|---|
| `OCTO_TRAFFIC_SHOP_BASE_URL` | `https://shop.example.test` | Shop public URL |
| `OCTO_TRAFFIC_CRM_BASE_URL` | `https://crm.example.test` | CRM public URL |
| `OCTO_TRAFFIC_TARGET_RPS` | `2.0` | New sessions per second |
| `OCTO_TRAFFIC_CONCURRENT_SESSION_LIMIT` | `50` | Hard cap on in-flight sessions |
| `OCTO_TRAFFIC_BURST_MULTIPLIER` | `1.0` | Multiplier during flash-sale simulations |
| `OCTO_TRAFFIC_FAILURE_INJECTION_RATE` | `0.05` | Fraction of sessions that force a bad request |
| `OCTO_TRAFFIC_CHAOS_MODE` | `false` | Additionally toggle CRM chaos admin |
| `OCTO_TRAFFIC_RUN_DURATION_SECONDS` | `0` | `0` = forever, `>0` = one-shot burst |
| `OCTO_TRAFFIC_OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | OTLP/HTTP endpoint or OCI APM data upload endpoint (empty = no export) |
| `OCTO_TRAFFIC_OTEL_EXPORTER_OTLP_HEADERS` | `""` | `api-key=...,tenant-id=...` |
| `OCI_APM_PRIVATE_DATAKEY` | `""` | Optional private data key when exporting directly to OCI APM |
| `OCTO_TRAFFIC_SEED` | `0` | `0` = non-deterministic; any other = reproducible |

## Session state machine

```
arrive ─► browse (Pareto pageviews)
          │
          ├── 45% bounce      ─► BROWSED_ONLY
          └── 55% add-to-cart
                    │
                    ├── 25% SSO whoami probe
                    └── 30% of 55% → checkout
                              │
                              ├── 201/200 ─► COMPLETED_PURCHASE
                              ├── 429     ─► RATE_LIMITED
                              ├── 4xx/5xx ─► FAILED_CHECKOUT
                              └── network ─► NETWORK_ERROR
```

## What it looks like in APM

- Service: `octo-traffic-generator` (distinct from shop/CRM)
- Every session emits one root span `traffic.session` with attributes:
  - `session.id`
  - `session.outcome` (one of six values above)
  - `session.force_failure` (true if this session will tickle an error)
  - `session.duration_seconds_simulated`
- Inside each session, HTTPX auto-instrumentation emits a span per
  request — these link to the upstream shop/CRM spans via W3C
  `traceparent` propagation. The traces you see in APM are true
  end-to-end chains: generator → LB → WAF → shop → CRM → ATP.

## Tests

```bash
pytest -q
# 10 passed in ~5s — no network required
```

Tests use `respx` to stub HTTP and never touch a real shop. Distribution
tests pin the seed and assert shape properties (pareto cap, bernoulli
mean, log-normal tail, poisson inter-arrival).

## Next

Phase 1.2 (SSO E2E), 1.3 (trace↔log round-trip), 1.4 (cross-service
smoke) depend on this running continuously in the target environment —
with the generator pointed at `shop.<your-domain>`, the rest of the
observability plumbing has inputs to verify against.
