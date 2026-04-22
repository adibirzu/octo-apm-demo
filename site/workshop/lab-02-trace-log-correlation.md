# Lab 02 — Trace ↔ Log correlation

## Objective

Take an APM trace_id, find the matching log records in Log Analytics,
and learn the round-trip click path operators use during incidents.

## Time budget

30 minutes.

## Prerequisites

- Lab 01 complete.
- Log Analytics source `octo-shop-app-json` registered (one-time;
  `tools/create_la_source.py --apply`).
- Saved searches deployed (`tools/la-saved-searches/apply.sh`).

## Steps

### 1. Generate a request and capture the trace_id

```bash
TRACEPARENT="00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01"
TRACE_ID=$(echo "$TRACEPARENT" | cut -d- -f2)

curl -sS \
    -H "traceparent: $TRACEPARENT" \
    -H "X-Workflow-Id: workshop-lab-02" \
    https://drone.octodemo.cloud/api/products?category=drones | jq '.[0:3]'

echo "trace_id: $TRACE_ID"
```

### 2. Wait for ingestion, then query Log Analytics (Console)

OCI Logging → Service Connector → Log Analytics ingestion typically
lands within 60 s.

1. Open **OCI Console → Observability & Management → Logging
   Analytics → Search**.
2. Run the saved search you deployed:
    ```
    'Log Source' = 'octo-shop-app-json' | where oracleApmTraceId = '<TRACE_ID>'
    ```
3. You should see one row per log record the shop emitted while
   processing your request. The `oracleApmTraceId` column is the join
   key; click any row to open its full JSON payload.

### 3. Query Log Analytics from the CLI

```bash
oci log-analytics query \
    --namespace-name "$LA_NAMESPACE" \
    --query-string "'Log Source' = 'octo-shop-app-json' | where oracleApmTraceId = '$TRACE_ID' | head limit = 10" \
    | jq '.data.results[] | {ts:."Time", level, message}'
```

### 4. Click back to APM from a log record

In the Console:

1. Click any record in your saved-search result.
2. The right panel shows the full JSON. Find `oracleApmTraceId`.
3. The value is hyperlinked to APM Trace Explorer with that
   `trace_id` pre-filled (this is the drilldown you registered when
   you applied the saved searches).

That's the round trip: APM → LA → APM, in two clicks.

### 5. Try a richer query

The same saved search supports advanced filtering. Try:

```
'Log Source' = 'octo-shop-app-json'
  | where oracleApmTraceId = '<TRACE_ID>'
  | stats count() by level
```

If your request only emitted `INFO` logs, you'll see one row. If a
`WARN` or `ERROR` slipped in (failure-injection traffic, perhaps), the
breakdown shows up.

## Verify

```bash
./tools/workshop/verify-02.sh "$TRACE_ID"
```

Expected:

```
✓ trace_id valid format
✓ Log Analytics returned ≥ 1 record for trace_id
✓ records include oracleApmTraceId field
✓ records include workflow_id=workshop-lab-02
PASS — Lab 02 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| LA query returns 0 rows after 3 min | Service Connector not running | Check Console → Logging → Service Connectors → `la-pipeline-octo-shop-app` (created by `deploy/terraform/main.tf::la_pipeline_app_logs`) |
| `oracleApmTraceId` is empty in records | App's correlation shim not stamping | Verify `shop/server/observability/correlation.py` is enriching the logging adapter; restart pod |
| LA records have no `workflow_id` | App middleware doesn't propagate the header | Check the `X-Workflow-Id` request middleware in `shop/server/main.py` |

## Read more

- [Tools → la-saved-searches/](https://github.com/adibirzu/octo-apm-demo/tree/main/tools/la-saved-searches)
- [Architecture → Correlation Contract](../architecture/correlation-contract.md)
- [Observability → Cross-Service Tracing](../observability/distributed-traces.md)

---

[← Lab 01](lab-01-first-trace.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 03 → Slow SQL drill-down →](lab-03-slow-sql-drill-down.md)
