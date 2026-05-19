# Requirements: OCTO APM Demo

**Defined:** 2026-05-14
**Core Value:** Every demo user action must produce inspectable, correlated OCI
observability evidence across browser, application, payment gateway, Java
sidecar, database, logs, traces, metrics, security, and GenAI where relevant.

## Current Requirements

### User Journeys

- [x] **JOURNEY-01**: Customer can log in, browse drones, add items to cart,
  checkout, and see a successful order confirmation.
- [x] **JOURNEY-02**: Customer checkout exposes copyable evidence for Trace ID,
  Order ID, Payment Gateway Request ID, payment status, gateway steps, APM
  saved query, Log Analytics search, and security triage search.
- [x] **JOURNEY-03**: Admin user can inspect users, orders, catalog data, DB
  cleanup actions, and related observability pivots from the Admin site.
- [x] **JOURNEY-04**: Login and admin actions appear in RUM, backend spans,
  structured logs, ATP/database evidence, and Log Analytics user/order pivots.

### Payment Simulation

- [x] **PAY-01**: Google Pay and Apple Pay flows are fully simulated with wallet,
  tokenization, gateway verification, authorization, processor response, and
  settlement-like steps.
- [x] **PAY-02**: Card flows simulate Visa and Mastercard gateways, including
  success, decline, timeout, and controlled error paths.
- [x] **PAY-03**: Payment telemetry is token-safe and never stores or logs real
  PAN, CVV, wallet secrets, or provider credentials.
- [x] **PAY-04**: Successful purchases produce a complete flow from browser to
  Shop, Java sidecar, payment rail, backend, CRM sync, and ATP.

### Observability Contract

- [x] **OBS-01**: Every service emits trace and span identifiers on spans and
  structured logs using the project correlation contract.
- [x] **OBS-02**: Logs promote existing Log Analytics fields for service,
  namespace, trace, span, workflow, user, order, payment, gateway, security, and
  database pivots before introducing new fields.
- [x] **OBS-03**: APM saved queries and drilldowns exist for checkout, payment
  gateway, Java sidecar, login/auth, DB slowness, service errors, GenAI, and
  platform workflows.
- [x] **OBS-04**: Log Analytics saved searches, dashboards, and scheduled
  detection rules run without query-format errors and are backed by real logs.
- [x] **OBS-05**: OCI Monitoring custom metrics use the shared
  `octo_apm_demo` namespace and support app, OKE, payment, and completeness
  checks.

### Deployment Parity

- [x] **DEPLOY-01**: VM, OKE, container, and local-stack deployment paths use
  consistent image tags, service names, environment variables, health checks,
  and observability configuration.
- [x] **DEPLOY-02**: OKE services send APM traces and Kubernetes logs to the
  same APM domain and Log Analytics contract as VM services.
- [x] **DEPLOY-03**: Public LB routing can round-robin across VM and OKE
  backends without breaking customer or admin flows.
- [x] **DEPLOY-04**: Deployment scripts remain idempotent, non-destructive, and
  scoped to OCTO demo resources unless explicitly approved otherwise.

### Security and Governance

- [x] **SEC-01**: Security simulation emits MITRE-style, payment-risk, edge,
  host, OKE, and database fields that Log Analytics detection rules can use.
- [x] **SEC-02**: Customer-facing pages describe the shop as a fake demo and do
  not expose backend internals.
- [x] **SEC-03**: OCI Coordinator is available only from Admin and only answers
  octo-apm-demo resource questions.
- [x] **SEC-04**: Public docs, diagrams, logs, and examples do not expose real
  secrets, OCIDs, IPs, wallet paths, or credential material.

### GenAI and Admin Assistant

- [x] **AI-01**: Shop/Admin AI Assistant capability uses OCI instance principal
  authentication where required in OCI and reports Langfuse/LLMetry status.
- [x] **AI-02**: GenAI requests emit APM spans, LLM telemetry, safe prompt
  metadata, Langfuse correlation, and Log Analytics pivots without leaking
  sensitive prompt or credential data.
- [x] **AI-03**: Admin assistant answers are grounded in OCTO APM demo pages,
  resources, traces, logs, and docs.

### Documentation and Architecture

- [x] **DOC-01**: Architecture diagrams remain layered, editable, sanitized, and
  aligned with the implementation.
- [x] **DOC-02**: Deployment docs cover VM, OKE, container, and local-stack
  flows with consistent validation steps.
- [x] **DOC-03**: Troubleshooting docs include APM-to-Log-Analytics searches,
  saved queries, dashboard checks, and common connector/collector failures.

### Scale and Elasticity

- [x] **SCALE-01**: HPA expansion covers shop, crm, and java-apm services with
  CPU + memory targets; the D-05 RPS metric is gated behind a nested Helm flag
  (`autoscaling.rps.enabled`) that defaults to `false`, so the legacy
  `helm template` output is bit-identical until an operator opts in. CRM HPA
  remains untouched (D-01).
- [x] **SCALE-02**: The OKE Cluster Autoscaler add-on is configurable through
  an idempotent, dry-run-by-default operator script
  (`deploy/oke/configure-cluster-autoscaler.sh`); a sibling
  `prometheus-adapter` Helm values file publishes `shop_request_rate` and
  `java_request_rate` as External Metrics for the optional custom-metric HPA
  path (default off).
- [x] **SCALE-03**: An admin-only `/admin/stress-test` UI on
  `admin.${DNS_DOMAIN}` exposes a FastAPI router with Pydantic-validated
  apply/clear/state endpoints, a three-channel MELTS audit (OTel span +
  Log Analytics `push_log` + OCI Monitoring `octo_apm_demo/stress_run_count`
  point) keyed by `run_id`, host-bound + OCTO scope enforcement, and a
  k6-based load-generator pod authenticated by `X-Internal-Service-Key`
  cross-service auth.
- [x] **SCALE-04**: APM saved queries, OCI Monitoring custom metrics in the
  `octo_apm_demo` namespace + alarm definitions, Log Analytics OKE Monitoring
  saved searches, and a published autoscaling dashboard are captured via
  existing apply tooling. No live OCI calls run in unit tests; only offline
  contract tests per VALIDATION.md Dimension 8.

## Deferred Requirements

- **FUTURE-01**: Full production multi-tenancy beyond the OCTO demo scope.
- **FUTURE-02**: Real payment provider integration.
- **FUTURE-03**: Automated Terraform apply for shared emdemo changes.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real payment capture | This is an observability demo and must remain safe for workshops. |
| Customer access to OCI Coordinator | Coordinator is an Admin-only operations surface. |
| Public tenancy identifiers | Public docs must remain portable and secret-safe. |
| Non-OCTO resource automation | User explicitly scoped changes to OCTO demo resources. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| JOURNEY-01, JOURNEY-02, JOURNEY-04 | Phase 2 | Complete |
| JOURNEY-03 | Phase 5 | Complete |
| PAY-01, PAY-02, PAY-03, PAY-04 | Phase 2 | Complete |
| OBS-01, OBS-02, OBS-03, OBS-05 | Phase 1 | Complete |
| OBS-04, SEC-01 | Phase 3 | Complete |
| DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04 | Phase 4 | Complete |
| SEC-02, SEC-03, SEC-04 | Phase 5 | Complete |
| AI-01, AI-02, AI-03 | Phase 5 | Complete |
| DOC-01, DOC-02, DOC-03 | Phase 6 | Complete |
| SCALE-01 | Phase 7 | Planned |
| SCALE-02 | Phase 7 | Planned |
| SCALE-03 | Phase 7 | Planned |
| SCALE-04 | Phase 7 | Planned |

**Coverage:**
- Current requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-05-14*
*Last updated: 2026-05-18 — added SCALE-01..04 for Phase 7 OKE Autoscaling and Stress Demo.*
