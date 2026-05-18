---
title: Lab 01 — Your first trace
description: Generate one HTTP request, find its trace in OCI APM, and read what it contains. The foundation lab — every later lab assumes you can do this.
---

# Lab 01 — Your first trace

## Objective

Generate one HTTP request, find its trace in OCI APM, and read what it
contains. This is the foundation lab — every later lab assumes you can
follow a request from the browser into APM, find it, and explain what
each span represents.

## Time budget

20 minutes (first time). 5 minutes once you've done it once.

## Prerequisites

- Platform deployed and reachable (see [workshop intro](index.md#prerequisites-checklist)).
- The pre-flight `/ready` check returned `apm_configured: true` on both
  shop and admin endpoints.
- You know your APM Domain OCID — find it in *OCI Console → Observability
  & Management → APM → Administration → Domain Details*.

## What you'll learn

- How W3C trace context (`traceparent` header) flows from any HTTP client
  into the FastAPI server and out to downstream services.
- How to find a specific trace in OCI APM Trace Explorer.
- How to read a flame chart: parent/child relationships, span duration,
  span attributes.
- The naming convention this platform uses for span attributes
  (`service.name`, `service.namespace`, `service.instance.id`).

## Steps

!!! tip "Personalize the commands"
    The **Configure your deployment** panel at the top of this page lets
    you replace `example.tld`, `${DNS_DOMAIN}`, and `<COMPARTMENT_OCID>`
    with your real values everywhere on this page. Open it once and the
    `curl` commands below become directly copy-pasteable.

### 1. Generate a request

We'll mint our own W3C `traceparent` header so we know the exact 32-hex
trace ID to look for later. This makes the lab deterministic — no
guessing which trace was yours among the hundreds the traffic generator
produces.

```bash
# Mint a fresh traceparent: version-traceId-spanId-flags
TRACEPARENT="00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01"
echo "traceparent we'll inject: $TRACEPARENT"

curl -sS \
    -H "traceparent: $TRACEPARENT" \
    -H "X-Workflow-Id: workshop-lab-01" \
    https://drones.example.tld/api/products | jq '.[0]'
```

**Expected response shape:**

```json
{
  "id": "drone-xyz",
  "name": "Carbon Fiber Recon",
  "price": 1299.0,
  "category": "tactical",
  "in_stock": true
}
```

If you got HTTP 200 + a JSON product object, the request succeeded and
APM has begun ingesting your span. ✓

The `traceparent` header is the W3C standard the shop's OTel SDK reads.
By generating it ourselves, we know the exact 32-hex `trace_id` to
search for. Extract it:

```bash
TRACE_ID=$(echo "$TRACEPARENT" | cut -d- -f2)
echo "trace_id: $TRACE_ID"
```

### 2. Find the trace in OCI APM (Console)

1. Open **OCI Console → Observability & Management → Application
   Performance Monitoring → Trace Explorer**.
2. Pick your APM Domain (typically `<DEPLOYMENT_PREFIX>-apm-domain`).
3. In the query bar, paste:
   ```
   TraceId = '<your trace_id>'
   ```
4. Click **Run query**. The trace appears within ~30 seconds of the
   request (OCI APM ingestion SLA is 1–2 minutes).

**What you should see** — a Trace Explorer screen similar to this (top
nav blurred + tenancy chips redacted to keep the image publishable):

![Trace Explorer with a single trace result](../assets/screenshots/oci/apm-01-trace-explorer-result.png)

The single matched row should show:

- **Operation**: `GET /api/products`
- **Service**: `octo-drone-shop`
- **Status**: HTTP 200
- **Duration**: 20-150 ms (varies with cold-start)
- **Span count**: 3-5 (FastAPI server span + SQLAlchemy spans + maybe a
  cache lookup)

### 3. Find the trace in OCI APM (CLI)

```bash
oci apm-traces trace get \
    --apm-domain-id "$OCI_APM_DOMAIN_ID" \
    --trace-key "$TRACE_ID" \
    --query 'data.{spans: spans[*].operationName, duration: "duration-in-ms"}' \
    | jq
```

You should see at least three spans:

- `GET /api/products` (FastAPI route)
- `SELECT FROM products …` (SQLAlchemy span)
- `traffic.session` if the traffic generator was running concurrently
  on a separate trace — ignore it for now.

### 4. Read the trace

In the Console UI, click the trace row to open the **flame chart**.

- The **root span** shows total wall-clock time end-to-end
- Child spans are nested by parent ID; widths show their share of the total
- Click any span to see its **attributes** in the right-hand panel

**Key attributes on the root span:**

| Attribute | Expected value | Why it matters |
|---|---|---|
| `service.name` | `octo-drone-shop` | Identifies which service produced the span |
| `service.namespace` | `octo` | Logical grouping for cross-service search |
| `service.instance.id` | pod/container/VM identifier | Lets you pivot to that instance's logs |
| `http.method` | `GET` | HTTP verb |
| `http.route` | `/api/products` | FastAPI route template (not the full URL) |
| `http.status_code` | `200` | Response status |

**On the database child span (SQLAlchemy):**

| Attribute | Expected value |
|---|---|
| `db.system` | `oracle` (or `postgresql` on local stack) |
| `db.statement` | `SELECT ... FROM products WHERE ...` |
| `db.sql_id` | Oracle SQL_ID hash (only on ATP) |

**The platform's correlation contract** says every log record emitted
during this request will share the same `oracleApmTraceId` value as the
trace's root `trace_id`. We'll exercise that in Lab 02.

**Flame chart view:** click the matched trace and the per-trace flame
chart opens, showing the FastAPI server span as the root and nested
SQLAlchemy / Java sidecar spans as children:

![Flame chart for one trace](../assets/screenshots/oci/apm-02-flame-chart.png)

**Span attributes:** click any span in the flame chart to open the
right-hand attributes panel. The attributes panel reveals
`service.name`, `service.namespace`, `http.route`, `db.statement`,
`oracleApmTraceId`, and the other fields documented in the architecture
correlation contract:

![Span attribute detail panel](../assets/screenshots/oci/apm-03-span-attributes.png)

If the trace has a `peer.service` attribute pointing at
`enterprise-crm-portal`, you generated a request that crossed the
cross-service boundary — useful for the next lab.

## Verify

```bash
./tools/workshop/verify-01.sh "$TRACE_ID"
```

Expected output:

```
✓ trace_id format valid (32 hex)
✓ trace appears in APM (HTTP 200)
✓ at least one span has service.name=octo-drone-shop
✓ at least one span has http.route=/api/products
PASS — Lab 01 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Trace not in APM after 60 s | OCI APM ingestion lag | Wait another 60 s; OCI APM SLA is 1–2 min for first appearance |
| `oci apm-traces trace get` returns 404 | Wrong APM Domain ID | `oci apm-control-plane apm-domain list --compartment-id $C --query 'data[].{name:"display-name", id:id}'` |
| Trace has only one span | OTel auto-instrumentation off | Check the shop pod env: `kubectl exec -n octo-drone-shop <pod> -- env | grep OCI_APM_ENDPOINT` — must be set |

## Read more

- [Architecture → Correlation Contract](../architecture/correlation-contract.md)
- [Observability → Traces (APM)](../observability/traces.md)
- [W3C Trace Context spec](https://www.w3.org/TR/trace-context/)

---

[Next: Lab 02 → Trace ↔ Log correlation](lab-02-trace-log-correlation.md)
