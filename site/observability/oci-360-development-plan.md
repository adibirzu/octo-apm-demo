# OCI 360 Development Plan

This plan turns `octo-apm-demo` from a two-service observability showcase into
a broader OCI-native reference platform that can demonstrate browser, API,
application, database, container, VM, edge, and event-driven monitoring from a
single control plane.

## Target Outcome

The target platform should let an operator start from any of these viewpoints
and pivot through the rest without losing context:

- browser or synthetic session
- API Gateway or WAF event
- application trace or service map
- structured logs and Log Analytics evidence
- business KPI or Monitoring alarm
- SQL statement, database session, or ATP health issue
- container, node, or VM saturation event
- async workflow delay, queue lag, or object-processing failure

## Current Baseline

The unified repository already provides a strong base:

- two application services in one repo: `shop/` and `crm/`
- shared ATP and cross-service trace/log correlation
- OCI APM, RUM, Logging, Log Analytics, Monitoring, WAF, DB Management, and
  Operations Insights hooks
- OKE, VM, and Resource Manager deployment paths
- simulation, k6, Playwright, and golden workflow documentation

That means the next phase is not “add observability” but “expand the runtime
surface and make every signal drill down cleanly across more technologies”.

## Gaps To Close

The current platform still has six structural gaps:

1. No single load-control plane for DB, web, app, RUM, container, and VM
   workloads.
2. Edge visibility is partial: API Gateway, load balancer logs, and route-level
   policies are not yet a first-class demo surface.
3. The platform is still mostly synchronous and request/response-driven; it
   lacks queue, stream, cache, and object-processing paths.
4. Host-level visibility is incomplete because the repo has no dedicated VM
   workload module and no container stress lab.
5. Stack Monitoring, Log Analytics, and alarms are strong for the current app
   path but not yet normalized across more runtime types.
6. Auto-remediation exists as a concept, not yet as a repeatable operational
   service chain.

## Design Principles

1. One correlation contract across every runtime.
2. Every new service must add a new failure mode and a new drill-down path.
3. Prefer OCI-native services for edge, telemetry, logging, security, and
   remediation.
4. Keep the operator entry point centralized in the CRM control plane and `/api/observability/360`.
5. Separate “demo data generation” from “load generation” so workloads can be
   replayed safely.
6. Treat logs, metrics, traces, and business events as equal first-class
   evidence.

## Additional Services To Implement

### Control and Telemetry Services

| Service | Type | Why it is needed | Primary signals |
| --- | --- | --- | --- |
| `octo-otel-gateway` | OTel Collector deployment/gateway | Centralize export, enrichment, routing, and sampling for app, edge, VM, and synthetic telemetry | traces, metrics, logs |
| `octo-load-control` | FastAPI control-plane service or CRM module first, standalone later | Run named workload profiles and return run IDs, status, evidence links, and rollback actions | workload events, run metadata, metrics |
| `octo-browser-runner` | Playwright worker / Kubernetes Job executor | Generate real browser sessions for true frontend and RUM-style workflows, not only HTTP load | browser timings, frontend events, journey steps |
| `octo-remediator` | Events + Functions / operator automation service | Execute alarm-driven recovery actions and prove closed-loop operations | alarm actions, audit logs, recovery traces |

### Runtime Expansion Services

| Service | Type | Why it is needed | Primary signals |
| --- | --- | --- | --- |
| `octo-edge-gateway` | OCI API Gateway deployment + route config | Add a real edge policy and routing tier with route-specific auth, quotas, and logs | access logs, latency, 4xx/5xx, auth failures |
| `octo-async-worker` | Background job consumer | Demonstrate retries, backlog, dead-letter handling, and async trace continuation | queue depth, job latency, failure rate |
| `octo-event-stream` | OCI Streaming producer/consumer pair | Add event-driven observability and lag monitoring to order, catalog, and fulfillment flows | stream lag, consumer delay, redelivery |
| `octo-cache` | Redis/Valkey cache | Add cache hit/miss/eviction visibility and cache-induced failure modes | cache latency, hit ratio, evictions |
| `octo-object-pipeline` | Object Storage + Events/Functions processor | Demonstrate file ingestion, document processing, and storage-driven workflows | object events, processing latency, error logs |
| `octo-vm-lab` | Compute VM workload target | Add host metrics, OS logs, process health, filesystem saturation, and management-agent visibility | CPU, memory, disk, syslog, process state |
| `octo-container-lab` | OKE DaemonSet/Job workload set | Add noisy-neighbor, OOM, crashloop, throttling, and node-pressure demos | pod restarts, OOMKilled, throttling, node saturation |

### Optional Later-Phase Service

| Service | Type | Why it is optional |
| --- | --- | --- |
| `octo-service-mesh` | OCI Service Mesh or equivalent | Only add when east-west policy control, service-to-service mTLS, and per-route traffic telemetry become more valuable than the operational overhead |

## OCI Service Additions And Expansion

These are the OCI services that should become part of the standard deployed
surface for the next major version:

| OCI service | Add / expand | Purpose in the platform |
| --- | --- | --- |
| API Gateway | Add | Public API front door for workflow, CRM, and machine-facing endpoints |
| Load Balancer access/error logs | Expand | Edge traffic evidence for every demo and postmortem |
| WAF | Expand | Route-aware protection and visibility across storefront and admin surfaces |
| APM Availability Monitoring | Add | OCI-native synthetic and availability checks for browser/API paths |
| Logging + Service Connector Hub | Expand | Route app, LB, API Gateway, WAF, audit, and flow logs into a unified analytics layer |
| Log Analytics | Expand | New parsers, saved searches, dashboards, and run-specific drilldowns |
| Monitoring + Alarms + Notifications | Expand | Per-service SLOs, load-profile alarms, VM/container saturation alarms |
| Stack Monitoring | Expand | Discover more than ATP: include edge, app, host, and runtime dependencies where supported |
| DB Management + Operations Insights | Expand | Normalize SQL pivots for every workload profile and service |
| Events + Functions | Add | Auto-remediation, event-triggered workflows, and auditability |
| Vault + CSI | Expand | Secrets for every new runtime, worker, and edge service |
| Certificates + DNS + Health Checks | Expand | Production-grade edge path and operator validation |
| Cloud Guard + VSS + Security Zones | Expand | Security posture and compliance story across the wider platform |
| Management Agent / host integrations | Add | Bring VM-level telemetry into the same operator path |

## Proposed Load Profile Catalog

The next release should introduce a named profile model instead of isolated ad
hoc buttons. Each profile should emit:

- `load_profile`
- `run_id`
- `workflow_id`
- `target_type`
- `target_name`
- `operator`
- `expected_signal`
- `rollback_action`

Recommended first profile set:

| Profile | Target | Purpose |
| --- | --- | --- |
| `db-read-burst` | ATP | High-frequency read load with SQL drill-down |
| `db-write-burst` | ATP | Insert/update bursts for redo, wait, and commit visibility |
| `web-checkout-surge` | Shop + CRM | End-to-end storefront and CRM order path |
| `crm-backoffice-surge` | CRM | Operator-heavy workload on admin modules |
| `browser-journey` | Browser + RUM | Real page navigation, cart, checkout, error, and retry paths |
| `app-exception-storm` | App tier | Error-rate, trace, and alert validation |
| `cache-miss-storm` | Cache + app | Cache cold-start and failover visibility |
| `stream-lag-burst` | Streaming | Consumer delay, backlog, and redelivery |
| `container-cpu-pressure` | OKE pods | CPU throttling and HPA / alarm response |
| `container-memory-pressure` | OKE pods | OOM, restart, and degraded latency |
| `vm-cpu-io-pressure` | Compute VM | Host saturation, process slowdown, disk latency |
| `edge-auth-failure-burst` | API Gateway + WAF | Edge rejection, auth noise, and route protection |

## Delivery Phases

### Phase 0. Normalize The Correlation Contract

Deliverables:

- shared workload run schema
- standard service metadata across shop, CRM, worker, gateway, and load tools
- log field contract for edge, app, DB, worker, and host logs
- naming rules for alarms, dashboards, searches, and saved views

Exit criteria:

- every log and span includes enough identity to pivot by run, workflow, and
  service
- `/api/observability/360` exposes the current environment, edges, and enabled
  add-ons consistently

### Phase 1. Edge And Telemetry Backbone

Deliverables:

- `octo-otel-gateway`
- OCI API Gateway in front of selected public and machine-facing routes
- LB, API Gateway, and WAF log onboarding
- route-aware request IDs and trace propagation at the edge
- certificate, DNS, and health-check normalization

Exit criteria:

- a request can be followed from edge event to trace to log search to DB or app
  evidence
- edge logs and app logs share join keys

### Phase 2. Unified Load Control Plane

Deliverables:

- `octo-load-control`
- named workload profiles with audit trail
- CRM Simulation Lab updated to trigger profiles instead of isolated toggles
- run ledger persisted in DB or Object Storage
- profile status surfaced in `/api/observability/360`

Exit criteria:

- one operator action can launch DB, web, app, container, and VM-oriented runs
- every run has deterministic evidence and cleanup semantics

### Phase 3. Browser And Synthetic Workflows

Deliverables:

- `octo-browser-runner`
- browser-based checkout, catalog, and CRM admin journeys
- OCI APM Availability Monitoring / health checks aligned to the same journeys
- screenshot, trace, and log links bound to `run_id`

Exit criteria:

- browser journeys produce frontend and backend evidence that operators can
  follow without manual correlation

### Phase 4. Async And Stateful Runtime Expansion

Deliverables:

- `octo-async-worker`
- `octo-event-stream`
- `octo-cache`
- `octo-object-pipeline`
- new workflows for async order processing, stock sync, asset ingestion, and
  cache invalidation

Exit criteria:

- the platform demonstrates synchronous, asynchronous, cached, and
  event-driven failure modes
- Monitoring and Log Analytics distinguish service, queue, and cache behavior

### Phase 5. Host, Container, And Security Operations

Deliverables:

- `octo-vm-lab`
- `octo-container-lab`
- node, pod, and VM stress profiles
- expanded Cloud Guard / VSS / audit / WAF dashboards
- `octo-remediator` with operator-approved or automated remediations

Exit criteria:

- one incident can start at VM or container level and still pivot through app,
  trace, log, and alarm evidence
- at least one alarm can trigger a safe remediation workflow end to end

### Phase 6. Demo Hardening And Publication

Deliverables:

- final dashboards and saved searches
- runbooks for every golden profile
- doc updates, screenshots, and one-command demo paths
- pass/fail verification matrix

Exit criteria:

- a new operator can run the full platform demo without tribal knowledge
- every profile has a documented validation path

## Recommended Execution Order For Services

Build in this order:

1. `octo-otel-gateway`
2. `octo-edge-gateway`
3. `octo-load-control`
4. `octo-browser-runner`
5. `octo-async-worker`
6. `octo-cache`
7. `octo-event-stream`
8. `octo-object-pipeline`
9. `octo-container-lab`
10. `octo-vm-lab`
11. `octo-remediator`

Why this order:

- the telemetry backbone must exist before adding more workloads
- the load-control plane is the multiplier for every later service
- browser and async services create the most visible new operator value
- host and remediation work only pay off once the platform emits richer alarms

## Verification Matrix

| Area | Must be true before phase closes |
| --- | --- |
| Edge | API Gateway, LB, and WAF traffic can be joined to app evidence |
| Browser | A real browser run produces frontend and backend evidence under one `run_id` |
| App | Request spikes, error storms, and latency bursts are visible in APM, Logging, and Monitoring |
| DB | SQL drill-downs work for read, write, contention, and slow-query profiles |
| Cache | Hit ratio and cache-failure profiles have distinct dashboards and alarms |
| Async | Stream lag, worker retries, and DLQ-style failures are observable |
| Container | Pod restarts, CPU throttling, and memory pressure are visible with clear drill-downs |
| VM | Host pressure is visible through logs, metrics, and alarms with app correlation |
| Security | WAF, auth, and audit events can be tied to workload runs and operator actions |
| Remediation | At least one alarm can launch a controlled remediation workflow with audit evidence |

## Initial Backlog For The Next Build Cycle

### Foundation

- create shared telemetry and run metadata schema
- add `run_id` support to the current observability and simulation surfaces
- define labels, dimensions, and log fields for all future services

### Services

- scaffold `octo-otel-gateway`
- scaffold `octo-load-control`
- scaffold `octo-browser-runner`
- define OCI API Gateway route groups and auth model

### Observability

- add LB, API Gateway, WAF, audit, and flow-log ingestion plan
- define Log Analytics saved searches per new runtime type
- define Monitoring metrics and alarms per profile

### Runtime expansion

- choose the first async service pair
- choose cache topology and invalidation model
- define VM target topology and node/container stress method

## Non-Goals For The Next Phase

Do not add these in the first wave:

- multi-region failover
- service mesh, unless edge and async phases prove it is necessary
- self-managed Kafka or Elastic if OCI-native services cover the need
- generic “AI observability” features before the baseline OCI 360 path is complete

## Definition Of Done For The Program

The program is done when:

- the platform demonstrates browser, edge, app, DB, cache, async, container,
  and VM workloads from one control plane
- every workload has traces, logs, metrics, alarms, and an operator drill-down
  path
- OCI-native services provide the 360-degree operations story at the edge, app,
  data, runtime, and security layers
- the docs and demo scripts are strong enough that the platform can be reused
  as a repeatable tenancy blueprint, not only as a developer sandbox
