---
title: API Reference
---

# API Reference

This document describes the HTTP APIs exposed by every service in `octo-apm-demo`.
It is reference-style: every endpoint, expected payload, authentication requirement, and
observability surface is listed by service.

For configuration of credentials and base URLs, see [CONFIGURATION.md](CONFIGURATION.md).
For service-level architecture and call paths, see [ARCHITECTURE.md](../ARCHITECTURE.md).

## A. API surface overview

Four HTTP services participate in the demo:

| Service | Path | Tech | Audience |
|---------|------|------|----------|
| Drone Shop storefront | `shop/server/` | FastAPI (Python 3.11) | Customers (SSO) + admin + service-to-service |
| Enterprise CRM | `crm/server/` | FastAPI (Python 3.11) | Admins only (SSO) + service-to-service |
| Java payment sidecar | `services/apm-java-demo/` | Spring Boot 3 (Java 17+) | Internal — called by Drone Shop |
| Workflow Gateway | `shop/services/workflow-gateway/` | Go (net/http) | Internal — proxied by Drone Shop, admin surface only |

### Authentication model

| Caller | Mechanism | Header / Cookie | Notes |
|--------|-----------|-----------------|-------|
| Customer (browser) | Oracle IDCS SSO → shop session cookie | `Cookie: session=…` | Established via `/api/auth/sso/login` → `/api/auth/sso/callback` |
| Admin (browser) | Oracle IDCS SSO → CRM admin session cookie | `Cookie: session=…` | Required for `/api/admin/*`, `/api/admin/coordinator/*` |
| Shop → CRM | Shared service key | `X-Internal-Service-Key: <secret>` | Compared with HMAC-safe equality |
| Shop → Java sidecar | None (cluster-internal) | Propagates `traceparent`, `X-Request-Id`, `X-Workflow-Id` | Network policy and service mesh enforce isolation |
| Shop → Workflow Gateway | Admin SSO + admin-surface host check | Same cookie + `Host` header | Public storefront refused with HTTP 403 |

### Cross-cutting response headers

When OCI APM tracing is enabled (`apm_configured: true` on `/ready`), every server response
carries:

- `traceparent` — W3C trace context (32-char trace ID + 16-char span ID)
- `tracestate` — vendor extensions, when propagated
- `X-Correlation-Id` — request correlation ID (echoes inbound when present, otherwise minted)

Log records emitted by each request carry `oracleApmTraceId` set to the active trace ID so
APM traces and Log Analytics entries correlate without an external join.

## B. Drone Shop API (`shop/server/`)

Public API base path: `/` on port `8080` by default. Routers below are mounted in
`shop/server/main.py`.

### B.1 Health & readiness

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | Liveness — returns `{status, service}` |
| `GET` | `/ready` | none | Readiness — runs `SELECT 1 FROM DUAL`, reports APM/RUM/logging config |
| `GET` | `/api/modules` | none | Module dependency graph (used by dashboards) |
| `GET` | `/api/version` | none | Build version & git SHA |
| `GET` | `/api/platform/status` | none | Aggregated platform health (downstream services) |
| `GET` | `/metrics` | none | Prometheus scrape endpoint |

`/ready` returns the following flags (`true`/`false`):
`ready`, `database`, `db_type`, `apm_configured`, `rum_configured`,
`logging_configured`, `java_apm_enabled`, `payment_gateway_simulation_enabled`,
`workflow_gateway_configured`, `selectai_configured`, `genai_configured`,
`llmetry_enabled`, `langfuse_configured`.

### B.2 Catalogue (`/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/products` | optional session | List products with filtering & pagination |
| `GET` | `/api/products/{product_id}` | optional session | Single product detail |
| `GET` | `/api/categories` | optional session | List categories |
| `GET` | `/api/products/{product_id}/reviews` | optional session | Reviews for a product |
| `POST` | `/api/products/{product_id}/reviews` | session required | Create review |

### B.3 Auth & SSO (`/api/auth`, `/api/auth/sso`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/login` | none | Local form login (demo only) |
| `GET` | `/api/auth/profile` | session | Current customer profile |
| `GET` | `/api/auth/sso/status` | none | Reports whether IDCS SSO is configured |
| `GET` | `/api/auth/sso/login` | none | Begin IDCS OAuth2 flow |
| `GET` | `/api/auth/sso/callback` | none | OAuth2 callback — sets session cookie |
| `GET` | `/api/auth/sso/logout` | session | Clear session, redirect to IDCS logout |

### B.4 Storefront & checkout (`/api/shop`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/shop/featured` | optional session | Featured products |
| `GET` | `/api/shop/storefront` | optional session | Full storefront snapshot |
| `POST` | `/api/shop/coupon/apply` | session | Apply coupon to cart |
| `POST` | `/api/shop/checkout` | session | Place order — see idempotency contract below |
| `GET` | `/api/shop/wallet` | session | Wallet balance |
| `GET` | `/api/shop/locations` | none | Store/pickup locations |
| `GET` | `/api/shop/app-server/health` | none | Probes Java sidecar health |
| `POST` | `/api/shop/app-server/simulate/{scenario}` | session | Forwarded simulation to Java sidecar |
| `POST` | `/api/shop/payment/simulate/{scenario}` | session | Synthetic payment scenarios |
| `POST` | `/api/shop/demo/storyboard` | session | Run a scripted purchase journey |
| `POST` | `/api/shop/attack/simulate` | admin | Synthetic attack-path generator |
| `GET` | `/api/shop/captcha` | none | Demo CAPTCHA token |
| `POST` | `/api/shop/captcha/verify` | none | Verify CAPTCHA token |
| `GET` | `/api/shop/assistant/history/{session_id}` | session | GenAI assistant transcript |
| `POST` | `/api/shop/assistant/query` | session | Submit prompt to GenAI assistant |

**Checkout idempotency contract** — `POST /api/shop/checkout` accepts an optional
`checkout_idempotency_key` (or `idempotency_key`) in the JSON body. Server-side it is
normalized by `normalize_checkout_idempotency_key`, then SHA-256 hashed; the first 16 hex
chars are emitted as the span attribute `orders.checkout_idempotency_key_hash`. The shop
also synthesises a deterministic UUID5 `idempotency_token` and forwards it to CRM in the
`POST /api/orders` body so retries do not create duplicate CRM invoices.

### B.5 Orders & cart (`/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/cart` | session | Current cart |
| `POST` | `/api/cart/add` | session | Add item to cart |
| `DELETE` | `/api/cart/{item_id}` | session | Remove cart line |
| `GET` | `/api/orders` | session | Customer order history |
| `GET` | `/api/orders/{order_id}` | session | Order detail |
| `POST` | `/api/orders` | session | Create order (server-side path) |

### B.6 Shipping (`/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/shipping` | session | Customer shipments |
| `GET` | `/api/shipping/{shipment_id}` | session | Shipment detail |
| `POST` | `/api/shipping/{shipment_id}/status` | session | Status update |
| `GET` | `/api/shipping/by-region` | session | Shipments aggregated by region |
| `GET` | `/api/shipping/warehouses` | session | Warehouse roster |

### B.7 Campaigns & analytics (`/api`, `/api/analytics`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/campaigns` | session | List campaigns |
| `GET` | `/api/campaigns/{campaign_id}` | session | Campaign detail |
| `POST` | `/api/campaigns` | admin | Create campaign |
| `GET` | `/api/campaigns/{campaign_id}/leads` | admin | Campaign leads |
| `POST` | `/api/campaigns/{campaign_id}/leads` | admin | Append lead |
| `GET` | `/api/analytics/overview` | session | Overview KPIs |
| `GET` | `/api/analytics/security/events` | admin | Recent security events |
| `GET` | `/api/analytics/security/correlations` | admin | Correlated security incidents |
| `GET` | `/api/analytics/geo` | session | Geo distribution |
| `GET` | `/api/analytics/funnel` | session | Funnel metrics |
| `POST` | `/api/analytics/track` | session | RUM-style event ingest |

### B.8 Dashboard (`/api/dashboard`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/dashboard/summary` | session | KPI summary |
| `GET` | `/api/dashboard/catalog` | session | Catalog mini-view |
| `POST` | `/api/dashboard/demo/customer` | admin | Seed demo customer |
| `POST` | `/api/dashboard/demo/company` | admin | Seed demo company |
| `POST` | `/api/dashboard/demo/orders` | admin | Seed demo orders |
| `POST` | `/api/dashboard/demo/sync-customers` | admin | Trigger CRM sync |
| `GET` | `/api/dashboard/slow-query` | session | Intentional slow SQL (demo) |
| `GET` | `/api/dashboard/n-plus-one` | session | Intentional N+1 (demo) |
| `GET` | `/api/dashboard/error-demo` | session | Intentional 500 (demo) |

### B.9 Admin proxies (`/api/admin`)

All routes here require an admin session.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/admin/users` / `POST` / `PUT /users/{user_id}` | User management |
| `GET` | `/api/admin/shops` / `POST` / `PUT /shops/{shop_id}` | Storefront config |
| `GET` | `/api/admin/products` / `POST` / `PUT /products/{product_id}` | Catalog management |
| `GET` | `/api/admin/customers` / `POST` / `PUT /customers/{customer_id}` | Customer admin |
| `GET` | `/api/admin/orders` / `POST` / `PUT /orders/{order_id}` | Order admin |
| `GET` | `/api/admin/invoices` / `POST` / `PUT /invoices/{invoice_id}` | Invoice admin |
| `GET` | `/api/admin/audit-logs` | Audit log feed |
| `GET` | `/api/admin/config` | Effective config snapshot |
| `GET`/`POST` | `/api/admin/assistant/history/{session_id}`, `/assistant/query` | Admin GenAI assistant |
| `POST` | `/api/admin/seed`, `/api/admin/reseed` | Demo data seeding |
| `POST` | `/api/admin/partners` | Partner provisioning |

### B.10 Workflow Gateway proxy (`/api/workflow-gateway`)

Single catch-all route:

```
GET|POST /api/workflow-gateway/{path:path}
```

The proxy:

1. Calls `require_admin_or_internal_service(request)` — admin session OR `X-Internal-Service-Key`.
2. For non-service principals, calls `_require_admin_surface_host(request)` which compares the
   request `Host` (or `X-Forwarded-Host`) against the allowed admin hostnames
   (`localhost`, configured `crm_public_hostname`, `admin.<dns_domain>`,
   `crm.<dns_domain>`). Requests from the public storefront host are rejected with `403`.
3. Restricts upstream paths to one of `api/workflows/`, `api/components/`,
   `api/query-lab/`, `api/selectai/`. Anything else returns `404`.
4. Forwards a small allow-list of headers: `authorization`, `content-type`,
   `traceparent`, `tracestate`, `x-correlation-id`, `x-request-id`, `x-session-id`,
   `x-internal-service-key`.
5. Caps the request body at 16 KiB and Select AI prompts at 1 000 characters.

### B.11 Observability dashboards (`/api/observability`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/observability/360` | session | 360 health snapshot |
| `GET` | `/api/observability/360/app-health` | session | App health card |
| `GET` | `/api/observability/360/db-health` | session | DB health card |
| `GET` | `/api/observability/360/security` | session | Security card |
| `GET` | `/api/observability/payment-gateway/events` | session | Payment event feed |
| `GET` | `/api/observability/capabilities` | none | Discovery — what trace, log, RUM features are wired |
| `GET` | `/api/observability/melts` | none | Metrics/Events/Logs/Traces inventory |

### B.12 Integrations with CRM (`/api/integrations`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/integrations/schema` | session | Schema graph |
| `GET` | `/api/integrations/crm/customer-enrichment` | session | Enrich customer via CRM call |
| `POST` | `/api/integrations/crm/sync-order` | session | Push order to CRM (`X-Internal-Service-Key` injected server-side) |
| `POST` | `/api/integrations/crm/sync-customers` | admin | Bulk customer sync |
| `GET` | `/api/integrations/crm/customers` | admin | Mirror of CRM customer list |
| `GET` | `/api/integrations/crm/ticket-products` | session | CRM ticket-linked products |
| `POST` | `/api/integrations/crm/catalog-sync` | admin | Push catalog to CRM |
| `GET` | `/api/integrations/crm/health` | none | CRM reachability probe |
| `GET` | `/api/integrations/status` | none | Integration topology summary |

### B.13 Other routers

- **Public API v1** — `GET /api/v1/public/*` (catalog, status; key-gated where applicable).
- **Partner API v1** — `GET /api/v1/partner/*` (requires partner API key).
- **Payments webhooks** — `POST /api/payments/webhooks/{provider_name}`.
- **Simulation** — `/api/simulate/configure|reset|db-latency|error-burst|status`.
- **Chaos read-only** — `GET /api/chaos/presets`, `GET /api/chaos/state`.
- **Synthetic users** — `POST /api/synthetic/users/run` (`X-Internal-Service-Key` required).
- **Services catalogue** — `GET /api/services/catalog`, tickets `GET|POST /api/services/tickets`.

## C. Enterprise CRM API (`crm/server/`)

Public API base path: `/` on port `8080` by default. All `/api/admin/*` and
`/api/admin/coordinator/*` routes require an admin session.

### C.1 Health & readiness

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | Liveness |
| `GET` | `/ready` | none | Readiness — `SELECT 1`; reports `apm_configured`, `rum_configured`, `logging_configured`, `atp_ocid`, `atp_connection_name`. Returns `503` when DB is down. |
| `GET` | `/api/modules` | none | Module dependency graph |

### C.2 Auth (`/api/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/login` | none | Local login |
| `POST` | `/api/auth/register` | none | Demo registration |
| `GET` | `/api/auth/session` | session | Inspect current session |
| `POST` | `/api/auth/logout` | session | Clear session |
| `GET` | `/api/auth/sso/login` | none | Begin IDCS OAuth2 |
| `GET` | `/api/auth/sso/callback` | none | OAuth2 callback |
| `GET` | `/api/auth/sso/status` | none | SSO config status |

### C.3 Dashboard (`/api/dashboard`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/dashboard/summary` | admin | KPI cards |
| `GET` | `/api/dashboard/slow-query` | admin | Intentional slow SQL |
| `GET` | `/api/dashboard/n-plus-one` | admin | Intentional N+1 |
| `GET` | `/api/dashboard/error-demo` | admin | Intentional 500 |

### C.4 Core CRM resources

Each resource exposes a standard `GET` list, `GET /{id}`, `POST`, `PATCH /{id}` (or `PUT`),
`DELETE /{id}` pattern.

| Prefix | Resource |
|--------|----------|
| `/api/customers` | Customers |
| `/api/products` (+ `POST /sync/shop`) | Products with shop catalog sync |
| `/api/shops` | Storefronts |
| `/api/invoices` (+ `POST /{id}/pay`, `GET /{id}/pdf`) | Invoices |
| `/api/tickets` (+ `GET /redirect`) | Support tickets |
| `/api/reports` (+ `POST /execute`, `POST /import`, `GET /export`) | Reports |
| `/api/campaigns` (+ `GET /{id}/leads`, `POST /{id}/leads`, `PATCH /{id}/leads/{lead_id}`) | Campaigns & leads |
| `/api/shipping` (+ `GET /by-region`, `GET /warehouses`, `PATCH /{id}/status`) | Shipping |

### C.5 Orders (`/api/orders`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/orders` | admin | List orders |
| `GET` | `/api/orders/backlog` | admin | Backlog snapshot |
| `GET` | `/api/orders/security/summary` | admin | Order security signals |
| `POST` | `/api/orders/sync` | `X-Internal-Service-Key` | Bulk sync from shop |
| `GET` | `/api/orders/{order_id}` | admin | Order detail |
| `POST` | `/api/orders` | `X-Internal-Service-Key` if configured | Create or upsert order (composite idempotency key) |
| `PATCH` | `/api/orders/{order_id}/status` | admin | Update status |

`POST /api/orders` accepts:

```json
{
  "customer_id": 123,
  "items": [{ "product_id": 1, "quantity": 2, "unit_price": 49.95 }],
  "total": 99.90,
  "source_system": "octo-drone-shop",
  "source_order_id": "shop-7f3c…",
  "idempotency_token": "uuid5-from-shop"
}
```

When `source_system` and `source_order_id` are both present, the server upserts on the
composite key `(source_system, source_order_id)` and reapplies payment metadata so retried
syncs do not create duplicate invoices.

### C.6 Admin (`/api/admin`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/admin/users` | List users |
| `PATCH` | `/api/admin/users/{user_id}/role` | Change role |
| `GET` | `/api/admin/config` | Effective config |
| `GET` | `/api/admin/debug` | Debug snapshot |
| `GET` | `/api/admin/audit-logs` | Audit log feed |
| `GET` | `/api/admin/data-retention/preview` | Retention preview |
| `POST` | `/api/admin/data-retention/cleanup` | Apply retention |
| `GET` | `/api/admin/db-status` | DB status card |

### C.7 Admin Coordinator (`/api/admin/coordinator`)

The Coordinator is a scoped admin helper that refuses prompts referencing OCI resources
outside the OCTO APM Demo project boundary.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/admin/coordinator/scope` | admin + admin host | Returns the project scope, allowed hosts, and guardrails payload |
| `POST` | `/api/admin/coordinator/query` | admin + admin host | Answers an admin question; refuses out-of-scope topics |

`_require_admin_host()` rejects requests whose `Host` header is not in
`_allowed_resource_hosts()`. The set includes `localhost`, `127.0.0.1`, the configured
admin hostnames, and the configured shop hostnames. Public storefront hosts are excluded.

`POST /api/admin/coordinator/query` body:

```json
{ "message": "<admin question>" }
```

Response envelope:

```json
{
  "answer": "...",
  "sources": [{ "title": "...", "url": "..." }],
  "scope": { "project": "octo-apm-demo", "...": "..." },
  "refused": false,
  "refusal_reason": ""
}
```

### C.8 Other routers

- **Simulation** — `/api/simulate/configure|reset|db-latency|db-disconnect|error-burst|
  slow-query|n-plus-one|app-exception|db-error|generate-orders|generate-backlog|
  high-value-order|add-customer|create-customer|sync-customers`.
- **Files** — `POST /api/files/upload`, `GET /api/files/download`,
  `POST /api/files/parse-xml`, `POST /api/files/import-url`.
- **API keys** — `POST /api/keys/generate`, `GET /api/keys/validate|list`.
- **Analytics** — `/api/analytics/overview|geo|funnel|revenue-by-region|track|performance`.
- **Integrations** — `/api/integrations/{drone-shop|mushop}/product-catalog|order-history|
  recommend-products|health`, `/api/integrations/topology|status|console/connections|console/config`.
- **Observability dashboards** — same `360`, `capabilities`, `melts` shape as the shop.
- **Frontend RUM beacon** — `POST /api/observability/frontend` (204 No Content).
- **Chaos admin** — `/api/admin/chaos/presets|state|apply|clear`.

## D. Java payment sidecar API (`services/apm-java-demo/`)

Spring Boot service exposing payment-style endpoints. Default port `8080`. No
authentication — the service is intended for cluster-internal traffic only. Network
policy restricts access to the shop service account.

### D.1 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service identity + endpoint listing |
| `GET` | `/ready` | Readiness — JVM version, app server name, role |
| `GET` | `/healthz` | Plain liveness — `{status: "up"}` |
| `GET` | `/api/java-apm/health` | Alias for `/ready` |
| `POST` | `/api/java-apm/quote` | Compute subtotal, tax (7%), shipping, total |
| `POST` | `/api/java-apm/payment/authorize` | Authorize payment; emits `java_payment_authorize` event |
| `POST` | `/api/java-apm/payment/verify` | Verify payment; emits `java_payment_verify` event |
| `POST` | `/api/java-apm/simulate/slow` | Sleeps 100–10 000 ms |
| `POST` | `/api/java-apm/simulate/gc` | Allocates 8–256 MiB to exercise GC |
| `POST` | `/api/java-apm/simulate/cpu` | CPU burn 100–5 000 ms |
| `POST` | `/api/java-apm/simulate/error` | Throws `IllegalStateException` (HTTP 500) |
| `POST` | `/api/java-apm/simulate/external-error` | Calls an HTTP target and raises on `>= 400` |
| `POST` | `/api/java-apm/simulate/sql-error` | Issues a deliberate bad SQL against the configured Oracle DSN |
| `POST` | `/api/java-apm/simulate/attack` | Emits a MITRE ATT&CK-labelled attack-path log |
| `GET` | `/slow` | Random 200–1 000 ms sleep |
| `GET` | `/allocate` | Allocate 16–63 MiB |
| `GET` | `/error` | Tagged controlled error (`demo.scenario=java-controlled-error`) |

### D.2 Expected request headers

The Java filter chain copies these headers into MDC and the server span:

| Header | MDC key | Span attribute |
|--------|---------|----------------|
| `traceparent` | `trace_id`, `span_id` | — (handled by OTel context propagation) |
| `X-Correlation-Id` | `correlation_id` | — |
| `X-Request-Id` | `request_id` | `request_id` |
| `X-Workflow-Id` | `workflow_id` | `workflow_id`, `workflow.id` |
| `X-Workflow-Step` | `workflow_step` | `workflow_step`, `workflow.step` |
| `X-Run-Id` | `run_id` | `run_id` |

Every request produces a `SERVER` span named `HTTP <METHOD> <route>` with attributes
`http.request.method`, `http.route`, `url.path`, `app.logical_endpoint`,
`app.module=java-payment-gateway`, `service.namespace=octo`,
`oci.demo.stack=octo-apm-demo`.

### D.3 Payment authorize — request shape

```json
{
  "order_id": "shop-1234",
  "amount_minor_units": 4995,
  "currency": "EUR",
  "customer_email_domain": "example.com",
  "idempotency_key_hash": "<16-hex>",
  "simulation_mode": "approve|decline|deny|timeout"
}
```

Response payload (decision-dependent) includes:
`payment_provider`, `payment_processor_name`, `payment_gateway_request_id`,
`payment_method`, `payment_network`, `payment_status`, `decision`, `authorization_code`,
`network_authorization`, `processor_response_code`, `network_transaction_id`,
`card_flow`, `wallet_flow`, `risk_score`, `latency_ms`, `currency`,
`amount_minor_units`, `error_code`, `customer_email_domain`,
`idempotency_key_hash`, `simulation_mode`, `token_safe: true`.

### D.4 Error handling

| Exception | HTTP status | Notes |
|-----------|-------------|-------|
| `IllegalStateException` | 500 | Tagged `demo.expected=true` for `/error` and `/api/java-apm/simulate/error` |
| `ExternalCallSimulationException` | 502 | Includes `external.target_url`, `external.status_code` |
| `SQLException` | 500 | Includes `sql.vendor_code`, `sql.state` |

## E. Workflow Gateway API (`shop/services/workflow-gateway/`)

Go service running on port `8090` by default. Exposes a flat HTTP routing table via
`internal/api/router.go`. Not directly reachable from the public storefront — the shop
proxies admin browser calls and enforces the admin-surface host check (see B.10).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/metrics` | Prometheus scrape |
| `GET` | `/api/workflows/catalog` | Workflow catalog |
| `GET` | `/api/workflows/overview` | Workflow overview |
| `GET` | `/api/components/snapshots` | Component snapshots |
| `GET` | `/api/query-lab/executions` | Query Lab execution history |
| `POST` | `/api/query-lab/run` | Run a Query Lab query |
| `POST` | `/api/selectai/generate` | Select AI prompt → SQL / narration / chat |

### E.1 Sub-services

- **Select AI** — uses `DBMS_CLOUD_AI.GENERATE`. Requires `selectai_configured: true`.
  Action must be one of `showsql`, `narrate`, `chat`. Prompt capped at 1 000 chars.
- **Query Lab** — runs pre-registered named queries against ATP via a service account.
- **GenAI assistant proxy** — orchestrates OCI Generative AI calls through Langfuse for
  prompt-level telemetry.

### E.2 Storefront refusal

Calls reaching the gateway directly from public storefront hostnames are refused at the
shop layer with HTTP 403:

```json
{ "detail": "Workflow Gateway admin labs are only available from the admin surface." }
```

## F. Service-to-service contract

### F.1 `X-Internal-Service-Key`

Both shop and CRM read the shared secret from `INTERNAL_SERVICE_KEY` (env or
`*_FILE`-mounted file). The CRM also accepts `DRONE_SHOP_INTERNAL_KEY` as an alias.
Comparison uses `hmac.compare_digest` so timing leaks are avoided. Endpoints that require
the key reject mismatches with:

```json
{ "detail": "Invalid or missing X-Internal-Service-Key" }
```

The shop injects the header automatically on cross-service calls in
`shop/server/modules/integrations.py`:

```python
headers["X-Internal-Service-Key"] = cfg.internal_service_key
```

### F.2 Idempotency

| Layer | Field | Format |
|-------|-------|--------|
| Shop checkout body | `checkout_idempotency_key` (or `idempotency_key`) | Free-form string, normalized server-side |
| Shop → CRM order body | `idempotency_token` | UUID5 derived from checkout key + order data |
| Shop → CRM order body | `source_system`, `source_order_id` | `(octo-drone-shop, shop-<uuid>)` |
| CRM persistence | Composite `(source_system, source_order_id)` | Unique upsert key |
| Java sidecar | `idempotency_key_hash` | First 16 hex chars of SHA-256 |

A retried shop checkout produces the same `idempotency_token`. CRM's `POST /api/orders`
detects the duplicate via the composite unique index and re-applies payment metadata
instead of inserting a new row.

### F.3 Cross-service URLs

Resolved at runtime from configuration. See [CONFIGURATION.md](CONFIGURATION.md) for the
authoritative variable list.

| Caller | Target | Variable |
|--------|--------|----------|
| Shop → CRM | In-cluster service URL | `CRM_INTERNAL_BASE_URL` |
| Shop → CRM | Public URL (admin surface) | `CRM_PUBLIC_URL` |
| Shop → Java sidecar | In-cluster URL | `JAVA_APM_SERVICE_URL` |
| Shop → Workflow Gateway | In-cluster URL | `WORKFLOW_API_BASE_URL` |
| CRM → Shop | In-cluster URL | `DRONE_SHOP_INTERNAL_BASE_URL` |

## G. Health & readiness contract

Every service exposes `/health` (liveness) and `/ready` (readiness). `ready: true`
guarantees:

| Service | Guarantee |
|---------|-----------|
| Drone Shop | ATP connection healthy (`SELECT 1 FROM DUAL`); `apm_configured`, `rum_configured`, `logging_configured` reported truthfully; Java sidecar + Workflow Gateway config flags reported |
| CRM | ATP connection healthy; `apm_configured`, `rum_configured`, `logging_configured` reported. Returns HTTP 503 when database is unreachable |
| Java sidecar | Process is running; JVM identity returned. No deep dependency check |
| Workflow Gateway | Process is running and listening |

Kubernetes liveness/readiness probes should point at `/health` and `/ready` respectively.
Prometheus scrapers consume `/metrics` on the Python services and the Workflow Gateway.

## H. Observability surface in API calls

Every request through the FastAPI services and the Spring Boot sidecar produces:

1. **One SERVER span** — `HTTP <method> <route>` with attributes documented in
   [ARCHITECTURE.md](../ARCHITECTURE.md): `http.request.method`, `http.route`,
   `http.response.status_code`, `app.module`, `app.logical_endpoint`,
   `service.namespace`, `oci.demo.stack`.
2. **Outgoing `traceparent` response header** — when APM is configured.
3. **A correlated log record** — emitted via the structured-logging SDK with fields
   `trace_id`, `span_id`, `correlation_id`, `request_id`, and `oracleApmTraceId` so OCI
   Log Analytics can join logs and APM traces without an additional dataset.
4. **Domain spans** for sub-operations — for example
   `orders.create`, `admin.coordinator.query`, `workflow_gateway.selectai.generate`,
   `java.payment.authorize`.
5. **Event records** in the OCI Logging stream for security-relevant actions
   (`security_event`, `mass_assignment`, `controlled_java_error`, …).

### H.1 Trace propagation

Inbound `traceparent` / `tracestate` are extracted by each service. When a request reaches
the shop without a trace context, the shop mints one and forwards it on outbound calls so
the trace remains continuous through CRM and the Java sidecar.

### H.2 RUM ↔ APM linking

Browser RUM beacons sent to `POST /api/observability/frontend` (CRM) and the shop's RUM
endpoint carry the active server `traceparent` as a meta tag. OCI APM treats the matching
trace ID as a single distributed trace spanning RUM → FastAPI → CRM → Java sidecar.

## I. Error envelope conventions

Where validation fails before reaching business logic, FastAPI's default
`HTTPException` shape applies:

```json
{ "detail": "<human readable message>" }
```

Business-level errors typically return HTTP 200 with a payload containing an `error`
field — for example:

```json
{ "error": "Customer not found" }
```

Java payment endpoints return Spring's default JSON error map with `status`,
`error_type`, `message`, and (where relevant) `external.*` or `sql.*` fields. None of the
services return raw stack traces in production responses.

## J. Rate limits

Rate limiting is applied at the OCI API Gateway layer for public-facing routes when
deployed on OCI; service-internal limits are not enforced inside the FastAPI apps. The
shop performs per-route input-size validation (16 KiB body cap on the Workflow Gateway
proxy, 1 000-character Select AI prompt cap). Operational rate-limit values vary per
deployment.

<!-- VERIFY: API Gateway production rate limit values per route -->

## K. Cross-references

- Authentication & SSO configuration: [CONFIGURATION.md](CONFIGURATION.md)
- Service topology, span attributes, and event taxonomy: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Local stack endpoints (developer iteration): see `deploy/local-stack/README.md`
