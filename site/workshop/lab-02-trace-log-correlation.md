---
title: Lab 02 — Trace ↔ Log correlation
description: Pivot from a single APM trace to every log record emitted during that request, using oracleApmTraceId as the join key. The bread-and-butter operator workflow.
---

# Lab 02 — Trace ↔ Log correlation

## Objective

Take an APM trace_id, find the matching log records in Log Analytics,
and learn the round-trip click path operators use during incidents.
This is the bread-and-butter workflow — every later lab assumes you
can move between APM spans and Log Analytics rows in one click.

## Time budget

30 minutes.

## What you'll learn

- How `oracleApmTraceId` ties APM spans to Log Analytics rows
- The Log Analytics search syntax for cross-referencing traces
- The platform's pre-shipped saved searches for common correlation
  scenarios (auth, payment, workflow, connector coverage)
- How detection rules consume the same correlation contract

## Prerequisites

- Lab 01 complete (you know how to find a trace in APM Trace Explorer).
- Log Analytics source `SOC Application Logs` registered for direct/OKE app
  rows. In the private demo profile, Connector Hub rows from OCI Logging
  appear as `OCI Unified Schema Logs`; use `connector-live-log-coverage.sql`
  for that path.
- Saved searches deployed (`tools/la-saved-searches/apply.sh`).

## Steps

### 1. Generate a request and capture the trace_id

```bash
TRACEPARENT="00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01"
TRACE_ID=$(echo "$TRACEPARENT" | cut -d- -f2)

curl -sS \
    -H "traceparent: $TRACEPARENT" \
    -H "X-Workflow-Id: workshop-lab-02" \
    https://shop.example.tld/api/products?category=drones | jq '.[0:3]'

echo "trace_id: $TRACE_ID"
```

### 2. Wait for ingestion, then query Log Analytics (Console)

OCI Logging → Service Connector → Log Analytics ingestion typically
lands within 60 s.

1. Open **OCI Console → Observability & Management → Logging
   Analytics → Search** (also called Log Explorer).
2. Run the saved search you deployed:
    ```
    'Log Source' = 'SOC Application Logs' and 'Trace ID' = '<TRACE_ID>'
    ```
3. You should see one row per log record the shop emitted while
   processing your request. The `oracleApmTraceId` column is the join
   key; click any row to open its full JSON payload.

**Where this lands in APM Trace Explorer first** — the same `trace_id`
returns a single row that looks like:

![Trace Explorer with one result](../assets/screenshots/oci/apm-01-trace-explorer-result.png)

**The flame chart** shows you exactly how many spans are involved.
Every span in this flame chart will produce 1+ log records in Log
Analytics — that's what step 2 above retrieves:

![Flame chart](../assets/screenshots/oci/apm-02-flame-chart.png)

**Each span exposes its `oracleApmTraceId` in the attributes panel**.
This is the field that joins APM ↔ Log Analytics:

![Span attribute panel showing oracleApmTraceId](../assets/screenshots/oci/apm-03-span-attributes.png)

### 3. Query Log Analytics from the CLI

```bash
oci log-analytics query \
    --namespace-name "$LA_NAMESPACE" \
    --query-string "'Log Source' = 'SOC Application Logs' and 'Trace ID' = '$TRACE_ID' | head limit = 10" \
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
'Log Source' = 'SOC Application Logs'
  and 'Trace ID' = '<TRACE_ID>'
  | stats count() by level
```

If your request only emitted `INFO` logs, you'll see one row. If a
`WARN` or `ERROR` slipped in (failure-injection traffic, perhaps), the
breakdown shows up.

### 6. Detection rules use the same correlation contract

The platform ships **Logging Analytics detection rules** that fire when
specific patterns (auth anomalies, payment-rail timeouts, attack-lab
signatures) appear in log streams. Because every detection consumes the
same field schema you just queried, you can trace from a fired
detection back to the originating spans in two clicks.

Navigate to: **Logging Analytics → Detection Rules**:

![Detection rules list](../assets/screenshots/oci/loganalytics-04-detection-rules.png)

Click a rule (e.g. `auth-login-burst`) to see its query, its evaluation
schedule, and the dimensions it groups by. Every detection rule's query
is reproducible from the source SQL committed in
`deploy/oci/log_analytics/searches/`.

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
| LA query returns 0 rows after 3 min | Wrong ingestion path or connector issue | For OKE/direct app rows, run `service-trace-log-coverage.sql`. For OCI Logging connector rows, run `connector-live-log-coverage.sql` and check `OCI Unified Schema Logs`. |
| `oracleApmTraceId` is empty in records | App's correlation shim not stamping | Verify `shop/server/observability/correlation.py` is enriching the logging adapter; restart pod |
| LA records have no `workflow_id` | App middleware doesn't propagate the header | Check the `X-Workflow-Id` request middleware in `shop/server/main.py` |

## Read more

- [Tools → la-saved-searches/](%%GITHUB_REPO_URL%%/tree/main/tools/la-saved-searches)
- [Architecture → Correlation Contract](../architecture/correlation-contract.md)
- [Observability → Cross-Service Tracing](../observability/distributed-traces.md)

---

[← Lab 01](lab-01-first-trace.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 03 → Slow SQL drill-down →](lab-03-slow-sql-drill-down.md)
