/*
 * OCTO Drone Shop — ATP Database Stress Test
 *
 * Hammers Oracle ATP through the application layer to generate heavy DB load
 * visible in OCI DB Management, Operations Insights, and APM SQL traces.
 *
 * k6 cannot connect to Oracle ATP directly, so this test drives DB pressure
 * through the app endpoints that produce the most expensive SQL:
 *
 *   Writes:  checkout (INSERT orders + order_items + shipments + audit_logs)
 *   Writes:  demo/customer (INSERT customers), demo/orders (bulk INSERT)
 *   Reads:   dashboard/summary (8-table aggregation JOIN)
 *   Reads:   /api/orders (correlated subqueries: subtotal + shipping)
 *   Reads:   analytics/overview (full-table scan + grouping)
 *   N+1:     dashboard/n-plus-one (1 list + N detail queries)
 *   Slow:    dashboard/slow-query (configurable pg_sleep / DBMS_SESSION.SLEEP)
 *   Sync:    integrations/crm/sync-customers (bulk UPSERT from CRM)
 *
 * Each scenario tags its spans so you can filter in APM by demo.type or
 * app.logical_endpoint and see exactly which query pattern caused the load.
 *
 * Usage:
 *   k6 run --env DNS_DOMAIN=example.cloud k6/db_stress.js
 *   k6 run --env SHOP_URL=http://localhost:8080 k6/db_stress.js
 *   k6 run --env DNS_DOMAIN=example.cloud --env PROFILE=heavy k6/db_stress.js
 *   k6 run --env DNS_DOMAIN=example.cloud --env CRM_URL=https://crm.example.cloud k6/db_stress.js
 *
 * OCI verification after the run:
 *   1. DB Management → Performance Hub → SQL Monitoring: look for the test
 *      window, sort by elapsed time or executions
 *   2. Operations Insights → SQL Warehouse → Top SQL: verify the INSERT and
 *      aggregation patterns from this test appear in the top-N
 *   3. APM → Trace Explorer → filter db.system=oracle: see per-statement
 *      spans with db.statement, db.client.execution_time_ms, db.row_count
 *   4. Log Analytics → search "slow query demo" OR "n_plus_one": correlated
 *      structured logs with oracleApmTraceId
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── Configuration ───────────────────────────────────────────────
const DNS_DOMAIN = __ENV.DNS_DOMAIN || '';
const SHOP_URL = __ENV.SHOP_URL || (DNS_DOMAIN ? `https://shop.${DNS_DOMAIN}` : 'http://localhost:8080');
const CRM_URL = __ENV.CRM_URL || (DNS_DOMAIN ? `https://crm.${DNS_DOMAIN}` : '');
const PROFILE = (__ENV.PROFILE || 'moderate').toLowerCase();

// ── Custom Metrics ──────────────────────────────────────────────
const errorRate = new Rate('errors');
const writeLatency = new Trend('db_write_latency_ms');
const readLatency = new Trend('db_read_latency_ms');
const nPlusOneLatency = new Trend('n_plus_one_latency_ms');
const slowQueryLatency = new Trend('slow_query_latency_ms');
const bulkSyncLatency = new Trend('bulk_sync_latency_ms');
const checkoutLatency = new Trend('checkout_latency_ms');
const totalQueries = new Counter('total_db_queries');
const writeOps = new Counter('write_ops');
const readOps = new Counter('read_ops');

// ── Profiles ────────────────────────────────────────────────────
const PROFILES = {
    light: {
        writes:   { vus: 2,  iters: 10 },
        reads:    { rate: 5,  duration: '1m',  maxVUs: 8  },
        nplusone: { vus: 1,  iters: 5  },
        slow:     { vus: 1,  iters: 3  },
        checkout: { vus: 2,  iters: 8  },
        sync:     { vus: 1,  iters: 3  },
    },
    moderate: {
        writes:   { vus: 5,  iters: 25 },
        reads:    { rate: 15, duration: '3m',  maxVUs: 20 },
        nplusone: { vus: 3,  iters: 15 },
        slow:     { vus: 2,  iters: 8  },
        checkout: { vus: 5,  iters: 20 },
        sync:     { vus: 2,  iters: 8  },
    },
    heavy: {
        writes:   { vus: 10, iters: 60 },
        reads:    { rate: 40, duration: '5m',  maxVUs: 50 },
        nplusone: { vus: 5,  iters: 30 },
        slow:     { vus: 3,  iters: 15 },
        checkout: { vus: 10, iters: 50 },
        sync:     { vus: 4,  iters: 15 },
    },
};

const P = PROFILES[PROFILE] || PROFILES.moderate;

export const options = {
    scenarios: {
        // Scenario 1: Bulk writes — customers + orders
        bulk_writes: {
            executor: 'per-vu-iterations',
            vus: P.writes.vus,
            iterations: P.writes.iters,
            exec: 'bulkWrites',
        },
        // Scenario 2: Read-heavy aggregations
        read_aggregations: {
            executor: 'constant-arrival-rate',
            rate: P.reads.rate,
            timeUnit: '1s',
            duration: P.reads.duration,
            preAllocatedVUs: 5,
            maxVUs: P.reads.maxVUs,
            startTime: '10s',
            exec: 'readAggregations',
        },
        // Scenario 3: N+1 query pattern
        n_plus_one: {
            executor: 'per-vu-iterations',
            vus: P.nplusone.vus,
            iterations: P.nplusone.iters,
            startTime: '15s',
            exec: 'nPlusOnePattern',
        },
        // Scenario 4: Slow queries (configurable delay)
        slow_queries: {
            executor: 'per-vu-iterations',
            vus: P.slow.vus,
            iterations: P.slow.iters,
            startTime: '20s',
            exec: 'slowQueries',
        },
        // Scenario 5: Full checkout (multi-table INSERT transaction)
        checkout_storm: {
            executor: 'per-vu-iterations',
            vus: P.checkout.vus,
            iterations: P.checkout.iters,
            startTime: '5s',
            exec: 'checkoutStorm',
        },
        // Scenario 6: Cross-service bulk sync (CRM → Drone Shop UPSERT)
        cross_service_sync: {
            executor: 'per-vu-iterations',
            vus: P.sync.vus,
            iterations: P.sync.iters,
            startTime: '30s',
            exec: 'crossServiceBulkSync',
        },
    },
    thresholds: {
        errors: ['rate<0.20'],
        db_write_latency_ms: ['p(95)<5000'],
        db_read_latency_ms: ['p(95)<3000'],
        checkout_latency_ms: ['p(95)<8000'],
        slow_query_latency_ms: ['p(95)<12000'],
    },
};

// ── Helpers ──────────────────────────────────────────────────────

function headers() {
    return {
        'X-Correlation-Id': `k6-db-${uuidv4()}`,
        'Content-Type': 'application/json',
    };
}

function shopGet(path, h) {
    const res = http.get(`${SHOP_URL}${path}`, { headers: h, tags: { target: 'db' } });
    errorRate.add(res.status >= 400);
    totalQueries.add(1);
    return res;
}

function shopPost(path, body, h) {
    const res = http.post(`${SHOP_URL}${path}`, JSON.stringify(body), { headers: h, tags: { target: 'db' } });
    errorRate.add(res.status >= 400);
    totalQueries.add(1);
    return res;
}

// ── Scenario 1: Bulk Writes ──────────────────────────────────────

export function bulkWrites() {
    const h = headers();

    group('Create Customer', () => {
        const suffix = Math.floor(Math.random() * 99999);
        const start = Date.now();
        const res = shopPost('/api/dashboard/demo/customer', {
            company: `K6 Corp ${suffix}`,
            contact_name: `K6 Contact ${suffix}`,
            email: `k6.${suffix}@example.invalid`,
            industry: 'Stress Testing',
            revenue: Math.floor(Math.random() * 10000000),
        }, h);
        writeLatency.add(Date.now() - start);
        writeOps.add(1);
        check(res, { 'customer created': (r) => r.status === 200 });
    });
    sleep(0.2);

    group('Bulk Orders', () => {
        const start = Date.now();
        const res = shopPost('/api/dashboard/demo/orders', {
            count: Math.floor(Math.random() * 5) + 2,
            quantity: Math.floor(Math.random() * 3) + 1,
            status: ['processing', 'pending', 'completed', 'queued'][Math.floor(Math.random() * 4)],
            high_value: Math.random() > 0.7,
        }, h);
        writeLatency.add(Date.now() - start);
        writeOps.add(1);
        check(res, { 'orders generated': (r) => r.status === 200 });
    });
    sleep(0.3);
}

// ── Scenario 2: Read Aggregations ────────────────────────────────

const READ_ENDPOINTS = [
    '/api/dashboard/summary',          // 8-table JOIN with GROUP BY + revenue SUM
    '/api/orders?limit=100',           // correlated subqueries (subtotal, shipping)
    '/api/analytics/overview',         // full-scan aggregation
    '/api/analytics/funnel',           // multi-step conversion funnel
    '/api/products',                   // product catalog scan
    '/api/shipping',                   // shipment listing + JOINs
    '/api/campaigns',                  // campaign + leads aggregation
    '/api/observability/360',          // 4-table health check + counts
    '/api/dashboard/catalog',          // customers + products for form dropdowns
    '/ready',                          // SELECT 1 FROM DUAL (baseline)
];

export function readAggregations() {
    const h = headers();
    const ep = READ_ENDPOINTS[Math.floor(Math.random() * READ_ENDPOINTS.length)];
    const start = Date.now();
    const res = shopGet(ep, h);
    readLatency.add(Date.now() - start);
    readOps.add(1);
    check(res, { 'read ok': (r) => r.status === 200 });
}

// ── Scenario 3: N+1 Query Pattern ────────────────────────────────

export function nPlusOnePattern() {
    const h = headers();

    group('N+1 Demo', () => {
        const start = Date.now();
        const res = shopGet('/api/dashboard/n-plus-one', h);
        nPlusOneLatency.add(Date.now() - start);
        readOps.add(1);
        check(res, { 'n+1 completes': (r) => r.status === 200 });
        if (res.status === 200) {
            try {
                const body = res.json();
                // Each N+1 call generates 1 + N DB queries
                totalQueries.add(body.query_count || 1);
            } catch (_) {}
        }
    });
    sleep(0.5);
}

// ── Scenario 4: Slow Queries ─────────────────────────────────────

export function slowQueries() {
    const h = headers();
    // Vary the delay to create different SQL execution time profiles
    const delays = [1.0, 2.0, 3.0, 5.0];
    const delay = delays[Math.floor(Math.random() * delays.length)];

    group(`Slow Query ${delay}s`, () => {
        const start = Date.now();
        const res = shopGet(`/api/dashboard/slow-query?delay=${delay}`, h);
        slowQueryLatency.add(Date.now() - start);
        readOps.add(1);
        check(res, { 'slow query returns': (r) => r.status === 200 });
    });
    sleep(0.5);
}

// ── Scenario 5: Checkout Storm (Multi-Table INSERT) ──────────────

export function checkoutStorm() {
    const h = headers();
    const sessionId = `k6-db-${uuidv4().substring(0, 8)}`;
    const productId = Math.floor(Math.random() * 8) + 1;

    group('Add Items', () => {
        // Add 1-4 items to cart
        const itemCount = Math.floor(Math.random() * 3) + 1;
        for (let i = 0; i < itemCount; i++) {
            shopPost('/api/cart/add', {
                product_id: ((productId + i) % 8) + 1,
                quantity: Math.floor(Math.random() * 3) + 1,
                session_id: sessionId,
            }, h);
            writeOps.add(1);
        }
    });
    sleep(0.2);

    group('Checkout', () => {
        const start = Date.now();
        const res = shopPost('/api/shop/checkout', {
            session_id: sessionId,
            customer_name: `K6 DB Buyer ${Math.floor(Math.random() * 10000)}`,
            customer_email: `k6.db.${uuidv4().substring(0, 6)}@example.invalid`,
            shipping_address: `K6 DB Stress ${Math.floor(Math.random() * 999)} Test Lane`,
        }, h);
        checkoutLatency.add(Date.now() - start);
        writeOps.add(1);
        check(res, { 'checkout ok': (r) => r.status === 200 });
    });
    sleep(0.5);
}

// ── Scenario 6: Cross-Service Bulk Sync ──────────────────────────

export function crossServiceBulkSync() {
    const h = headers();

    group('CRM Customer Sync', () => {
        // Forces a full CRM → local DB upsert cycle
        const start = Date.now();
        const res = shopPost('/api/integrations/crm/sync-customers', {
            force: true,
            limit: 200,
        }, h);
        bulkSyncLatency.add(Date.now() - start);
        writeOps.add(1);
        check(res, { 'sync ok': (r) => r.status === 200 });
        if (res.status === 200) {
            try {
                const body = res.json();
                totalQueries.add(body.synced || 0); // each customer = 1 SELECT + 1 INSERT/UPDATE
            } catch (_) {}
        }
    });
    sleep(1);

    // If CRM is configured, also hit the CRM's DB directly
    if (CRM_URL) {
        group('CRM Dashboard Summary', () => {
            const start = Date.now();
            const res = http.get(`${CRM_URL}/api/dashboard/summary`, { headers: h });
            readLatency.add(Date.now() - start);
            readOps.add(1);
        });
        sleep(0.5);
    }
}

// ── Summary ──────────────────────────────────────────────────────

export function handleSummary(data) {
    const m = (key) => data.metrics[key] ? Math.round(data.metrics[key].values['p(95)']) : 'N/A';
    const c = (key) => data.metrics[key] ? data.metrics[key].values.count : 0;

    const summary = {
        test: 'OCTO ATP Database Stress Test',
        profile: PROFILE,
        shop_url: SHOP_URL,
        crm_url: CRM_URL || '(not configured)',
        stats: {
            total_db_queries: c('total_db_queries'),
            write_ops: c('write_ops'),
            read_ops: c('read_ops'),
            error_rate: data.metrics.errors ? (data.metrics.errors.values.rate * 100).toFixed(1) + '%' : 'N/A',
        },
        latency_p95_ms: {
            writes: m('db_write_latency_ms'),
            reads: m('db_read_latency_ms'),
            checkout: m('checkout_latency_ms'),
            n_plus_one: m('n_plus_one_latency_ms'),
            slow_query: m('slow_query_latency_ms'),
            bulk_sync: m('bulk_sync_latency_ms'),
        },
        oci_verification: {
            db_management: 'DB Management → Performance Hub → SQL Monitoring → sort by elapsed time',
            ops_insights: 'Operations Insights → SQL Warehouse → Top SQL during test window',
            apm_sql: 'APM → Trace Explorer → filter db.system=oracle → per-statement spans',
            log_analytics: 'Log Analytics → search "slow query" OR "n_plus_one" with oracleApmTraceId',
        },
    };

    return {
        stdout: JSON.stringify(summary, null, 2) + '\n',
    };
}
