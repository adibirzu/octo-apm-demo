# OCTO Drone Shop

ATP-backed drone commerce platform with full OCI observability, IDCS SSO, cross-service CRM integration, chaos engineering, and automated remediation.

**Deployment profile:** Shop storefront on OKE with shared-DB CRM integration

## What is in this repo

### Application
- **Oracle ATP** backend for products, customers, carts, orders, shipments, page views, workflows, and AI assistant conversations.
- **Go workflow gateway** for backend workflow menus, scheduled ATP query sweeps, query-lab probes, and Select AI execution paths.
- **IDCS OIDC SSO** (Authorization Code + PKCE) with JWKS-verified ID tokens (RS256). SSO users auto-provisioned; password users coexist.
- **Cross-service CRM integration** — bidirectional customer/order sync with the companion CRM service via W3C `traceparent`-propagated distributed traces.

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
export DNS_DOMAIN="<your-domain>"
# → shop.<your-domain> (shop URL, CORS, SSO callback)
# → crm.<your-domain> (CRM URL, customer sync)
# → All IDCS redirect URIs auto-derived
# → All CORS origins auto-derived
```

No tenancy OCIDs, regions, or hostnames are hardcoded in the codebase.

### Deployment paths

| Path | Artifact | When to use |
|---|---|---|
| OKE (Kubernetes) | `deploy/k8s/*.yaml` + `deploy/deploy.sh` | Production / HA |
| OCI Resource Manager stack | `deploy/resource-manager/` | Console-driven one-click observability + WAF bootstrap |
| Unified single VM | `deploy/vm/` | Demos, workshops, air-gapped |

Full matrix in [site/getting-started/deployment-options.md](site/getting-started/deployment-options.md).

### Bill of Materials

The complete, minimal list of tenancy resources, secrets, CLIs, and
images needed to redeploy from a blank slate lives in
**[deploy/BOM.md](deploy/BOM.md)**. `pre-flight-check.sh`,
`init-tenancy.sh`, and the Resource Manager schema all validate
against it — if they disagree, the BOM wins and the mismatch is a
bug to raise.

### New tenancy bootstrap workflow

| Step | Script | Purpose |
|---|---|---|
| 1 | `deploy/pre-flight-check.sh` | Validates required env vars, detects placeholder leaks (`example.cloud` etc.), checks CLI tools + kubectl context |
| 2 | `deploy/init-tenancy.sh` | Idempotent bootstrap: OCIR repo, K8s namespace, initial Secrets (`octo-auth`, `octo-atp`), `terraform init` |
| 3 | `deploy/oci/ensure_apm.sh --apply` | Provisions OCI APM Domain + RUM Web Application; emits `export OCI_APM_*` for Secret population |
| 4 | `python3 tools/create_la_source.py --apply` | Registers Log Analytics source `octo-shop-app-json` + JSON parser for trace-correlated search |
| 5 | `deploy/oci/ensure_stack_monitoring.sh` (DRY_RUN=false) | Registers the ATP as a Stack Monitoring MonitoredResource |
| 6 | `deploy/deploy.sh` | Build + push + OKE rollout |

Full walkthrough: [site/getting-started/new-tenancy.md](site/getting-started/new-tenancy.md).

### Secrets

Two supported modes:

1. **Plain Kubernetes Secrets** — created by `deploy/init-tenancy.sh`. Simplest; fine for demos.
2. **OCI Vault via Secrets Store CSI Driver** — template at
   [deploy/k8s/secret-provider-class.yaml](deploy/k8s/secret-provider-class.yaml).
   Mounts Vault secrets as files; the app already supports `*_FILE` variants
   for every secret via `server/config.py::_env_secret`.

### Cross-service integration contract

- Preferred env var name: `SERVICE_CRM_URL` (legacy alias: `ENTERPRISE_CRM_URL` — emits a deprecation warning on startup).
- Required header on all cross-service calls: `X-Internal-Service-Key: $INTERNAL_SERVICE_KEY`.
- Order sync payloads carry `idempotency_token` + `source_system` + `source_order_id` for CRM-side dedup.
- Machine-readable contract exposed at `GET /api/integrations/schema` (OpenAPI 3.1 subset).

## Documentation

| Document | What it covers |
|---|---|
| [docs/install-guide.md](docs/install-guide.md) | Full install guide with standalone quickstart (§1b), ATP, APM, SSO, OKE |
| [docs/observability-enhancement-plan.md](docs/observability-enhancement-plan.md) | Sequential roadmap for complex flows, APM, Logging, Log Analytics, drilldowns, and DB tooling |
| [deploy/credentials.template](deploy/credentials.template) | Secret-only deployment template for env or `*_FILE` based secret injection |
| [docs/technical-architecture.md](docs/technical-architecture.md) | Runtime topology, data model, trace coverage, observability stack |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System diagram + database ERD |
| [deploy/k8s/deployment.yaml](deploy/k8s/deployment.yaml) | OKE deployment (envsubst-templated) |
| [deploy/oci/ensure_monitoring.sh](deploy/oci/ensure_monitoring.sh) | OCI Monitoring alarms + health checks + notifications |
| [deploy/oci/ensure_apm.sh](deploy/oci/ensure_apm.sh) | APM Domain + RUM Web Application provisioning (plan/apply/print) |
| [deploy/oci/ensure_stack_monitoring.sh](deploy/oci/ensure_stack_monitoring.sh) | Register ATP as Stack Monitoring MonitoredResource |
| [deploy/pre-flight-check.sh](deploy/pre-flight-check.sh) | Env + placeholder + tooling pre-flight |
| [deploy/init-tenancy.sh](deploy/init-tenancy.sh) | Idempotent new-tenancy bootstrap |
| [tools/create_la_source.py](tools/create_la_source.py) | Log Analytics source + JSON parser registrar |
| [site/getting-started/new-tenancy.md](site/getting-started/new-tenancy.md) | End-to-end new-tenancy playbook |

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
| `ENTERPRISE_CRM_URL` | Optional | Backend CRM URL for server-to-server integration; may be internal/private |
| `CRM_PUBLIC_URL` | Recommended | Public CRM browser URL, for example `https://crm.<your-domain>` |
| `WORKFLOW_PUBLIC_API_BASE_URL` | Optional | Public workflow gateway URL for browser access when `WORKFLOW_API_BASE_URL` is private |

## Quick start

```bash
# Local dev
cp .env.local.example .env.local
cp deploy/credentials.template deploy/credentials.env
docker compose up --build

# Any OCI tenancy
export DNS_DOMAIN="<your-domain>"
export AUTH_TOKEN_SECRET="$(openssl rand -hex 32)"
export CRM_PUBLIC_URL="https://crm.${DNS_DOMAIN}"
# Set ATP + APM env vars...
envsubst < deploy/k8s/deployment.yaml | kubectl apply -f -
```

## Testing

```bash
# E2E (237 tests)
npm run test:e2e

# Against live tenancy
SHOP_URL=https://shop.<your-domain> CRM_URL=https://crm.<your-domain> npm run test:e2e

# k6 stress tests
k6 run --env DNS_DOMAIN=<your-domain> k6/cross_service_stress.js
k6 run --env DNS_DOMAIN=<your-domain> --env PROFILE=heavy k6/db_stress.js
```

## OCI observability stack

| Layer | Service | How to verify |
|---|---|---|
| Traces | OCI APM | APM → Trace Explorer → filter `serviceName=octo-drone-shop` |
| Topology | OCI APM | APM → Topology → CRM ↔ Shop ↔ ATP ↔ IDCS edges |
| RUM | OCI APM | APM → Real User Monitoring → Session Explorer (add-to-cart, checkout events) |
| Logs | OCI Logging + Log Analytics | Log Analytics → search `oracleApmTraceId=<trace_id>` |
| Metrics | OCI Monitoring | Monitoring → Metric Explorer → namespace `octo_drone_shop` |
| Alarms | OCI Monitoring | Monitoring → Alarms (error-rate, db-latency, health-down, crm-sync) |
| DB | OCI DB Management | DB Management → Performance Hub → SQL Monitor |
| DB insights | OCI Operations Insights | OPSI → SQL Warehouse → filter by `MODULE=octo-drone-shop` |
| Security | OCI WAF | WAF → Logs (detection mode on LB) |
| Health | OCI Health Checks | Health Checks → HTTP Monitors → `/ready` |

## Enhancement roadmap

The recommended rollout order is:

1. Instrument the golden business flows: checkout, CRM sync, AI assistant, and
   simulated faults.
2. Validate those flows in OCI APM Trace Explorer and Topology.
3. Land structured logs in OCI Logging and route them into Log Analytics.
4. Publish drilldowns from APM traces to Log Analytics and DB tools.
5. Enable Database Management and Operations Insights for ATP and verify SQL
   visibility.

See [docs/observability-enhancement-plan.md](docs/observability-enhancement-plan.md)
for the detailed workstreams, acceptance criteria, and documentation scope.

## Optional platform automation

If you wrap this repo with a higher-level deployment pipeline, that automation should inject the same runtime inputs described above. Typical responsibilities are:
- Derive `AUTH_TOKEN_SECRET` and `INTERNAL_SERVICE_KEY` from the deployment secret source
- Inject `DNS_DOMAIN` into ConfigMap or secret-backed runtime config
- Wire IDCS SSO if `IDCS_DOMAIN_URL` / `IDCS_CLIENT_ID` / `IDCS_CLIENT_SECRET` are set
- Create the APM domain, OCI Logging resources, WAF policy, and health checks
- Pass `INTERNAL_SERVICE_KEY` to the CRM control surface for the simulation proxy

For manual deployments, keep non-secret settings in `.env.local` or `deploy/env.template`, and keep secrets in `deploy/credentials.env` derived from [deploy/credentials.template](deploy/credentials.template) or mounted `*_FILE` secrets.

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
