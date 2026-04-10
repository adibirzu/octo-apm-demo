# OCTO Drone Shop Technical Architecture

## Runtime topology

```
                    ┌─────────────┐
                    │  Browser    │
                    │  (RUM)      │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  OCI WAF    │  detection mode
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  OCI LB     │  flexible shape, TLS termination
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐ ┌─────▼─────┐ ┌───▼──────────┐
     │ Python App │ │ Workflow  │ │ OCI API      │
     │ (FastAPI)  │ │ Gateway   │ │ Gateway      │
     │ 98 routes  │ │ (Go)      │ │ (optional)   │
     └─────┬──────┘ └─────┬─────┘ └──────────────┘
           │              │
           │    ┌─────────┘
           │    │
     ┌─────▼────▼────┐
     │  Oracle ATP    │  shared with CRM
     │  (wallet auth) │
     └───────┬────────┘
             │
    ┌────────┴─────────────────┐
    │                          │
┌───▼────────┐  ┌──────────────▼──────────┐
│ DB Mgmt    │  │ Operations Insights     │
│ Perf Hub   │  │ SQL Warehouse           │
└────────────┘  └─────────────────────────┘
```

### Cross-service integration

```
Drone Shop ◄──── W3C traceparent ────► Enterprise CRM
     │                                       │
     │   /api/integrations/crm/*             │  /api/integrations/drone-shop/*
     │   (customer sync, order sync,         │  (simulation proxy,
     │    enrichment, health)                │   service-key auth)
     │                                       │
     └─────────► Oracle ATP ◄────────────────┘
                (shared instance)
```

### IDCS SSO flow

```
Browser → /api/auth/sso/login → IDCS /oauth2/v1/authorize (PKCE S256)
     ◄── redirect with code ──
Browser → /api/auth/sso/callback → IDCS /oauth2/v1/token
     → verify ID token via JWKS (/admin/v1/SigningCert/jwk)
     → upsert local user → issue HMAC bearer token → httpOnly cookie
```

## Services

| Service | Tech | Routes | Backend |
|---|---|---|---|
| Drone Shop | Python/FastAPI | 98 | Oracle ATP |
| Workflow Gateway | Go | ~15 | Oracle ATP |
| Enterprise CRM | Python/FastAPI | ~80 | Oracle ATP (shared) |
| Ops Portal | Python/FastAPI | ~40 | N/A (proxies to other services) |

## Data model

### Core tables
- `users`, `products`, `customers`, `orders`, `order_items`, `shops`

### Sales
- `cart_items`, `reviews`, `coupons`, `shipments`, `warehouses`

### Marketing
- `campaigns`, `leads`

### Operations
- `page_views`, `audit_logs`, `security_events`
- `services`, `tickets`, `ticket_messages`

### AI assistant
- `assistant_sessions`, `assistant_messages`

### Workflow gateway
- `workflow_runs` — scheduled and manual workflow refresh runs
- `query_executions` — SQL execution history (including intentional failures for investigation)
- `component_snapshots` — backend component health rollups

## Observability stack (MELTS)

### Metrics

| Source | Destination | What |
|---|---|---|
| Prometheus `/metrics` | Grafana / scraper | HTTP RED, business KPIs, runtime |
| OCI Monitoring SDK | OCI Monitoring (`octo_drone_shop` namespace) | app.health, requests.rate, errors.rate, checkout.count, orders.count, db.latency_ms, crm.sync_age_s |
| OCI Alarms | OCI Notifications → email/webhook | Error rate > 5/min, DB p95 > 2s, health down, CRM sync stale |
| OCI Health Checks | OCI Console | HTTP `/ready` every 30s |

### Events

| Event type | How generated | Where visible |
|---|---|---|
| Security spans | 19 MITRE ATT&CK types (`security_span()`) | APM → filter `security.vuln_type` |
| Span error events | 4xx → `http.client_error` event; 5xx → ERROR status | APM → Error Analysis |
| OCI Alarms | MQL queries on custom metrics | Monitoring → Alarms |

### Logs

| Log source | Destination | Correlation key |
|---|---|---|
| App structured logs | OCI Logging SDK → OCI Logging | `oracleApmTraceId`, `trace_id`, `span_id`, `correlation.id` |
| App structured logs | Splunk HEC (optional) | Same fields |
| LB access logs | OCI Logging (manual enable) | Request ID |
| WAF logs | OCI Logging (manual enable) | Request ID |
| Log Analytics | OCI Log Analytics | `oracleApmTraceId` JOIN with APM traces |

### Traces

| Instrumentation | Span examples | Attributes |
|---|---|---|
| FastAPI middleware | Every HTTP request | method, route, status, duration_ms, client_ip, correlation.id |
| SQLAlchemy | Every SQL query | db.statement, db.client.execution_time_ms, db.row_count, DbOracleSqlId |
| httpx | Every outbound HTTP (CRM calls) | W3C traceparent, peer.service |
| Custom spans | 50+ across 13 modules | Domain-specific (shop.checkout, auth.login, shipping.get, etc.) |
| Oracle session tags | Per-connection | MODULE, ACTION, CLIENT_IDENTIFIER=trace_id |
| SSO spans | Login initiate, callback | auth.method, auth.idcs.domain |

### Security

| Control | Implementation |
|---|---|
| CORS | Strict origin list from `DNS_DOMAIN`, no wildcard, no credentials with `*` |
| Auth | HMAC-SHA256 bearer tokens; `AUTH_TOKEN_SECRET` required in production |
| SSO | IDCS OIDC + PKCE (S256), JWKS-verified RS256 ID tokens |
| Simulation auth | `require_sso_user` OR `X-Internal-Service-Key` |
| WAF | OCI WAF in detection mode on the Load Balancer |
| Secrets | All via K8s Secrets or env vars; no hardcoded values |

## RUM (Real User Monitoring)

- OCI APM RUM beacon injected via `base.html` when `rum_configured=True`
- Custom RUM events emitted from `shop.html`:
  - `shop.add_to_cart` — product_id, name, price, category, cart_size
  - `shop.checkout_start` — cart_items, cart_total, session_id
  - `shop.checkout_complete` — order_id, total, tracking_number
  - `shop.checkout_error` — error message, cart_items
  - `shop.search` — query, category, sort
  - `shop.page_loaded` — load_time_ms, product count, cart items

## APM topology

When all services are deployed, OCI APM Topology shows:

```
Browser (RUM) → Drone Shop → Oracle ATP
                    ├──→ Enterprise CRM → Oracle ATP
                    └──→ IDCS (SSO login spans)
```

Each edge is a real W3C traceparent-propagated distributed trace. Clicking an edge in APM Topology shows the specific spans crossing that boundary.

## Testing infrastructure

| Test type | Tool | Test count | What it covers |
|---|---|---|---|
| E2E | Playwright | 237 | Health, shopping, cross-service, MELTS, auth, simulation, availability, k6 |
| Load (shop-only) | k6 | 4 scenarios | Browse, API load, geo-latency, security probes |
| Load (cross-service) | k6 | 5 scenarios | Shop+CRM browse, API, distributed traces, checkout, observability |
| Load (DB stress) | k6 | 6 scenarios | Bulk writes, aggregations, N+1, slow queries, checkout storms, CRM sync |

All k6 tests accept `DNS_DOMAIN` and `PROFILE` (light/moderate/heavy) environment variables.

## Validation checklist

- [ ] `/ready` returns `database: connected` and `db_type: oracle_atp`
- [ ] `/api/shop/storefront` shows `backend.database = oracle_atp`
- [ ] `/api/shop/checkout` creates rows in `orders`, `order_items`, `shipments`, `audit_logs`
- [ ] `/api/auth/sso/status` returns `configured: true` (if IDCS is set)
- [ ] `/api/observability/360` returns all pillar statuses
- [ ] `/api/integrations/crm/health` returns `crm_configured: true`
- [ ] OCI APM shows distributed traces spanning Shop → CRM → ATP
- [ ] OCI APM Topology shows edges between all services
- [ ] OCI APM RUM shows shop.add_to_cart and shop.checkout events
- [ ] OCI Log Analytics: `oracleApmTraceId=<trace_id>` returns correlated logs
- [ ] OCI Monitoring: `octo_drone_shop` namespace has metrics
- [ ] OCI DB Management Performance Hub shows SQL from the app
- [ ] `npm run test:e2e` passes all 237 tests
- [ ] `k6 run --env DNS_DOMAIN=<domain> k6/cross_service_stress.js` completes without threshold violations
