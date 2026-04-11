# Load Tests

Three k6 test suites with configurable intensity profiles (light/moderate/heavy).

## Suites

### 1. Shop-Only (`k6/load_test.js`)

```bash
k6 run --env BASE_URL=https://shop.octodemo.cloud k6/load_test.js
```

| Scenario | Pattern | Duration |
|---|---|---|
| browse | Ramping VUs (1→25→5→0) | 4 min |
| api_load | Constant 20 req/s | 3 min |
| geo_browse | 6 VUs × 20 iterations | 2 min |
| security_probes | 3 VUs × 50 iterations | 2 min |

### 2. Cross-Service (`k6/cross_service_stress.js`)

```bash
k6 run --env DNS_DOMAIN=octodemo.cloud k6/cross_service_stress.js
```

Hits both `shop.{domain}` and `crm.{domain}` simultaneously. Every request includes `X-Correlation-Id` for trace correlation.

| Scenario | What | Services |
|---|---|---|
| shop_browse | Storefront, products, cart | Shop |
| crm_browse | Customers, tickets, invoices | CRM |
| api_stress | High-rate API calls | Both |
| distributed_traces | Customer sync, order sync | Shop → CRM |
| checkout_storm | Concurrent checkouts | Shop → CRM → ATP |

### 3. Database Stress (`k6/db_stress.js`)

```bash
k6 run --env DNS_DOMAIN=octodemo.cloud k6/db_stress.js
```

| Scenario | SQL Pattern | Purpose |
|---|---|---|
| bulk_writes | INSERT orders + items + shipments | Write throughput |
| aggregations | 8-table JOIN dashboard | Read pressure |
| n_plus_one | 1 list + N detail queries | Pattern detection |
| slow_queries | DBMS_SESSION.SLEEP | Slow query investigation |
| checkout_storms | Concurrent checkouts | Lock contention |
| crm_sync | Bulk customer UPSERT | Sync load |

## Intensity Profiles

```bash
# Light (default)
k6 run --env PROFILE=light ...

# Moderate
k6 run --env PROFILE=moderate ...

# Heavy
k6 run --env PROFILE=heavy ...
```

## OCI Verification After Load Test

1. **DB Management** → Performance Hub → SQL Monitor: test window queries
2. **Operations Insights** → SQL Warehouse → Top SQL: INSERT/aggregation patterns
3. **APM** → Trace Explorer → filter `db.system=oracle`: per-statement spans
4. **Log Analytics** → search `"slow query demo"`: correlated structured logs
5. **OCI Monitoring** → `octo_drone_shop` namespace: metric spikes during test
