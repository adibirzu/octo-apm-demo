# Simulation Lab

The CRM Portal includes a comprehensive simulation lab with 15+ chaos injection endpoints and cross-service proxy capabilities.

## Runtime-Toggleable Flags

| Flag | Effect | Visible In |
|---|---|---|
| `db_latency` | 2.5s sleep before queries | APM: db.client.execution_time_ms spike |
| `db_disconnect` | ConnectionError on DB access | APM: ERROR spans, Monitoring: error rate alarm |
| `memory_leak` | 1MB allocated per request | Process metrics: RSS growth |
| `cpu_spike` | Busy-loop math per request | Process metrics: CPU% spike |
| `slow_queries` | asyncio.sleep in route handlers | APM: increased request duration |
| `error_rate` | Random 500 responses (0.0-1.0) | Monitoring: error rate alarm |

## Control Endpoints

```bash
# View state
GET /api/simulate/status

# Toggle flags
POST /api/simulate/configure
{"db_latency": true, "error_rate": 0.3}

# Reset all
POST /api/simulate/reset
```

## One-Shot Incidents

| Endpoint | Effect | Duration |
|---|---|---|
| `POST /simulate/db-latency` | Manual delay (1-30s) | Single request |
| `POST /simulate/db-disconnect` | Connection refused | 10 seconds |
| `POST /simulate/error-burst` | Generate N errors | Immediate |
| `POST /simulate/slow-query` | Python sleep + DB query | Single request |
| `POST /simulate/n-plus-one` | N individual SELECTs | Single request |
| `POST /simulate/app-exception` | ValueError + OTel recording | Single request |

## Data Generation

| Endpoint | Creates |
|---|---|
| `POST /simulate/add-customer` | Single customer |
| `POST /simulate/generate-orders` | N orders with items |
| `POST /simulate/generate-backlog` | Orders with stale timestamps |
| `POST /simulate/high-value-order` | $82k+ order (alert trigger) |
| `POST /simulate/sync-customers` | Trigger order sync from Drone Shop |

## Cross-Service Proxy

CRM can trigger actions on Drone Shop via service key:

```bash
POST /api/simulate/drone-shop/health
POST /api/simulate/drone-shop/product-catalog
POST /api/simulate/drone-shop/order-history
POST /api/simulate/drone-shop/recommend-products
```

Uses `DRONE_SHOP_INTERNAL_KEY` header for auth. Enables cross-service chaos scenarios visible in OCI APM distributed traces.
