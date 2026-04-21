# Enhancement Plan

This page defines the recommended rollout for turning OCTO into a complete OCI
observability showcase rather than just an instrumented application set.

## Goals

- demonstrate complex cross-service business calls
- expose every important workflow in OCI APM Trace Explorer and Topology
- land structured logs in OCI Logging, then route them into Log Analytics
- create usable drilldowns between APM, Log Analytics, DB Management, and OPSI
- make the whole flow reproducible from the published docs

## Golden workflows

The platform should always be able to showcase these four workflows:

1. Shop browse -> cart -> checkout -> order persistence -> CRM sync
2. CRM product or storefront update -> shop catalog synchronization
3. Shop AI assistant -> workflow gateway -> Oracle ATP query execution
4. Simulated failure -> correlated trace, log, and SQL evidence

## Rollout sequence

### Phase 1. Instrument business flows

- normalize span names around business actions, not only HTTP routes
- standardize attributes such as `workflow.id`, `workflow.step`, `order.id`,
  `product.sku`, `shop.id`, `sync.status`, and `DbOracleSqlId`
- ensure the shop, CRM, and workflow gateway all propagate `traceparent`

### Phase 2. Make OCI APM the first operator surface

- verify Trace Explorer shows every golden workflow
- verify Topology shows Shop <-> CRM <-> ATP and workflow gateway edges
- create query-based APM dashboard widgets for:
  - checkout latency and failures
  - CRM sync success / failure
  - AI assistant latency and error rate
  - database-bound traces and slow SQL spans

### Phase 3. Complete the logging path

- emit structured JSON logs from both apps
- preserve `trace_id`, `span_id`, `oracleApmTraceId`, `workflow_id`, and
  service metadata
- send logs to OCI Logging first
- route those log groups into Log Analytics
- publish saved searches keyed to the trace id and workflow id

### Phase 4. Publish drilldowns

- APM trace -> Log Analytics search by `oracleApmTraceId`
- APM SQL span -> DB Management Performance Hub via `DbOracleSqlId`
- app dashboards -> OCI console URLs surfaced by `/api/observability/360`
- operator runbooks for checkout, CRM sync, AI assistant, and simulated faults

### Phase 5. Enable DB Management and OPSI

- enroll ATP in Database Management
- enroll ATP in Operations Insights
- verify session tagging with `MODULE`, `ACTION`, and `CLIENT_IDENTIFIER`
- validate SQL Monitor, Performance Hub, and SQL Warehouse visibility for app
  traffic from both services

### Phase 6. Freeze the demo path

- drive the golden workflows with k6 and smoke scripts
- capture the verification checkpoints in the docs
- keep the README, install guide, and published site aligned

## Deliverables

| Workstream | Deliverable |
| --- | --- |
| Complex calls | repeatable scripts that produce demonstrable cross-service traces |
| APM | dashboard widgets, trace queries, topology validation steps |
| Logging | OCI Logging log groups + Service Connector + Log Analytics searches |
| Drilldowns | documented pivots from trace -> logs -> SQL evidence |
| Database | DB Management and OPSI enablement plus validation screenshots or checks |
| Docs | updated README, install guide, observability pages, and home page links |

## Acceptance criteria

- one demo run produces traces for checkout, CRM sync, AI assistant, and a
  simulated failure
- those traces are visible in OCI APM with business-level attributes
- the same trace id can be searched in Log Analytics
- at least one SQL span can be traced into DB Management
- OPSI shows workload aggregated for the same database and app modules

## Related pages

- [Add-Ons Guide](addons.md)
- [Traces (APM)](traces.md)
- [Logs](logs.md)
- [Cross-Service Tracing](distributed-traces.md)
- [APM Drill-Down](../observability-v2/apm-drilldown.md)
