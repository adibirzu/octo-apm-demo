# APM ↔ Log Analytics round-trip (Phase 1.3)

Closes the observability loop: every APM trace links to its log records,
every LA log record links back to the APM trace. Clickable both
directions.

## Components

| File | Purpose |
|---|---|
| `trace-to-logs.json` | Saved search parameterised by `${trace_id}`. APM widgets deep-link to it. |
| `errors-by-route.json` | Bar-chart widget: HTTP 4xx/5xx by route, last 1h. Populates the operations dashboard. |
| `slow-checkout-spans.json` | Table: checkout calls > 1s, grouped by `oracleApmTraceId` — click the trace id to jump into APM Trace Explorer. |
| `apply.sh` | Idempotent upsert of every `*.json` saved search via `oci log-analytics saved-search create-or-update`. |
| `smoke-test.py` | End-to-end smoke: given a trace id, polls LA until the log record arrives; asserts the round-trip works. |

## Wire it up

```bash
LA_NAMESPACE=<oci-tenancy-la-namespace> \
LA_LOG_GROUP_ID=ocid1.loganalyticsloggroup.oc1..xxx \
./tools/la-saved-searches/apply.sh
```

Then, in the **OCI APM → Trace Explorer** widget editor, add a drilldown
action on the "Trace ID" column:

```
https://cloud.oracle.com/loganalytics/search?region=${OCI_REGION}&savedSearch=octo-trace-to-logs&param.trace_id=${TRACE_ID}
```

Clicking a trace id in APM now opens LA filtered to that trace's logs.
Click a log record in LA and the `oracleApmTraceId` column links back
to `https://cloud.oracle.com/apm-traces/trace-explorer?traceId=<x>`.

## Validate end-to-end

```bash
# 1. Run the traffic generator briefly
OCTO_TRAFFIC_RUN_DURATION_SECONDS=90 \
OCTO_TRAFFIC_SHOP_BASE_URL=https://drone.octodemo.cloud \
octo-traffic

# 2. Grab any trace_id from APM Trace Explorer (30 chars hex)
# 3. Run the smoke test
python tools/la-saved-searches/smoke-test.py \
    --la-namespace <namespace> \
    --trace-id <32-hex-chars> \
    --timeout 300
```

A passing run prints:

```
[poll 3] trace_id=abc...def found in LA after 28s
```

If it times out, check:

- The Service Connector `la-pipeline-octo-shop-app` exists
  (created by `deploy/terraform/main.tf::la_pipeline_app_logs`).
- The shop's `server/observability/logging_sdk.py` is stamping
  `oracleApmTraceId` (it should — the correlation.py shim handles this).
- LA has `octo-shop-app-json` as a registered source
  (run `tools/create_la_source.py --apply`).

Typical ingestion latency on OCI: 30–120 s.
