# APM drill-down

Every span inherits `workflow.id`, `workflow.step`, and `service.name`
attributes. Chaos-injected faults register as span *events* — not
wrapping spans — so latency budgets still reflect reality.

## Provisioning the APM Domain + RUM Web Application

A new tenancy needs both an APM Domain and a RUM Web Application before
traces/RUM events can be ingested. The terraform module
`deploy/terraform/modules/apm_domain` creates both:

```hcl
module "apm_domain" {
  source                       = "./modules/apm_domain"
  compartment_id               = var.compartment_id
  display_name                 = "octo-apm"
  web_application_display_name = "octo-drone-shop-web"
}
```

Outputs include `apm_data_upload_endpoint`, `rum_web_application_id`,
`apm_public_datakey`, and `apm_private_datakey` (sensitive). The helper
script `deploy/oci/ensure_apm.sh` wraps `terraform plan/apply/print` and
emits the matching `export OCI_APM_*` lines for secret population.

## Operator goals

Drilldowns should let an operator start from any one of these entry points and
keep context:

- APM trace
- APM dashboard widget
- Log Analytics row
- `/api/observability/360` response
- DB Management or OPSI investigation

## Recommended widgets

Build query-based APM dashboard widgets around the golden workflows:

- checkout latency and error rate
- CRM sync latency and failure count
- AI assistant latency and downstream query load
- traces containing SQL spans or chaos events

These widgets should be the top-level navigation surface before an operator
opens Trace Explorer.

## Copy-paste trace URL

```
https://cloud.oracle.com/apm-traces/trace-explorer?region=${OCI_REGION}&apmDomainId=${OCI_APM_DOMAIN_OCID}&traceId=<TRACE_ID>
```

## Suggested trace filters

Use repeatable filters for the main demo flows:

- `serviceName = "octo-drone-shop"` for storefront traces
- `serviceName = "enterprise-crm-portal"` for catalog and sync traces
- `workflow.id = "checkout"` for cart-to-order flow
- `workflow.id = "crm-sync"` for order and catalog sync
- `has(attribute.DbOracleSqlId)` for database drilldown candidates

## Linking from a log row

Log Analytics renders every record with a `Trace ID` column; click it to
open the APM trace viewer. Conversely, the Coordinator's
`drilldown_pivot` node returns both the APM URL and a saved-search URL
as `evidence_links` on the incident.

## Linking from a SQL span

When a trace contains `DbOracleSqlId`, use that attribute as the bridge into:

- DB Management Performance Hub / SQL Monitor for statement detail
- Operations Insights SQL Warehouse for historical aggregation

This is the fastest way to move from application latency to database evidence.

## Acceptance criteria

- operators can pivot from APM into Log Analytics using the trace id
- at least one checkout and one CRM sync trace contain valid SQL drilldown data
- `/api/observability/360` exposes the console URLs needed for the pivots
- the same workflow can be followed across APM, logs, and DB tooling without
  manual guesswork

## RUM

RUM sessions now carry `workflow_id` as a custom dimension (added by
`server/observability/rum_dimensions.py` — wave 2 follow-up). Pair the
RUM session id with the backend trace id to see user-visible timing
alongside backend spans.
