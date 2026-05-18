# Metrics

## HTTP RED Metrics (OpenTelemetry)

| Metric | Type | Labels |
|---|---|---|
| `shop.http.requests.total` | Counter | route, method, status_code |
| `shop.http.request.duration` | Histogram | route, method |
| `shop.http.requests.in_flight` | UpDownCounter | route, method |

## Business Metrics

| Metric | Type | Description |
|---|---|---|
| `shop.business.orders.created` | Counter | Orders placed |
| `shop.business.order.value` | Histogram | Order total (USD) |
| `shop.business.cart.additions` | Counter | Items added to cart |
| `shop.business.checkout.total` | Counter | Checkout attempts |
| `shop.business.checkout.failures` | Counter | Failed checkouts |
| `shop.business.auth.login` | Counter | Successful logins |
| `shop.business.security.events` | Counter | Security events detected |
| `shop.business.crm.sync` | Counter | CRM sync operations |

## OCI Monitoring Custom Metrics

Published every 60 seconds to OCI Monitoring namespace `octo_apm_demo`:

| Metric | Unit | Description |
|---|---|---|
| `app.health` | count | 1 = healthy, 0 = unhealthy |
| `app.uptime_seconds` | seconds | Process uptime |
| `app.requests.rate` | count | Requests per interval |
| `app.errors.rate` | count | 5xx errors per interval |
| `app.checkout.count` | count | Checkouts per interval |
| `app.orders.count` | count | Orders per interval |
| `app.db.latency_ms` | milliseconds | Last readiness check round-trip |
| `app.crm.sync_age_s` | seconds | Seconds since last CRM sync |
| `app.auth.success.count` | count | Admin successful logins per interval |
| `app.auth.failure.count` | count | Admin failed logins per interval |
| `app.security.events.count` | count | Admin security events per interval |
| `app.dashboard.loads.count` | count | Admin dashboard loads per interval |
| `app.order_sync.count` | count | Admin order sync operations per interval |
| `app.inventory.low_stock_products` | count | Products with stock < 10 |

## Prometheus Endpoint

```
GET /metrics
Content-Type: text/plain
```

Scrape-compatible with Grafana, Prometheus, or any OpenMetrics-compatible collector.
