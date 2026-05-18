---
title: Architecture
---

# Architecture

`octo-apm-demo` is an end-to-end reference platform for Oracle Cloud Infrastructure (OCI) Observability. It is a working, multi-tier system — a storefront, a back-office, a Java app-server tier, a payment gateway emulator, a workflow gateway, several support services, and an Oracle Autonomous Database — wired together with a single correlation contract that makes traces, metrics, logs, and RUM events join on the same identifiers across every hop.

This document describes the platform as built. It is intended for architects, SREs, observability engineers, and anyone evaluating how to drive APM, Logging, Logging Analytics, Monitoring, Stack Monitoring, and Service Connector Hub from a real workload rather than from synthetic samples.

---

## A. Platform Overview

At the highest level the platform is a layered web stack with three application tiers, one database tier, and one observability fabric that wraps everything:

- **Storefront tier** — public storefront where customers browse, log in, and check out (`shop/`).
- **Back-office tier** — admin and CRM portal where operators run orders, integrations, simulation, and the workflow command center (`crm/`).
- **Java app-server tier** — Spring Boot service the storefront calls during checkout and simulation so OCI APM populates its "App Servers" dashboards with real JVM telemetry (`services/apm-java-demo/`).
- **Support services** — async-worker, load-control, object-pipeline, edge-fuzz, remediator, auto-remediator and others — independent OTel-instrumented services that feed deterministic shapes of telemetry into the same observability stack (`services/*`).
- **Data tier** — a single Oracle Autonomous Database (ATP) shared by the storefront and the back-office, surfaced through SQLAlchemy and JDBC, observed via OCI Stack Monitoring and via APM database spans.
- **Observability fabric** — APM, RUM, Logging, Logging Analytics, Monitoring, Stack Monitoring, and Service Connector Hub. Every service emits the same five identifiers (`service.namespace`, `service.name`, `service.instance.id`, `oracleApmTraceId`, `oracleApmSpanId`) on every signal so that a click in any pillar lands you in any other pillar with the join already done.

Two SVG references describe the topology and the observability surface in detail:

- `site/architecture/diagrams/platform-overview.svg` — services, ingress, ATP, and signal flow at a glance.
- `site/architecture/diagrams/private-demo-observability-reference.svg` — the same topology with APM/RUM/Logging/Logging Analytics/Monitoring/Stack Monitoring/Service Connector Hub overlays.

Both diagrams are kept current alongside the running deployment and are rendered into the MkDocs site under `/architecture/`.

---

## B. Application Tier

### B.1 `shop/` — OCTO Drone Shop

The OCTO Drone Shop is a FastAPI (Python) storefront. It is the public face of the platform: anonymous browsing, login, cart, checkout, payment.

**Server modules (`shop/server/`):**

- `main.py` — FastAPI application factory. Wires middleware, mounts `modules/*`, starts OTel and the logging SDK at import time.
- `auth_security.py` — login + session helpers. Hosts `require_admin_or_internal_service`, which is the boundary check used by every admin-only handler.
- `store_service.py` — read/write helpers for products, categories, and inventory.
- `storefront.py` — Jinja-rendered storefront pages (catalogue, product detail).
- `crm_catalog_sync.py` — pulls catalog state from the back-office so storefront and admin stay aligned.
- `assistant_service.py` / `genai_service.py` — Storefront-side façade for the GenAI assistant calls (proxied through the workflow gateway).
- `modules/auth.py`, `modules/orders.py`, `modules/products.py`, `modules/catalogue.py`, `modules/shop.py` — public storefront API surface.
- `modules/payments/` — payment gateway emulator and providers.
  - `gateway_emulator.py` — the heart of the checkout observability story. Emits one span and one structured log per gateway step (wallet decryption, antifraud check, network token, authorize, capture). Stores only token-safe metadata.
  - `simulated_provider.py`, `paypal_provider.py`, `stripe_provider.py`, `oci_osb_provider.py` — pluggable providers.
  - `checkout_workflow.py` — orchestration state machine.
  - `state_machine.py`, `webhooks.py`, `events.py`, `registry.py` — supporting infrastructure.
- `modules/java_app_server.py` — `JavaAppServerClient`. Routes checkout antifraud verification and authorization through the Java sidecar so OCI APM sees a real Java app-server segment downstream of the Python span.
- `modules/workflow_gateway.py` — same-origin proxy for the private Workflow Gateway service. Admin-only, host-bound, with allow-listed prefixes (`api/workflows/`, `api/components/`, `api/query-lab/`, `api/selectai/`).
- `modules/public_api.py` — versioned external order ingest API. Documents the idempotency contract for B2B order pushers.
- `modules/admin.py`, `modules/observability_dashboard.py`, `modules/simulation.py` — back-office surfaces that ride alongside the public shop for demo purposes.

**Middleware (`shop/server/middleware/`):**

- `tracing.py` — adds custom spans for request entry, auth check, response finalize, plus a "request span" binding so downstream `push_log()` calls attach `app.log` span events to the same server span.
- `metrics_mw.py` — emits per-request RED metrics (rate, errors, duration) with low-cardinality labels.
- `geo_latency.py`, `chaos.py`, `circuit_breaker.py` — controlled-failure injectors for chaos and resilience demos.

**Templates (`shop/server/templates/`):**

- `base.html`, `shop.html`, `login.html`, `services.html`, `page.html`, `dashboard.html` — Jinja templates with sanitized RUM hooks. Login submits emit `auth.login.submit` and `auth.login.result` RUM custom actions that carry the workflow ID and the W3C `traceparent` but never the username or password.

**Observability (`shop/server/observability/`):**

- `otel_setup.py` — OpenTelemetry initialization. Builds the resource (`service.name`, `service.namespace`, `service.instance.id`, `host.name`), wires the OCI APM exporter with the private/public data key, configures the FastAPI auto-instrumentation with sanitized request header capture (`x-correlation-id`, `x-request-id`, `x-workflow-id`, `x-run-id`, `x-octo-journey-id`, …) and a sanitize list (`authorization`, `cookie`, `set-cookie`, `x-api-key`, `x-internal-service-key`, `oci-apm-private-datakey`).
- `logging_sdk.py` — structured JSON logger backed by the OCI Logging ingestion SDK (`oci.loggingingestion`). Masks email, phone, PAN, CVV in payloads but exempts trace IDs and request IDs from card-number masking so correlation survives. Attaches compact `app.log` span events to the active request span so the APM "Span Details" page shows Logs > 0.
- `correlation.py` — `build_correlation_id`, `current_trace_context`, `outbound_headers`, `set_peer_service`, `apply_span_attributes`, `service_metadata`. The single source of truth for what identifiers flow on what signal.
- `workflow_context.py` — `resolve_workflow`, `current_workflow`. Maps URL paths and explicit overrides to a `(workflow.id, workflow.step)` pair that is then attached to every span, log, and metric on the request.
- `security_spans.py` — `security_span` context manager. Emits child spans for security-relevant operations (login, authz check, secret access) with stable attribute names that the saved searches and detection rules key off.
- `business_metrics.py` — OTel instruments for KPIs (orders created, order value, login failures, login success, active sessions, payment success rate, idempotency rejections). Low cardinality only.
- `metrics.py` — meter and instrument bootstrap.
- `oci_monitoring.py` — direct OCI Monitoring ingest for metrics that must land in the `octo_apm_demo` namespace.
- `purchase_journey.py` — derived "journey" instrument that joins login + cart + checkout into a single funnel signal.
- `llmetry.py` — LLM telemetry helpers (token usage, model latency, prompt classification) for the GenAI assistant path.
- `db_session_tagging.py` — annotates SQLAlchemy sessions with `db.target`, `db.connection_name`, `tenancy.compartment` so DB spans carry the right peer.service.
- `oci_vss.py` — OCI Vulnerability Scanning Service integration hook.
- `log_enricher.py` — final-mile log enrichment (adds resource attributes and trace context to every record).

### B.2 `crm/` — Enterprise CRM Portal

The CRM Portal is a FastAPI back-office. It is admin-bound: orders, customers, integrations, campaigns, tickets, the observability dashboard, and the workflow / attack-lab command centers.

**Server modules (`crm/server/`):**

- `main.py` — FastAPI factory. Same shape as the shop but with admin defaults.
- `bootstrap.py` — first-run database initialisation.
- `order_sync.py` — `sync_external_orders` and order-risk helpers. Pulls orders from external sources (the shop, configurable upstreams) and reconciles them into the CRM order table.
- `shop_catalog_sync.py` — inverse of the shop's `crm_catalog_sync.py`.
- `modules/admin.py` — admin surface (users, roles, system flags).
- `modules/coordinator.py` — admin-only OCI Coordinator surface, scoped to OCTO APM Demo resources only. Rejects general OCI assistant queries. Allow-lists a small set of resource hosts and a fixed project scope.
- `modules/observability_dashboard.py` and `modules/observability_frontend.py` — the in-app observability command center.
- `modules/orders.py`, `modules/customers.py`, `modules/products.py`, `modules/shops.py`, `modules/shipping.py`, `modules/invoices.py`, `modules/tickets.py`, `modules/campaigns.py`, `modules/customer_enrichment.py`, `modules/files.py`, `modules/api_keys.py`, `modules/integrations.py`, `modules/reports.py`, `modules/analytics.py`, `modules/simulation.py`, `modules/slack_notify.py` — the CRM domain modules.
- `modules/_authz.py` — `require_admin_user`. Hard boundary used by every admin-only route, including the coordinator.

**Middleware (`crm/server/middleware/`):**

- `tracing.py` — same minimum-three-spans-per-request pattern as the shop (`middleware.entry`, `auth.check`, response finalize) plus workflow resolution, request ID propagation, and correlation ID derivation. Combined with FastAPI auto-instrumentation, route handler spans, DB spans, and security spans, every request produces eight or more spans.
- `metrics_mw.py` — RED metrics with admin-friendly label sets.
- `session_gate.py` — session validity and admin-cookie checks.
- `geo_latency.py`, `chaos.py` — chaos injectors.

**Observability (`crm/server/observability/`):**

The shape is identical to the shop and uses the same module names. `business_metrics.py` exposes back-office KPIs (orders created, invoices generated, invoice paid, tickets created, auth login failures, active sessions, order sync total, security events, leads captured/converted, shipments, file uploads/downloads, reports). The label design rule is explicit: low cardinality only, no user IDs, no session IDs, no IPs in metric labels.

### B.3 `services/apm-java-demo/` — Java Payment App Server

A small Spring Boot service (`com.octo.apmdemo.App`) attached to the OCI APM Java agent via `-javaagent:`. The Java agent reports Apdex, active servers, server restarts, per-thread resource consumption, server request rate, app-server CPU load, and full JVM telemetry (name, version, young/old GC time) into the OCI APM "App Servers" dashboard. Python services do not populate that dashboard surface by themselves; routing checkout through this JVM creates a real downstream app-server segment.

Source files:

- `src/main/java/com/octo/apmdemo/App.java` — Spring Boot application, controllers for `/api/java-apm/quote`, `/api/java-apm/payment/verify`, `/api/java-apm/payment/authorize`, `/api/java-apm/simulate/*`. Filter chain that extracts the inbound W3C trace context, opens a server span, mirrors MDC fields for logback, and emits stdout JSON events.
- `src/main/java/com/octo/apmdemo/OtelSupport.java` — manual OpenTelemetry helpers used in addition to the auto-attached agent.
- `src/main/java/com/octo/apmdemo/PaymentRailSimulator.java` — deterministic payment-rail simulator with seedable randomness; emits structured events for each rail step.
- `src/main/resources/application.yml` — Spring Boot configuration.
- `agent-bundle/` and `download-agent.sh` — OCI APM Java agent bundle and fetch script. Bundled into the container at build time; configured at runtime through environment variables.

### B.4 `services/workflow-gateway/` — Admin Workflow Gateway

The Workflow Gateway is the admin-only proxy that fronts Select AI, Query Lab, and the GenAI assistant. It is reachable only via the shop's `modules/workflow_gateway.py` same-origin proxy. The gateway enforces:

- Allow-listed path prefixes (`api/workflows/`, `api/components/`, `api/query-lab/`, `api/selectai/`).
- A capped body size (16 KiB) and a Select AI prompt cap (1000 characters).
- A closed set of Select AI actions (`showsql`, `narrate`, `chat`).
- Header forwarding for `traceparent`, `tracestate`, `x-correlation-id`, `x-request-id`, `x-session-id`, `x-internal-service-key`, plus `authorization` and `content-type`.

### B.5 Support Services

Each support service is an independent Python or Go process with its own `pyproject.toml`, its own `telemetry.py`, and the same five-identifier emission contract:

- `services/async-worker/` — durable background worker. Pulls jobs from an internal queue, executes them under a span, emits structured logs.
- `services/load-control/` — back-pressure controller. Watches platform-wide queue depth and throttles upstream callers.
- `services/object-pipeline/` — ingest pipeline for blob storage events.
- `services/edge-fuzz/` — input fuzzer for edge endpoints; doubles as a chaos source.
- `services/remediator/` — orchestrated remediation actions for detected incidents.
- `services/auto-remediator/` — OCI Function (`func.py` + `func.yaml`) that runs automated remediation in response to OCI Monitoring alarms.
- `services/otel-gateway/` — local OTel collector for the compute-VM topology.
- `services/browser-runner/`, `services/cache/`, `services/container-lab/`, `services/vm-lab/` — supporting infrastructure for the attack/demo lab.

Every support service sets `service.namespace = "octo"`, a stable `service.name`, and a `service.instance.id` derived from `SERVICE_INSTANCE_ID` → `POD_NAME` → `HOSTNAME` → `local-dev` (see Section E.3).

### B.6 `tools/traffic-generator/` — Synthetic Traffic

`tools/traffic-generator/` produces ongoing, realistic traffic against the storefront and back-office. It is OTel-instrumented like a real client: each synthetic session starts a root span, propagates `traceparent` and `tracestate` on every fetch, and emits its own RUM-shaped logs. This is what populates the platform's "always-on" telemetry baseline so dashboards and alarms have signal to fire against between live walkthroughs.

---

## C. Data Tier

One Oracle Autonomous Database (ATP) backs both the storefront and the back-office. The schema is split into logical domains but lives in a single PDB.

**Storage and access:**

- Shop side uses async SQLAlchemy (`shop/server/database.py`) with the `python-oracledb` thin driver.
- CRM side uses the same SQLAlchemy stack (`crm/server/database.py`) plus `db_compat.py` for compatibility shims.
- The Java app-server uses the Oracle JDBC thin driver.
- All three connect via the same `octo-atp-wallet` Kubernetes secret (Helm template `deploy/helm/octo-apm-demo/templates/secrets.yaml`), which materialises the wallet directory into each container and exposes the wallet password via env.

**Order idempotency contract — the most load-bearing data-tier invariant:**

The shop emits an `idempotency_token` for every outbound order push:

```python
# shop/server/modules/integrations.py
idempotency_token = str(uuid.uuid5(_ORDER_IDEMPOTENCY_NS, f"{order_id}:{source}"))
```

The CRM honours it via the composite key `(source_system, source_order_id, idempotency_token)`. Replays from the public order ingest API (`shop/server/modules/public_api.py`, schema in `shop/server/modules/order_sync_async.py` and `crm/server/modules/orders.py`) are deduplicated against this composite. The token is UUID5 over a stable namespace so retries from different machines converge on the same value.

**DB span enrichment:**

`observability/db_session_tagging.py` (both shop and CRM) attaches `db.target`, `db.connection_name`, and tenancy/compartment hints to every SQLAlchemy session. `observability/db_spans.py` (CRM) adds query-shape attributes. The result: any DB span in APM carries the same trace ID as the parent HTTP span and the same `db.connection_name` as the OCI Stack Monitoring ATP target, so a slow query in APM can be cross-referenced to a DB-side wait event in Stack Monitoring with one click.

---

## D. OCI Observability Surface

This is the section the platform was built to demonstrate.

### D.1 OCI APM (Application Performance Monitoring)

- **Domain configuration:** private and public data keys + APM domain endpoint are injected as environment variables. The shop reads them from `cfg` and registers the OCI APM exporter in `otel_setup.py`.
- **Trace context:** W3C `traceparent` and `tracestate` are accepted on inbound requests and propagated on every outbound HTTP call (`outbound_headers()` in `observability/correlation.py`). B3 headers are accepted as a fallback for clients that have not migrated.
- **Span attributes — the dotted/snake_case duality:** every span carries both dotted OTel attributes (`http.url.path`, `workflow.id`, `payment.gateway.step`) and snake_case aliases (`workflow_id`, `workflow_step`). Dotted names map cleanly to Log Analytics fields; snake_case aliases survive flat-attribute exporters and saved-search field discovery.
- **Trace Explorer drilldowns:** spans, span events, exceptions, and child spans are all populated. The `app.log` span events emitted by `logging_sdk.push_log()` are visible in the APM "Span Details > Logs" tab so engineers do not have to leave APM to read the log line that produced the failure.
- **Span identity:** the resource always carries `service.name`, `service.namespace`, `service.instance.id`, `host.name`, plus the OTel SDK and language version.

### D.2 OCI APM RUM

- **Web application OCID:** configured per environment, surfaced to the browser via a sanitized inline config block in the base templates (`shop/server/templates/base.html`, `crm/server/templates/base.html`).
- **Sanitized custom actions:** login submission and result, cart events, checkout step transitions, workflow start/end. Each carries the workflow ID, the journey ID, the action name, the HTTP status — but never the username, password, or PAN. The `templates/login.html` form is wired so the submit event publishes `auth.login.submit` with form completeness flags, not field values.
- **Trace propagation from the browser:** RUM fetches set `traceparent` so the server-side FastAPI span is a child of the RUM span. Both halves carry the same `oracleApmTraceId`, so a slow page reported in RUM lands you on the exact server span in APM.

### D.3 OCI Logging

- **Transport:** structured JSON via the OCI Logging ingestion SDK (`oci.loggingingestion`). The shop and CRM share `logging_sdk.py` with a background queue + worker thread to keep the request path off the SDK socket.
- **Record fields:** `timestamp`, `level`, `message`, `oracleApmTraceId`, `oracleApmSpanId`, `request_id`, `workflow_id`, `workflow_step`, `service.namespace`, `service.name`, `service.instance.id`, plus the per-domain payload.
- **Span-event mirroring:** every `push_log()` call also emits a compact `app.log` span event on the request server span. This is what makes the APM "Span Details > Logs" tab non-empty.
- **PII masking:** email, phone, PAN, CVV are masked in both the JSON record and the span event. The mask-exempt list explicitly preserves `trace_id`, `span_id`, `oracleApmTraceId`, `oracleApmSpanId`, `traceparent`, `request_id`, `correlation.id`, `workflow_id`, `workflow_step`, and the payment gateway/network transaction IDs so card-number regex cannot eat correlation identifiers that happen to be long numeric strings.

### D.4 OCI Logging Analytics

- **Custom parsers** under `deploy/oci/log_analytics/parsers/`:
  - `octo-shop-v2.json` — shop JSON logs.
  - `octo-crm-v2.json` — CRM JSON logs.
  - `octo-chaos-audit.json` — chaos injector audit trail.
  - `octo-ebpf-tetragon.json` — Tetragon eBPF runtime events.
  - `octo-waf.json` — OCI WAF logs.

- **Saved searches** under `deploy/oci/log_analytics/searches/` — each is a real production-shaped query used by the dashboards and demos. The full inventory:
  - `auth-login-correlation.sql`, `checkout-payment-correlation.sql`, `oke-checkout-payment-correlation.sql`, `oke-kubernetes-trace-correlation.sql`, `oke-onm-ingestion-health.sql`, `connector-live-log-coverage.sql`, `melts-collection-completeness.sql`
  - `genai-assistant-llmetry.sql`, `workflow-health.sql`, `trace-drilldown.sql`, `service-trace-log-coverage.sql`, `service-error-triage.sql`, `service-health-errors.sql`, `chaos-vs-organic.sql`, `db-slowness-hotspots.sql`
  - Security: `attack-lab-detections.sql`, `attack-lab-trace-timeline.sql`, `api-gateway-edge-detections.sql`, `payment-gateway-security-triage.sql`, `payment-threats.sql`, `ebpf-container-drift.sql`, `osquery-attack-findings.sql`, `waf-vs-app-errors.sql`
  - Detection rules: `rule-api-gateway-threat-count.sql`, `rule-compromised-vm-count.sql`, `rule-java-payment-error-count.sql`, `rule-oke-collector-error-count.sql`, `rule-oke-onm-log-samples.sql`, `rule-payment-interception-count.sql`, `rule-payment-redirect-count.sql`

- **Dashboards** under `deploy/oci/log_analytics/dashboards/`:
  - `attack-lab-command-center.json` — the security/attack-lab single-pane-of-glass.
  - `workflow-command-center.json` — workflow health, business KPIs, and trace-log coverage.

- **Detection rules** are wired through `deploy/oci/log_analytics/wire_auto_remediation.py`, which binds each rule SQL to a metric/dimension contract and a Monitoring alarm.

- **Field reuse map** — `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json` documents the mapping from OTel attribute names to existing Logging Analytics fields. This is the contract the contract tests in `tests/test_observability_asset_contract.py` enforce so a renamed OTel attribute cannot silently break a parser or a saved search.

### D.5 OCI Monitoring

- **Custom metric namespace:** `octo_apm_demo` (configurable via `OCI_MONITORING_NAMESPACE`).
- **Metric publishing path:** OTel meter → `observability/oci_monitoring.py` → OCI Monitoring `PostMetricData`.
- **Metrics published:** payment success rate, login failures, login success, active sessions, checkout idempotency rejections, order sync throughput, security event counts, plus the business KPIs from `business_metrics.py`.
- **Alarms** are defined alongside the detection-rule SQLs and bound to the same dimension set so an alarm body can deep-link into the matching saved search.

### D.6 OCI Stack Monitoring

- **ATP health:** the shared Autonomous Database is registered as a Stack Monitoring resource; its connection name matches the `db.connection_name` span attribute emitted by SQLAlchemy session tagging so APM-side DB spans cross-reference one-to-one.
- **JVM telemetry:** the Java sidecar's OCI APM Java agent feeds the APM "App Servers" surface; the same JVM is registered as a Stack Monitoring resource for host/JVM-level health metrics (heap utilisation, GC counts, thread counts).

### D.7 OCI Service Connector Hub

A Service Connector routes every relevant OCI Logging log group into Logging Analytics so saved searches can run against the same records the apps write. The mapping is one Service Connector per log group, source = Logging, target = Logging Analytics log group, with a parser hint. Quota considerations: Service Connector Hub is subject to a per-tenancy connector cap; the deployment script consolidates log groups where possible and uses one connector per logical signal class (app logs, audit, WAF, eBPF) rather than one per service.

---

## E. Cross-Service Correlation Contract

This is the contract that makes the platform actually demo-able: every signal joins on the same identifiers.

### E.1 W3C / B3 Trace Context Flow

```
Browser (RUM)
  │   traceparent / tracestate set by APM RUM JS
  ▼
Public Load Balancer + WAF
  │   headers preserved end-to-end
  ▼
FastAPI (shop or crm)
  │   FastAPI auto-instrumentation extracts traceparent → server span is a child of RUM span
  ▼  outbound_headers() injects traceparent + tracestate + X-Workflow-Id + X-Request-Id
Java App Server (Spring Boot + APM Java agent)
  │   filter chain extracts headers, opens its own server span as a child
  ▼  JDBC instrumentation propagates context into DB spans
Oracle Autonomous Database (ATP)
```

### E.2 Custom Header Propagation

In addition to the standard W3C headers, the platform propagates a small, deliberate set of custom headers across every hop:

- `X-Request-Id` — stable per-request identifier (generated if missing).
- `X-Correlation-Id` — broader correlation across retries and async hops.
- `X-Workflow-Id` and `X-Workflow-Step` — semantic workflow context.
- `X-Run-Id` — for batch/simulation runs.
- `X-Octo-Journey-Id`, `X-Octo-Session-Id`, `X-Octo-User-Action`, `X-Octo-Checkout-Step` — RUM-originated journey context.
- `X-Internal-Service-Key` — server-to-server bearer for admin-only endpoints (used by `require_admin_or_internal_service` in `shop/server/auth_security.py`).

All of these are echoed back on responses and recorded as both dotted (`workflow.id`) and snake_case (`workflow_id`) span attributes.

### E.3 Service Identity Fallback Chain

Every emitter resolves `service.instance.id` through the same fallback:

```python
service_instance_id = env("SERVICE_INSTANCE_ID", env("HOSTNAME", "local-dev"))
```

Kubernetes manifests inject `SERVICE_INSTANCE_ID` from `POD_NAME` via the downward API. Compute VMs inject `SERVICE_INSTANCE_ID` from the cloud-init template. Local dev falls all the way back to `local-dev`. The Java service uses the same chain via `OtelSupport.resolveInstanceId()`.

### E.4 Trace-Log Correlation Identifiers

Every log record carries `oracleApmTraceId` and `oracleApmSpanId` (in addition to the OTel-native `trace_id` / `span_id`). The OCI APM span details page therefore exposes a one-click drilldown to "All logs for this trace" in Logging Analytics, and the Logging Analytics saved searches all `WHERE 'Oracle APM Trace ID' = …` rather than relying on free-text regex on the message body.

### E.5 Source-Level Contract Tests

The correlation surface is not a documentation promise; it is enforced in CI:

- `tests/test_signal_contract_inventory.py` walks every observability module, lists the attributes it emits, and asserts that the field reuse map and the saved searches reference only attributes that exist in the inventory.
- `tests/test_observability_asset_contract.py` parses every parser, every saved search, every dashboard, and every detection rule, and asserts that they all key off the same five identifiers and the documented dimension set.
- `tests/test_log_analytics_attack_assets.py` and `tests/test_log_analytics_detection_reliability.py` extend that contract to the attack-lab and detection surfaces.
- `tests/test_documentation_architecture_closure.py` keeps this document and the diagrams in sync with the code.

A rename of `workflow_id` to `workflow.id` without updating the field reuse map fails the build, not the demo.

---

## F. Security Boundaries

The platform is intentionally noisy in observability and intentionally quiet in trust:

- **Admin-only OCTO Coordinator scope:** `crm/server/modules/coordinator.py` rejects non-admin tenancy access and refuses any query that references a resource outside the `octo-apm-demo` project scope or the admin host allow-list. It is a scoped helper, not a general OCI assistant.
- **Workflow Gateway admin host binding:** `shop/server/modules/workflow_gateway.py` enforces `require_admin_or_internal_service`, allow-lists path prefixes, and binds the upstream to a local-host or admin-host upstream. Public storefront callers are rejected before any backend call is made.
- **Token-safe payment telemetry:** the gateway emulator records `payment.card.brand`, `payment.card.last4`, `payment.card.tokenized`, `payment.wallet.token_hash`, and a stable `payment.gateway.request_id`. It never records a PAN or CVV. The logging SDK's PII masking is the second line of defence in case a downstream provider stub leaks one.
- **Trace IDs exempt from card-number masking:** the PAN regex `\b(?:\d[ -]?){13,19}\b` would otherwise eat trace IDs, span IDs, request IDs, order IDs, and payment.gateway.request_id values. The mask-exempt key list in `logging_sdk.py` preserves all of these so correlation cannot be accidentally redacted.
- **Sanitized RUM:** the storefront and admin templates wire RUM custom actions through a small JS helper that strips form values and only emits event-name + outcome + workflow.

---

## G. Deployment Topology

The platform is built so that the same image set runs on three different deployment substrates with telemetry-equivalent behaviour:

- **OKE (Oracle Kubernetes Engine):** raw manifests under `deploy/k8s/oke/` (`shop/`, `crm/`, `apm-java-demo/`, `workflow-gateway/`, `common/` for namespaces and network policies).
- **Helm:** chart under `deploy/helm/octo-apm-demo/` with parity to the raw manifests (`shop-deployment.yaml`, `crm-deployment.yaml`, `java-gateway-deployment.yaml`, `workflow-gateway-deployment.yaml`, `secrets.yaml`, `ingress.yaml`, HPA and PDB resources, Tetragon DaemonSet for eBPF runtime events).
- **Compute (VM / Podman):** `deploy/compute/` ships a single-host topology driven by `app-compose.yml`, `install.sh`, `deploy-apps.sh`, `render-runtime-env.sh`, systemd units under `deploy/compute/systemd/`, and a cloud-init template at `deploy/compute/terraform/cloud-init/compute.yaml.tftpl`.
- **OCI Resource Manager stack:** `deploy/resource-manager/` packages the Terraform stack for one-click deployment.

**Public ingress:**

- Public load balancers with WAF policies. Shop and admin live on separate listeners with distinct WAF rule sets.
- TLS via cert-manager + Let's Encrypt on OKE, or via the OCI Certificates service on Compute.
- DNS lives under `${DNS_DOMAIN}` (the admin and storefront hostnames are environment-templated; the demo binds them via the `_ALLOWED_RESOURCE_HOSTS` allow-list in the coordinator module).

**Deployment parity test:** `tests/test_deployment_parity_release_gates.py` runs in CI and asserts that the same env contract, the same service identities, the same APM data key wiring, and the same wallet mount points are present in all three substrates. A drift in one (a new env var in the Helm chart that did not land in cloud-init) fails the release gate.

---

## H. Telemetry Pipeline Diagram

```
                  ┌──────────────┐
                  │   Browser    │
                  │  (OCI RUM)   │
                  └──────┬───────┘
                         │ traceparent / tracestate / RUM custom actions
                         ▼
              ┌────────────────────────┐
              │  Public LB + OCI WAF   │
              │  shop.${DNS_DOMAIN}    │
              │  admin.${DNS_DOMAIN}   │
              └──────┬─────────┬───────┘
                     │         │
              ┌──────▼───┐ ┌───▼──────┐
              │  Shop    │ │   CRM    │   FastAPI (Python)
              │ FastAPI  │ │ FastAPI  │   tracing + metrics middleware
              └──┬───┬───┘ └───┬──────┘   OTel SDK + OCI Logging SDK
                 │   │         │
                 │   │         │   trace context + X-Workflow-Id
                 │   ▼         │
                 │  ┌──────────────┐
                 │  │ Workflow GW  │   admin-only proxy:
                 │  │ (Select AI,  │   Select AI / Query Lab / Assistant
                 │  │  Query Lab)  │
                 │  └──────────────┘
                 │
                 │   trace context + idempotency_token
                 ▼
        ┌──────────────────┐
        │ Java App Server  │   Spring Boot + OCI APM Java agent
        │ (apm-java-demo)  │   populates "App Servers" + JVM dashboards
        └────────┬─────────┘
                 │  JDBC, propagated context
                 ▼
        ┌──────────────────┐
        │  Oracle ATP      │   shared by shop + crm + java
        │  (octo-atp-      │   Stack Monitoring registered target
        │   wallet)        │
        └──────────────────┘

Side-channels — every tier emits to every pillar:

  Spans ────────► OCI APM Domain (private/public data key)
  Metrics ──────► OCI Monitoring  (namespace: octo_apm_demo)
  Logs (JSON) ──► OCI Logging  ──Service Connector Hub──► Logging Analytics
                                                          (parsers, saved
                                                           searches,
                                                           dashboards,
                                                           detection rules)
  RUM events ───► OCI APM RUM (Web App OCID)
  JVM / DB ─────► OCI Stack Monitoring
  Alarms ───────► OCI Functions (auto-remediator)  ──► back into apps
```

Every arrow above carries the same five identifiers:

```
service.namespace = octo
service.name      = octo-drone-shop | enterprise-crm-portal | octo-apm-java-demo | …
service.instance.id = ${SERVICE_INSTANCE_ID} || ${POD_NAME} || ${HOSTNAME} || local-dev
oracleApmTraceId  = <128-bit trace id>
oracleApmSpanId   = <64-bit span id>
```

Hold those identifiers steady across every emitter, and a single click in any one OCI Observability pillar lands you in any other with the join already done. That is the platform.
