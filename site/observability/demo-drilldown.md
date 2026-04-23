# OCI Observability Demo Drill-Down

One-page script for showing MELTS + Stack Monitoring drill-down against
the live `shop.octodemo.cloud` + `crm.octodemo.cloud` deployment.

## Pre-demo (30 s)

```bash
# Generate traffic so fresh trace/log/metric data lands during the walk-through
for i in {1..30}; do
    curl -sS -o /dev/null https://shop.octodemo.cloud/                      # dashboard
    curl -sS -o /dev/null https://shop.octodemo.cloud/shop                  # catalog
    curl -sS -o /dev/null https://shop.octodemo.cloud/api/products          # API
    curl -sS -o /dev/null https://shop.octodemo.cloud/api/platform/status   # cross-service aggregator
    sleep 1
done
```

## 1. Metrics drill-down (OCI Monitoring)

**Console path**: Observability & Management → Monitoring → Metrics Explorer

| Namespace | Metric | What it shows |
|---|---|---|
| `octo_drone_shop` | `app.health` | Rolling 0/1 heartbeat |
| `octo_drone_shop` | `app.requests.rate` | Req/60s published by the pod |
| `octo_drone_shop` | `app.errors.rate` | 5xx/60s |
| `octo_drone_shop` | `app.checkout.count` | Checkouts/min |
| `octo_drone_shop` | `app.orders.count` | Order creations/min |
| `octo_drone_shop` | `app.db.latency_ms` | ATP round-trip on `/ready` |
| `octo_drone_shop` | `app.crm.sync_age_s` | Seconds since last CRM sync |
| `octo_drone_shop` | `app.sessions.active` | Active session gauge |
| `octo_drone_shop` | `app.inventory.low_stock_products` | Products with stock < 10 |
| `oci_autonomous_database` | `CpuUtilization` | ATP CPU % |
| `oci_autonomous_database` | `CurrentLogons` | Active DB sessions |
| `oci_vcn` + `oci_oke_cluster` | built-in | Network + node health |

Query template:
```
octo_drone_shop/app.requests.rate[5m].mean()
```
Build an alarm on `app.errors.rate[5m].sum() > 5` → Notifications topic →
`octo-remediator` playbook (tier-gated auto-fix).

**Drill to a single trace**: in the Metrics panel, click the spike → 
"View related traces" → lands in APM Trace Explorer filtered to that
window.

## 2. Traces drill-down (OCI APM)

**Console path**: Observability & Management → APM → Trace Explorer

- Service: `octo-drone-shop-oke` and `enterprise-crm-portal`.
- Filter: `service.namespace = "octo"` to scope.
- Group-by: `http.route` to see per-endpoint latency distribution.
- Click a slow trace → timeline shows `HTTP GET /shop → sqlalchemy SELECT → httpx POST /api/orders → crm handler → ATP INSERT`.
- Every span carries `oracleApmTraceId` + `oracleApmSpanId` tags for
  cross-linking with Log Analytics.

**Typical demo flow**:
1. Filter `http.status_code >= 500` over last 15 min → 0 results (healthy).
2. Flip `service.name = octo-drone-shop-oke and operation = "POST /api/orders"` → order-creation histogram.
3. Pick the p99 trace → expand timeline → highlight the ATP span and
   click "Go to Log Analytics".

## 3. RUM drill-down (OCI APM → Real User Monitoring)

**Console path**: APM → Real User Monitoring → (web application: `octo-drone-shop-web`)

- Page views by URL, by country, by browser, by network type.
- Core Web Vitals: LCP, FID, CLS.
- Beacon → filter by `session_id` → full user journey.

The beacon JS is embedded in `shop/server/templates/base.html`; public
data key lands via the `octo-apm` K8s secret. Registration of the web
application is a one-time OCI Console step — see
[OBSERVABILITY-BOOTSTRAP.md §7a](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/OBSERVABILITY-BOOTSTRAP.md).

## 4. Logs drill-down (OCI Logging → Log Analytics)

**Console path**: Observability & Management → Logging → Search

- Log Group: `octo-apm-demo`
- Custom Logs: `octo-app`, `octo-chaos-audit`, `octo-security`.

**Trace → logs** correlation:
1. Copy the `oracleApmTraceId` from an APM span.
2. In Log Analytics, search `'oracleApmTraceId' = '<id>'` against source
   `octo-shop-app-json`.
3. Every log line produced during that request appears.

**Saved searches** (in `tools/la-saved-searches/`):
- `slow-checkout-spans.json` — checkout > p95 + their correlated logs
- `errors-by-route.json` — 5xx grouped by http.route over 1h
- `trace-to-logs.json` — one trace ID → all logs

## 5. Stack Monitoring (ATP)

**Console path**: Observability & Management → Stack Monitoring → Monitored Resources → Autonomous Databases

- Resource: `octo-apm-demo-atp` (registered by
  `deploy/terraform/modules/stack_monitoring`).
- Tabs: Overview, Metrics, Health History, Events, Alerts.
- **Demo click**: SQL Performance → Top SQL tab → expand one statement →
  `EXPLAIN PLAN` + wait event breakdown.

**Cross-drill**: from a shop pod trace in APM → click the DB span →
Stack Monitoring loads the session with execution stats. This is the
magic moment — one click spans three services.

## 6. Events → Remediation

**Console path**: Observability → Events → Rules

- Rule `octo-alarm-5xx-burst` fires on Monitoring alarm `app.errors.rate > 5 for 5m`.
- Action: publish to Notifications topic `octo-alarms`.
- Subscriber: `octo-remediator` pod (HTTP endpoint).
- Remediator runs tier-gated playbook:
  - LOW → auto-apply
  - MEDIUM → wait for confirmation in Slack
  - HIGH → page on-call

Demo: `curl -X POST https://shop.octodemo.cloud/api/admin/chaos/apply \
  -d '{"scenario_id":"payment-timeout"}'` → watch remediator react.

## 7. End-to-end scenario — "slow checkout"

1. User reports `/checkout` is slow.
2. APM Trace Explorer → filter `http.route = "POST /api/orders" and duration > 2000ms`. One trace.
3. Timeline shows 1.8 s spent in the `sqlalchemy SELECT customers` span.
4. Click "Go to Stack Monitoring for this DB".
5. SQL Performance → the offending SELECT is listed with `cpu_time_delta = 1.7s` and wait event `latch free`.
6. Stack Monitoring's Advisor recommends an index on `customers.email`.
7. Remediator playbook `create-index-customers-email` runs (LOW tier, auto-approved) after a one-line Slack confirmation.
8. Metrics Explorer: `app.requests.rate` unchanged, `app.errors.rate`
   flat, but the `oci_autonomous_database/CpuUtilization` drops by 30 %.

That's the 5-minute demo.

## Where everything lives

| Signal | Publisher | Endpoint | Code |
|---|---|---|---|
| Traces | App → OTel SDK → `octo-otel-gateway` → OCI APM | `https://<apm-domain>.apm-agt.<region>.oci.oraclecloud.com` | `shop/server/observability/otel_setup.py` |
| Metrics | App → MonitoringClient | `https://telemetry-ingestion.<region>.oraclecloud.com` **(WRITE — not `telemetry.*`, see KB-456)** | `shop/server/observability/oci_monitoring.py` |
| Logs | App → LoggingIngestionClient | `https://ingestion.logging.<region>.oci.oraclecloud.com` | `shop/server/observability/logging_sdk.py` |
| RUM | Browser → RUM beacon | `https://<apm-domain>.apm-agt.<region>.oci.oraclecloud.com` | `shop/server/templates/base.html` |
| Stack Monitoring | OCI-managed (ATP auto-reports) | n/a | `deploy/terraform/modules/stack_monitoring` |

## Reset between demos

```bash
# Flush accumulated order rows + chaos state, then re-seed products.
kubectl exec -n octo-drone-shop deploy/octo-drone-shop -- \
    python -c "from server.database import reset_demo_data; reset_demo_data()"
```
