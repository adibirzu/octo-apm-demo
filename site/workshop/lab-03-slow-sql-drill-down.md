# Lab 03 — Find a slow SQL from an APM span

## Objective

Start at an APM span that crosses 500 ms, identify the SQL it
executed, and pivot into OCI DB Management to inspect the database
session that ran it.

## Time budget

30 minutes.

## Prerequisites

- Labs 01-02 complete.
- ATP DB Management enabled (Console → ATP → Tools → Database
  Management → Enable).
- OPSI enabled (Console → ATP → Tools → Operations Insights → Enable).

## Steps

### 1. Trigger a slow query

The shop has a test endpoint that intentionally executes a heavy query
to give you something visible:

```bash
TRACEPARENT="00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01"
TRACE_ID=$(echo "$TRACEPARENT" | cut -d- -f2)

curl -sS \
    -H "traceparent: $TRACEPARENT" \
    -H "X-Workflow-Id: workshop-lab-03" \
    "https://drone.octodemo.cloud/api/products?slow=true&category=drones" | jq '.[0:3]'

echo "trace_id: $TRACE_ID"
```

`?slow=true` adds a `pg_sleep`-like delay in the SQL path. The shop's
SQLAlchemy instrumentation tags the resulting span with the SQL text.

### 2. Open the trace in APM

Console → APM → Trace Explorer → `TraceId = '<TRACE_ID>'`.

In the flame chart you should see a span like
`SELECT FROM products WHERE category = ?` with **Duration > 500 ms**.

### 3. Read the SQL and the DbOracleSqlId

Click the slow span. In the right pane, look at attributes:

- `db.statement` — the literal SQL text.
- `db.oracle.sql_id` (a.k.a. `DbOracleSqlId`) — Oracle's stable hash
  for this SQL. This is the join key into DB Management + OPSI.

Copy the `DbOracleSqlId` value (e.g. `0a1b2c3d4e`).

### 4. Pivot to DB Management

Console → ATP → Tools → **Database Management → Performance Hub →
SQL Tuning Advisor**.

In the search box, paste your `DbOracleSqlId`. You'll see:

- Average elapsed time
- Buffer gets
- A profile of how often the SQL has run
- An **Explain Plan** with cost breakdown

If DB Management has been collecting for a while and the SQL is
genuinely slow, the **SQL Tuning Advisor** card may have an
optimization recommendation.

### 5. Pivot to OPSI

Console → ATP → Tools → **Operations Insights → SQL Warehouse**.

OPSI keeps long-term history of every SQL_ID. Filter by your SQL_ID
and look at the **trend** chart: is this SQL getting slower week-over-
week, or did it spike just now?

### 6. (Optional) Cross-reference with Log Analytics

```
'Log Source' = 'octo-shop-app-json'
  | where db.oracle.sql_id = '<SQL_ID>'
  | sort -Duration
  | head limit = 20
```

Every shop log record that emitted that SQL is listed, ordered by the
HTTP request duration. Useful when the same SQL fires from multiple
routes.

## Verify

```bash
./tools/workshop/verify-03.sh "$TRACE_ID"
```

Expected:

```
✓ trace contains a span with db.system=oracle
✓ slow span duration > 500 ms
✓ slow span has db.oracle.sql_id attribute
PASS — Lab 03 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Span has no `db.statement` | SQLAlchemy instrumentation not active | Verify `OTEL_PYTHON_INSTRUMENTATION_ENABLED=true` in pod env; the shop's `otel_setup.py` calls `SQLAlchemyInstrumentor().instrument()` on startup |
| `DbOracleSqlId` missing | Oracle session tagging off | Check `shop/server/observability/correlation.py::set_oracle_session_tags()` runs on every request; tags are what make APM ↔ DB Management join work |
| DB Management has no data for the SQL_ID | DB Mgmt collection lag | Recent SQL_IDs need ~5 min before the Performance Hub picks them up |

## Read more

- [Observability → Cross-Service Tracing](../observability/distributed-traces.md)
- [Stack Monitoring + ATP](../observability-v2/stack-monitoring.md)
- [Oracle DB Management docs](https://docs.oracle.com/en-us/iaas/database-management/)

---

[← Lab 02](lab-02-trace-log-correlation.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 04 → RUM outage detection →](lab-04-rum-outage-detection.md)
