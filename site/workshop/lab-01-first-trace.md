# Lab 01 — Your first trace

## Objective

Generate one HTTP request, find its trace in OCI APM, and read what it
contains.

## Time budget

20 minutes.

## Prerequisites

- Platform deployed and reachable (see [workshop intro](index.md#prerequisites-checklist)).

## Steps

### 1. Generate a request

```bash
TRACEPARENT="00-$(openssl rand -hex 16)-$(openssl rand -hex 8)-01"
echo "traceparent we'll inject: $TRACEPARENT"

curl -sS \
    -H "traceparent: $TRACEPARENT" \
    -H "X-Workflow-Id: workshop-lab-01" \
    https://shop.example.tld/api/products | jq '.[0]'
```

The `traceparent` header is the W3C standard the shop's OTel SDK reads.
By generating it ourselves, we know the exact 32-hex `trace_id` to
search for. Extract it:

```bash
TRACE_ID=$(echo "$TRACEPARENT" | cut -d- -f2)
echo "trace_id: $TRACE_ID"
```

### 2. Find the trace in OCI APM (Console)

1. Open OCI Console → **Observability & Management → Application
   Performance Monitoring → Trace Explorer**.
2. Pick the APM Domain (`octo-apm`).
3. In the search bar, paste:
    ```
    TraceId = '<your trace_id>'
    ```
4. Click **Run query**. The trace appears within ~30 s of the request.

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

- The root span shows total wall-clock time.
- Child spans are nested by parent-id; widths show their share of the
  total.
- Click any span to see its **attributes**: `service.name`, `http.method`,
  `http.route`, `db.system`, `db.statement`.

The `service.name` should be `octo-drone-shop`. The
`http.route` should be `/api/products`. If the trace has a `peer.service`
attribute pointing at `enterprise-crm-portal`, you generated a request
that crossed the cross-service boundary — useful for the next lab.

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
