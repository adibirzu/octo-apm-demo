# Traces (APM)

OCI APM receives traces via OpenTelemetry OTLP/HTTP. The application generates **50+ custom spans** across 13 modules, plus auto-instrumented spans for FastAPI, SQLAlchemy, and httpx.

## Span Coverage

| Module | Span Name | Key Attributes |
|---|---|---|
| shop | `shop.checkout` | order_id, total, item_count, payment_method |
| shop | `shop.storefront` | catalog_count, category_count, inventory_units |
| shop | `shop.assistant.query` | session_id, provider, documents_grounded |
| orders | `orders.cart.add` | product_id, quantity, session_id |
| orders | `orders.create` | order_id, total, crm_order_synced |
| auth | `auth.login` | username, auth_method, success |
| sso | `auth.sso.callback` | idcs_domain, token_verified |
| catalogue | `catalogue.list_products` | product_count, category_filter |
| integrations | `integration.crm.sync_customers` | customers_synced, circuit_breaker.state |
| integrations | `integration.crm.sync_order` | order_id, crm_status_code |
| security | `ATTACK:<type>` | vuln_type, severity, mitre.technique_id, owasp.category |

## Distributed Tracing

Cross-service calls inject `traceparent` automatically via `HTTPXClientInstrumentor`:

```
00-<trace_id>-<span_id>-01
```

Response headers include `X-Trace-Id`, `X-Span-Id`, and `X-Correlation-Id` for frontend correlation.

## SQL Instrumentation

Every database query generates a span with:

- `db.statement` — SQL text
- `db.client.execution_time_ms` — wall-clock time
- `db.row_count` — rows returned/affected
- `DbOracleSqlId` — Oracle SQL_ID for Performance Hub cross-reference

## OCI APM Configuration

```python
# Exporter configuration
OCI_APM_ENDPOINT = "https://<apm-endpoint>/20200101/opentelemetry/private/v1/traces"
OCI_APM_PRIVATE_DATAKEY = "<private-data-key>"  # Auth header: "dataKey {key}"
```
