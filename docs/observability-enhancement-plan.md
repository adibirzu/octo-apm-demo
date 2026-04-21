# OCTO Enhancement Plan

## Objective

Evolve the platform from "instrumented and deployable" into a repeatable OCI
showcase that demonstrates:

- complex cross-service calls with clear business semantics
- end-to-end visibility in OCI APM Trace Explorer and Topology
- structured log collection into OCI Logging and OCI Log Analytics
- deterministic drilldowns from APM to logs and database tooling
- database investigation through OCI Database Management and Operations Insights

## Target outcome

The final demo should let an operator start from any important workflow
(checkout, CRM catalog publish, AI assistant, order sync, simulated fault) and
move through four linked surfaces without losing context:

1. OCI APM trace and topology
2. OCI Logging / Log Analytics evidence
3. OCI DB Management Performance Hub / SQL Monitor
4. OCI Operations Insights SQL Warehouse

## Workstreams

### 1. Complex-call showcase

Prioritize four golden flows:

1. Shop browse -> add to cart -> checkout -> order persistence -> CRM sync
2. CRM product update -> shop catalog synchronization -> storefront refresh
3. Shop AI assistant -> workflow gateway -> database-backed query path
4. Chaos or failure injection -> correlated trace, log, and DB evidence

For each flow, standardize:

- root span name
- child business spans
- workflow identifiers
- order, product, customer, and shop attributes
- correlation-friendly log fields

### 2. OCI APM depth

Strengthen the APM story around business flows instead of raw HTTP traffic.

Deliverables:

- canonical span naming for each golden flow
- per-flow attributes for `workflow.id`, `workflow.step`, `order.id`,
  `customer.email_hash`, `shop.id`, `product.sku`, and sync status
- query-based APM dashboard widgets for checkout, CRM sync, AI assistant, and
  database latency
- a documented verification path for Trace Explorer and Topology

### 3. OCI Logging -> Log Analytics pipeline

Make the logging path explicit and testable:

- application emits structured JSON logs with `trace_id`, `span_id`,
  `oracleApmTraceId`, `workflow_id`, and service metadata
- logs land in OCI Logging log groups first
- OCI Service Connector routes those logs into Log Analytics
- Log Analytics uses saved searches and parsers keyed to the shared trace id

The key outcome is that an APM trace id can be pasted into Log Analytics and
return all related application evidence for both the shop and CRM.

### 4. APM drilldowns

Drilldowns should be designed around operator pivots:

- APM trace -> Log Analytics search by `oracleApmTraceId`
- APM SQL span -> DB Management via `DbOracleSqlId`
- APM service or workflow widget -> trace query filtered to a flow
- app `/api/observability/360` output -> direct OCI console links

The platform should document these as fixed operator playbooks, not as tribal
knowledge.

### 5. DB Management and Operations Insights

Treat DB tooling as part of the demo path, not as optional side tooling.

Deliverables:

- ATP enrolled in Database Management
- ATP enrolled in Operations Insights
- session tagging documented and verified with `MODULE`, `ACTION`, and
  `CLIENT_IDENTIFIER`
- drilldown examples for checkout SQL, CRM sync SQL, and slow-query / chaos SQL

### 6. Documentation and demo usability

The published documentation should guide an operator through rollout in this
order:

1. deploy the applications
2. enable APM and validate traces
3. enable OCI Logging and Log Analytics
4. configure APM drilldowns and dashboards
5. enable DB Management and Operations Insights
6. run the golden demo flows and validate every pivot

## Rollout phases

### Phase 0. Baseline tenancy prerequisites

- confirm ATP, APM domain, Logging log groups, Log Analytics namespace, and
  network egress
- confirm secret sources for `OCI_APM_*`, `OCI_LOG_*`, DB credentials, and
  browser-safe public URLs

### Phase 1. Instrument golden flows

- audit existing spans in shop, CRM, workflow gateway, and DB helpers
- normalize business span names
- document required attributes per flow
- add or refine load and demo scripts that generate the target traces

### Phase 2. Validate APM completeness

- verify Trace Explorer sees all golden flows
- verify Topology shows Shop <-> CRM <-> ATP and workflow gateway edges
- add APM dashboard widgets for latency, error rate, and per-flow trace volume

### Phase 3. Complete the log pipeline

- verify structured app logs reach OCI Logging
- route log groups into Log Analytics
- install saved searches and dashboards
- prove `oracleApmTraceId` joins trace and log evidence

### Phase 4. Build drilldowns

- document trace URL patterns
- document log-search URL patterns and saved searches
- validate DB drilldown fields on SQL spans
- publish the operator path from `/api/observability/360`

### Phase 5. Enable database observability

- enable Database Management for ATP
- enable Operations Insights for ATP
- verify Performance Hub, SQL Monitor, and SQL Warehouse visibility for app SQL

### Phase 6. Demo hardening

- run checkout, CRM sync, AI assistant, and simulated-fault scenarios
- capture screenshots or console checkpoints for GitHub Pages
- update the README, install guide, and published site pages

## Acceptance criteria

| Area | Done when |
| --- | --- |
| Complex calls | One command sequence can generate traces for checkout, CRM sync, AI assistant, and fault workflows |
| APM | Trace Explorer and Topology expose all golden flows with business attributes |
| Logging | OCI Logging receives structured JSON logs and Log Analytics can search by `oracleApmTraceId` |
| Drilldowns | Operators can pivot from trace -> logs -> DB evidence without manual reconstruction |
| Database | DB Management and OPSI show workload from both services with session-tag correlation |
| Docs | README, install guide, and GitHub Pages describe the rollout and validation path end to end |

## Recommended ownership

- Application instrumentation: shop, CRM, workflow gateway maintainers
- OCI service enablement: platform / tenancy operators
- Dashboards and saved searches: observability owner
- GitHub Pages and README: documentation owner after each rollout phase
