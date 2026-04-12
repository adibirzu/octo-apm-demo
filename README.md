# OCTO Drone Shop

ATP-backed drone commerce platform with full OCI observability, IDCS SSO, cross-service CRM integration, chaos engineering, and automated remediation.

**OCI-DEMO Component: C28** — Drone Shop Portal (OKE)

## What is in this repo

### Application
- **Oracle ATP** backend for products, customers, carts, orders, shipments, page views, workflows, and AI assistant conversations.
- **Go workflow gateway** for backend workflow menus, scheduled ATP query sweeps, query-lab probes, and Select AI execution paths.
- **IDCS OIDC SSO** (Authorization Code + PKCE) with JWKS-verified ID tokens (RS256). SSO users auto-provisioned; password users coexist.
- **Cross-service CRM integration** — bidirectional customer/order sync with enterprise-crm-portal via W3C traceparent-propagated distributed traces.

### Observability (MELTS)
- **Metrics** — Prometheus `/metrics` + OCI Monitoring custom metrics (app.health, error rate, checkout count, DB latency, CRM sync age)
- **Events** — OCI Alarms on error rate, DB latency, health-down, CRM sync staleness; OCI Notifications delivery
- **Logs** — OCI Logging SDK with `oracleApmTraceId` correlation; Splunk HEC; structured JSON with trace/span/correlation IDs
- **Traces** — OCI APM via OpenTelemetry (50+ custom spans across 13 modules); SQLAlchemy + httpx + logging auto-instrumentation; Oracle session tagging for DB Management/OPSI drill-down
- **Security** — 19 MITRE ATT&CK security span types with OWASP codes; WAF detection mode; rate limiting

### Frontend
- **RUM** — OCI APM Real User Monitoring with custom events: add-to-cart, checkout funnel (start/complete/error), search, page load timing
- **Shop UI** — product grid, cart, checkout, dealer locations, workflow panels, Select AI, query lab

### Testing
- **E2E** — 237 Playwright tests across 8 dimensions (health, shopping, cross-service, MELTS, auth, simulation, availability, k6)
- **k6 stress tests** — 3 suites (shop-only, cross-service, ATP database) with light/moderate/heavy profiles
- **OCI Health Checks** — HTTP `/ready` probe every 30s

### Infrastructure
- **Chaos engineering** — simulation controls (error burst, DB latency, slow responses, DB disconnect) gated behind IDCS SSO + internal service key; controlled from CRM portal
- **Tenancy portable** — single `DNS_DOMAIN` variable derives all URLs, CORS, SSO redirects
- **OKE deployment** — K8s manifests with `envsubst` templating, no hardcoded OCIDs

## Tenancy portability

Set **one variable** and everything derives:

```bash
export DNS_DOMAIN="yourcompany.cloud"
# → shop.yourcompany.cloud (shop URL, CORS, SSO callback)
# → crm.yourcompany.cloud (CRM URL, customer sync)
# → All IDCS redirect URIs auto-derived
# → All CORS origins auto-derived
```

No tenancy OCIDs, regions, or hostnames are hardcoded in the codebase.

## Documentation

| Document | What it covers |
|---|---|
| [docs/install-guide.md](docs/install-guide.md) | Full install guide with standalone quickstart (§1b), ATP, APM, SSO, OKE |
| [docs/technical-architecture.md](docs/technical-architecture.md) | Runtime topology, data model, trace coverage, observability stack |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System diagram + database ERD |
| [deploy/k8s/deployment.yaml](deploy/k8s/deployment.yaml) | OKE deployment (envsubst-templated) |
| [deploy/oci/ensure_monitoring.sh](deploy/oci/ensure_monitoring.sh) | OCI Monitoring alarms + health checks + notifications |

## Key files

| File | Purpose |
|---|---|
| `server/main.py` | FastAPI app entry — 98 routes, middleware stack, lifespan |
| `server/modules/sso.py` | IDCS OIDC + PKCE + JWKS verification (382 lines) |
| `server/modules/simulation.py` | Chaos controls (SSO + service key auth) |
| `server/auth_security.py` | Bearer token HMAC, strict secret validation, SSO/service-key auth |
| `server/observability/otel_setup.py` | OTel init (shared lib + standalone), SQLAlchemy/httpx instrumentation |
| `server/observability/oci_monitoring.py` | OCI Monitoring custom metrics publisher |
| `server/observability/security_spans.py` | 19 MITRE ATT&CK security span types |
| `services/workflow-gateway/` | Go workflow gateway (Select AI, query lab, ATP sweeps) |
| `k6/cross_service_stress.js` | k6: Shop + CRM + ATP distributed trace stress test |
| `k6/db_stress.js` | k6: ATP database stress (writes, N+1, slow queries, checkout storms) |
| `tests/e2e/` | 237 Playwright E2E tests (8 spec files) |

## Required production inputs

| Variable | Required | What it does |
|---|---|---|
| `DNS_DOMAIN` | Yes | All public URLs, CORS, SSO redirects derive from this |
| `AUTH_TOKEN_SECRET` | Yes (prod) | Bearer token signing key. Auto-generated in dev with warning. |
| `ORACLE_DSN` | Yes | ATP TNS alias (e.g. `myatp_low`) |
| `ORACLE_PASSWORD` | Yes | ATP admin password |
| `ORACLE_WALLET_DIR` | Yes | Path to ATP wallet (mounted in K8s) |
| `OCI_APM_ENDPOINT` | Recommended | OCI APM data upload endpoint |
| `OCI_APM_PRIVATE_DATAKEY` | Recommended | APM private data key for trace export |
| `OCI_COMPARTMENT_ID` | Recommended | Target compartment for OCI Monitoring custom metrics |
| `IDCS_DOMAIN_URL` | Optional | OCI IAM Identity Domain URL for SSO |
| `IDCS_CLIENT_ID` | Optional | IDCS Confidential App client ID |
| `IDCS_CLIENT_SECRET` | Optional | IDCS Confidential App client secret |
| `INTERNAL_SERVICE_KEY` | Optional | CRM→Shop service-to-service simulation proxy key |
| `ENTERPRISE_CRM_URL` | Optional | CRM portal URL for cross-service integration |

## Quick start

```bash
# Local dev
cp .env.local.example .env.local
docker compose up --build

# Any OCI tenancy
export DNS_DOMAIN="mytenancy.cloud"
export AUTH_TOKEN_SECRET="$(openssl rand -hex 32)"
# Set ATP + APM env vars...
envsubst < deploy/k8s/deployment.yaml | kubectl apply -f -
```

## Testing

```bash
# E2E (237 tests)
npm run test:e2e

# Against live tenancy
SHOP_URL=https://shop.mytenancy.cloud CRM_URL=https://crm.mytenancy.cloud npm run test:e2e

# k6 stress tests
k6 run --env DNS_DOMAIN=mytenancy.cloud k6/cross_service_stress.js
k6 run --env DNS_DOMAIN=mytenancy.cloud --env PROFILE=heavy k6/db_stress.js
```

## OCI observability stack

| Layer | Service | How to verify |
|---|---|---|
| Traces | OCI APM | APM → Trace Explorer → filter `serviceName=octo-drone-shop-oke` |
| Topology | OCI APM | APM → Topology → CRM ↔ Shop ↔ ATP ↔ IDCS edges |
| RUM | OCI APM | APM → Real User Monitoring → Session Explorer (add-to-cart, checkout events) |
| Logs | OCI Logging + Log Analytics | Log Analytics → search `oracleApmTraceId=<trace_id>` |
| Metrics | OCI Monitoring | Monitoring → Metric Explorer → namespace `octo_drone_shop` |
| Alarms | OCI Monitoring | Monitoring → Alarms (error-rate, db-latency, health-down, crm-sync) |
| DB | OCI DB Management | DB Management → Performance Hub → SQL Monitor |
| DB insights | OCI Operations Insights | OPSI → SQL Warehouse → filter by `MODULE=octo-drone-shop` |
| Security | OCI WAF | WAF → Logs (detection mode on LB) |
| Health | OCI Health Checks | Health Checks → HTTP Monitors → `/ready` |

## OCI-DEMO integration (C28)

When deployed as part of OCI-DEMO, the `c28_deploy_drone_shop.sh` script handles everything automatically:
- Derives `AUTH_TOKEN_SECRET` and `INTERNAL_SERVICE_KEY` from ATP password
- Injects `DNS_DOMAIN` into ConfigMap
- Wires IDCS SSO if `IDCS_DOMAIN_URL` / `IDCS_CLIENT_ID` / `IDCS_CLIENT_SECRET` are set
- Creates dedicated APM domain, OCI Logging resources, WAF policy, and health checks
- The CRM portal (C27) gets `INTERNAL_SERVICE_KEY` for the simulation proxy

```bash
python deploy.py c28  # deploys everything
```

## Autoremediation (OCI Coordinator)

The OCI Coordinator's **Remediation Agent v2** can scan this app's OCI services for errors, correlate with APM traces and logs, consult the LLM for diagnosis, generate runbooks, and optionally execute fixes:

```
User: "Check for issues and create runbooks"
→ Scans Cloud Guard, VSS, Data Safe, Audit
→ Correlates with APM traces
→ LLM diagnosis + proposed commands
→ Structured runbooks (troubleshoot → fix → rollback → verify)
→ Human approval gate (or YOLO mode for sandbox)
→ Execute via SSH / kubectl / OCI CLI
→ Verify fix
```

---

## Observability + Security v2 (wave 1 + 2)

Additive enhancement layer — existing capabilities unchanged, all new behavior
guarded by feature flags in `deploy/env.template`.

### What changed

* **Unified correlation contract** — every request carries `trace_id`,
  `span_id`, `request_id`, `workflow_id`, `workflow_step`. Logs are
  stamped by `server/observability/log_enricher.py` so Log Analytics
  can join Shop ↔ CRM ↔ DB ↔ WAF along any of those keys.
* **Workflow middleware** — `server/observability/workflow_context.py`
  maps URL → logical workflow (`browse-catalog`, `checkout`,
  `crm-lead-capture`, …). OTel spans and logs are tagged.
* **Security headers + request id** — `server/security/headers.py`,
  `server/security/request_id.py` attach HSTS, CSP nonce,
  X-Request-Id to every response.
* **Chaos — reader only on Shop.** Control surface lives on CRM
  (`/admin/chaos`) and the Ops portal. Shop exposes only
  `GET /api/chaos/state` + `/api/chaos/presets`. See
  `server/chaos/` for details.
* **SQLAlchemy fault hooks** — `server/chaos/db_faults.py` injects
  slow queries, deadlocks, and pool holds inside existing DB spans
  so APM sees the faults as first-class events.
* **WAF in DETECTION mode** — `deploy/terraform/modules/waf/` creates
  one policy per frontend with OWASP CRS, admin-CIDR guard, login
  rate limit. Flip `waf_mode = BLOCK` after a 7-day soak.
* **Log Analytics v2** — parsers, saved searches, and the Workflow
  Command Center dashboard in `deploy/oci/log_analytics/`.
* **CI security gates** — `.github/workflows/security-gates.yml`
  runs bandit, pip-audit, ruff (S-rules), semgrep (OWASP),
  gitleaks, tflint, trivy.

### Replicate in your tenancy

1. Copy `deploy/env.template` → `.env` and fill **every** OCID.
2. `cd deploy/terraform && cp terraform.tfvars.example terraform.tfvars`
   and fill variables.
3. `terraform init && terraform apply` — creates WAF + log pipelines.
4. Upload Log Analytics parsers:
   ```bash
   for p in deploy/oci/log_analytics/parsers/*.json; do
     oci log-analytics parser upload \
       --namespace-name "$OCI_LA_NAMESPACE" --from-json "file://$p"
   done
   ```
5. Helm install / `kubectl apply` the app — the middleware auto-enables
   when the new env vars are present. `CHAOS_ENABLED=false` by default.

### Verifying end-to-end

```bash
scripts/demo/full_workflow.sh        # applies chaos via CRM, runs k6,
                                     # polls Log Analytics + Coordinator
```

Further detail: `docs/observability-v2/` (mkdocs nav).
