# Lab 07 — Build a Log Analytics saved search

## Objective

Author a Log Analytics saved search that answers a business question
("how many checkouts failed in the last hour by reason"), pin it to a
dashboard widget, and parameterize it.

## Time budget

35 minutes.

## Prerequisites

- Lab 02.
- Authority to create saved searches in the LA namespace.

## Steps

### 1. Iterate the query in Search

Console → Logging Analytics → Search.

Start broad:

```
'Log Source' = 'octo-shop-app-json' and route = '/api/orders'
```

Narrow to failures:

```
'Log Source' = 'octo-shop-app-json'
  and route = '/api/orders'
  and http_status >= 400
```

Group by reason:

```
'Log Source' = 'octo-shop-app-json'
  and route = '/api/orders'
  and http_status >= 400
  | stats count() by http_status, error
  | sort -count
```

### 2. Generate some failures so the result is non-empty

```bash
# 5 valid orders, 5 invalid
for i in 1 2 3 4 5; do
    curl -sS -X POST https://shop.example.tld/api/orders \
        -H "Content-Type: application/json" \
        -d '{"customer_id":1,"items":[{"product_id":1,"quantity":1,"unit_price":1.0}]}' > /dev/null
    curl -sS -X POST https://shop.example.tld/api/orders \
        -H "Content-Type: application/json" \
        -d '{"customer_id":0,"items":[]}' > /dev/null
done
```

Wait 90 s for ingestion, re-run the query. You should see 5 rows like
`http_status=400 error=invalid_payload count=5`.

### 3. Save it

In Search, top right: **Save → Save as Saved Search**.

| Field | Value |
|---|---|
| Name | `octo-failed-checkouts-by-reason` |
| Display name | `OCTO — failed checkouts by reason (last 1h)` |
| Description | `5xx + 4xx breakdown for /api/orders. Used by Operations dashboard.` |
| Widget Type | BAR_CHART |

Save.

### 4. Same thing, declarative

Saved searches are JSON. Drop a file in
`tools/la-saved-searches/failed-checkouts.json`:

```json
{
  "name": "octo-failed-checkouts-by-reason",
  "displayName": "OCTO — failed checkouts by reason (last 1h)",
  "description": "5xx + 4xx breakdown for /api/orders. Used by Operations dashboard.",
  "queryString": "'Log Source' = 'octo-shop-app-json' and route = '/api/orders' and http_status >= 400 | stats count() by http_status, error | sort -count",
  "widgetType": "BAR_CHART"
}
```

Then `tools/la-saved-searches/apply.sh` upserts it. The advantage of
the declarative form: it's reviewable in PRs and travels with the
repo.

### 5. Parameterize for a dashboard

Replace the time window with a parameter so the dashboard widget can
control it:

```
'Log Source' = 'octo-shop-app-json'
  and route = '/api/orders'
  and http_status >= 400
  and Time > dateTime(${start_time})
  and Time < dateTime(${end_time})
  | stats count() by http_status, error
```

When you pin this saved search to a dashboard widget, the widget
controls `${start_time}` and `${end_time}` from the dashboard's time
picker.

### 6. Pin to the operations dashboard

Console → Dashboards → **Create Dashboard** (or open an existing one).
Click **+ → Add Widget → From Saved Search → octo-failed-checkouts-by-reason**.

Set widget refresh: 60 s. Save.

## Verify

```bash
./tools/workshop/verify-07.sh
```

Expected:

```
✓ saved search 'octo-failed-checkouts-by-reason' exists
✓ saved search returns rows in the last 1h
✓ saved search includes http_status as a grouped column
PASS — Lab 07 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Query returns 0 rows | Ingestion lag or wrong source name | Confirm `'Log Source' = 'octo-shop-app-json'` matches what `tools/create_la_source.py` registered |
| `error` field missing | App not setting it | Check the shop's exception handler — it should attach `error="invalid_payload"` to the log record on 4xx |
| Save button disabled | Missing `LogAnalyticsAdmin` policy | Grant `LOG_ANALYTICS_SAVED_SEARCH_CREATE` on the namespace |

## Read more

- [LA Saved Searches reference](https://docs.oracle.com/en-us/iaas/logging-analytics/doc/saved-searches.html)
- [Observability v2 → Log Analytics dashboards](../observability-v2/log-analytics-dashboards.md)

---

[← Lab 06](lab-06-waf-event-investigation.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 08 → Stack Monitoring + ATP →](lab-08-stack-monitoring-atp.md)
