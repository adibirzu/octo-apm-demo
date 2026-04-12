# Enterprise CRM Portal

Cloud-native CRM application built for **OCI Observability** demonstration. Showcases APM, Stack Monitoring, Logging, Log Analytics, Operations Insights, and DB Management integration as modular add-ons.

**OCI-DEMO Component: C27** — Enterprise CRM Portal (OKE)

## Architecture

```
                                +------------------+
    Users ──────────────────────│  OCI Load        │
                                │  Balancer        │
                                +--------+---------+
                                         |
                                +--------v---------+
                                |  FastAPI App      |
                                |  (Port 8080)      |
                                |                   |
                                |  - 12 CRM modules |
                                |  - 73 API routes  |
                                |  - 8+ spans/req   |
                                |  - RUM injection  |
                                +--------+---------+
                                         |
                                +--------v---------+
                                |  Oracle ATP       |
                                |  (shared w/ Shop) |
                                +-------------------+

    OCI Observability (modular add-ons):
    ├── OCI APM ──────────── Traces, Topology, Trace Explorer
    ├── OCI APM RUM ──────── Real User Monitoring
    ├── OCI Logging ──────── Structured logs → Log Analytics
    ├── OCI Monitoring ───── Custom metrics + Alarms
    ├── Stack Monitoring ─── Application topology + health
    ├── DB Management ────── Performance Hub, SQL Monitor
    ├── Ops Insights ─────── SQL Warehouse, capacity planning
    └── Prometheus ────────── /metrics endpoint (always on)
```

## OCI Observability Add-Ons

Each observability service is **independently activatable** — deploy the app first, enable observability later. No code changes required.

| Add-On | Env Vars to Set | What You Get |
|--------|----------------|--------------|
| **APM (Traces)** | `OCI_APM_ENDPOINT`, `OCI_APM_PRIVATE_DATAKEY` | 8+ spans/request, distributed traces, topology |
| **APM (RUM)** | `OCI_APM_RUM_ENDPOINT`, `OCI_APM_RUM_PUBLIC_DATAKEY` | Browser performance, session explorer |
| **Logging** | `OCI_LOG_ID`, `OCI_LOG_GROUP_ID` | Structured JSON logs with trace correlation |
| **Log Analytics** | Enable via OCI Console on log group | Search by `oracleApmTraceId`, saved searches |
| **Stack Monitoring** | Enable via OCI Console | Application topology, health dashboard |
| **DB Management** | `ensure_db_observability.sh` | Performance Hub, SQL Monitor, AWR |
| **Ops Insights** | `ensure_db_observability.sh` | SQL Warehouse, capacity planning |
| **Monitoring** | `OCI_COMPARTMENT_ID` | Custom metrics, alarms, health checks |
| **Prometheus** | Always enabled | `/metrics` endpoint for Grafana |
| **Splunk HEC** | `SPLUNK_HEC_URL`, `SPLUNK_HEC_TOKEN` | External SIEM forwarding |

### Minimal Deploy (No Observability)

```bash
# Works with just database — all observability is optional
export ORACLE_DSN="myatp_low"
export ORACLE_PASSWORD="<password>"
docker compose up -d
```

### Full Observability Deploy

```bash
# Add observability progressively
export OCI_APM_ENDPOINT="https://<apm-endpoint>"
export OCI_APM_PRIVATE_DATAKEY="<key>"
export OCI_LOG_ID="ocid1.log...."
export OCI_COMPARTMENT_ID="ocid1.compartment...."
# Restart — observability activates automatically
```

## CRM Modules (12)

| Module | Prefix | Routes | Functionality |
|--------|--------|--------|---------------|
| `auth` | `/api/auth` | 7 | Login, register, session, SSO (IDCS OIDC + PKCE) |
| `customers` | `/api/customers` | 4 | Customer CRUD with search and filter |
| `orders` | `/api/orders` | 6 | Order management, backlog tracking, external sync |
| `products` | `/api/products` | 3 | Product catalog management |
| `invoices` | `/api/invoices` | 4 | Invoicing, PDF generation, payment |
| `tickets` | `/api/tickets` | 4 | Support ticket management |
| `reports` | `/api/reports` | 3 | Custom report builder |
| `files` | `/api/files` | 5 | File upload/download management |
| `admin` | `/api/admin` | 6 | User management, audit logs, config |
| `campaigns` | `/api/campaigns` | 6 | Campaign + lead management |
| `shipping` | `/api/shipping` | 6 | Shipment tracking, warehouse management |
| `analytics` | `/api/analytics` | 6 | Overview, geo, funnel, revenue |
| `simulation` | `/api/simulate` | 15+ | Chaos engineering, data generation |
| `integrations` | `/api/integrations` | 6 | Cross-service topology, health probes |
| `observability` | `/api/observability` | 6 | 360 dashboard, console URLs |

## Trace Depth (8+ Spans per Request)

```
middleware.entry ─── IP, user-agent, URL
  ├── auth.check ─── session/token validation
  ├── request.validate ─── content type, WAF headers
  ├── {module}.{action} ─── route handler (auto-instrumented)
  │   └── db.query.* ─── SQLAlchemy (auto) + SQL_ID
  ├── ATTACK:{TYPE} ─── security span (if detected)
  └── response.finalize ─── status code, duration, correlation_id
```

## Cross-Service Integration

Integrates with [OCTO Drone Shop](https://github.com/adibirzu/octo-drone-shop) via:
- **Order sync** — one-way sync (Shop → CRM) with audit trail
- **Distributed traces** — W3C `traceparent` propagation
- **Shared ATP** — same Oracle ATP instance, session-tagged for OPSI
- **Simulation proxy** — cross-service chaos engineering

## Quick Start

```bash
git clone https://github.com/adibirzu/enterprise-crm-portal.git
cd enterprise-crm-portal
cp .env.example .env
docker compose up -d
open http://localhost:8080
```

## Load Testing (k6)

```bash
k6 run --env BASE_URL=http://localhost:8080 k6/load_test.js
```

3 scenarios: user browsing (ramp 1→25 VUs), API throughput (20 req/s), security probes.

## Chaos Engineering

```bash
# Toggle DB latency, error rate, slow queries
curl -X POST http://localhost:8080/api/simulate/configure \
  -H 'Content-Type: application/json' \
  -d '{"db_latency": true, "error_rate": 0.3}'

# Reset
curl -X POST http://localhost:8080/api/simulate/reset
```

## Security Testing Add-On

> **Optional module** — the CRM includes intentional OWASP Top 10 vulnerabilities for security training and detection testing. These are disabled by default in production and can be enabled for security workshops.

When enabled, security probes generate `ATTACK:{TYPE}` spans with MITRE ATT&CK classification, visible in OCI APM Trace Explorer. See [Security Testing Guide](docs/security-testing.md) for details.

## Kubernetes Deployment

```bash
kubectl apply -f deploy/k8s/deployment.yaml       # Standard
kubectl apply -f deploy/k8s/deployment-atp.yaml    # ATP-backed
```

## Documentation

| Document | Coverage |
|----------|----------|
| [Platform Docs](https://adibirzu.github.io/octo-drone-shop/) | Full platform documentation (both repos) |
| [OCI Observability Add-Ons](https://adibirzu.github.io/octo-drone-shop/observability/) | How to enable each OCI service |
| [Database Integration](https://adibirzu.github.io/octo-drone-shop/architecture/database-integration/) | Shared ATP architecture |
| [Security Testing Guide](docs/security-testing.md) | Optional OWASP vulnerability testing |

## Project Structure

```
enterprise-crm-portal/
├── server/
│   ├── main.py              # FastAPI app (73 routes, 12 modules)
│   ├── config.py            # Environment configuration
│   ├── database.py          # SQLAlchemy ORM + async engine
│   ├── order_sync.py        # External order sync (Drone Shop)
│   ├── modules/             # 12+ CRM modules
│   ├── middleware/           # 5 middleware layers
│   ├── observability/       # OTel + OCI APM + Logging SDK
│   ├── templates/           # Jinja2 HTML (RUM injection)
│   └── static/              # CSS + JS + product images
├── deploy/
│   ├── k8s/                 # Kubernetes manifests
│   └── observability/       # OTel Collector, SLO rules
├── k6/                      # Load testing (3 suites)
├── docs/                    # Additional documentation
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # App + PostgreSQL
└── requirements.txt
```

---

## Observability + Security v2 (wave 1 + 2)

Additive enhancement layer shared with the Octo Drone Shop and the OCI
Coordinator. The CRM is the **sole controller** of chaos scenarios — the
Shop has zero write endpoints.

### What changed

* **Workflow-aware logs + traces** — same contract as the shop:
  `trace_id`, `span_id`, `request_id`, `workflow_id`, `workflow_step`.
* **Chaos admin surface** — `/admin/chaos` (role: `chaos-operator`).
  Presets, TTL-bounded apply, clear, and an audit log consumed by the
  `octo-chaos-audit` Log Analytics parser.
* **Security headers** — HSTS, CSP nonce, `X-Frame-Options` allowing
  the ops portal (via `OPS_DOMAIN`) to embed the admin page.
* **WAF + LA pipelines** — same Terraform module as the shop, via
  `deploy/env.template` and the root-stack variables.
* **CI gates** — `.github/workflows/security-gates.yml`.

### Replicate in your tenancy

Same steps as the Shop README — the two apps share `deploy/env.template`
schema and the same Terraform variables. Set `CHAOS_ADMIN_ROLE` if you
want a different IDCS role name than the default (`chaos-operator`).

### Safe defaults

- `CHAOS_ENABLED=false`
- `WAF_MODE=DETECTION`
- `AUTOREMEDIATE_ENABLED=false`

Further detail: `docs/observability-v2/` (mkdocs nav).
