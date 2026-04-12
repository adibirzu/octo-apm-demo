# APM drill-down

Every span inherits `workflow.id`, `workflow.step`, and `service.name`
attributes. Chaos-injected faults register as span *events* — not
wrapping spans — so latency budgets still reflect reality.

## Copy-paste trace URL

```
https://cloud.oracle.com/apm-traces/trace-explorer?region=${OCI_REGION}&apmDomainId=${OCI_APM_DOMAIN_OCID}&traceId=<TRACE_ID>
```

## Linking from a log row

Log Analytics renders every record with a `Trace ID` column; click it to
open the APM trace viewer. Conversely, the Coordinator's
`drilldown_pivot` node returns both the APM URL and a saved-search URL
as `evidence_links` on the incident.

## RUM

RUM sessions now carry `workflow_id` as a custom dimension (added by
`server/observability/rum_dimensions.py` — wave 2 follow-up). Pair the
RUM session id with the backend trace id to see user-visible timing
alongside backend spans.
