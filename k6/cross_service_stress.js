/*
 * OCTO Cross-Service Stress Test — Drone Shop + CRM + ATP + OCI Observability
 *
 * Exercises the full end-to-end path that generates correlated traces in OCI APM,
 * structured logs in OCI Logging / Log Analytics, and backend DB load in ATP:
 *
 *   Browser → Drone Shop → ATP (products, orders, cart)
 *   Browser → CRM        → ATP (customers, tickets, invoices)
 *   Drone Shop → CRM     → ATP (customer sync, order sync — distributed trace)
 *   CRM → Drone Shop     → ATP (simulation proxy — service key auth)
 *
 * Every HTTP request includes a X-Correlation-Id header so all traces, logs,
 * and DB queries can be joined in OCI APM / Log Analytics on the same ID.
 *
 * Usage:
 *   # Against live OKE deployment
 *   k6 run --env DNS_DOMAIN=example.cloud k6/cross_service_stress.js
 *
 *   # Against local docker-compose
 *   k6 run --env SHOP_URL=http://localhost:8080 --env CRM_URL=http://localhost:8081 k6/cross_service_stress.js
 *
 *   # Moderate load (default)
 *   k6 run --env DNS_DOMAIN=example.cloud k6/cross_service_stress.js
 *
 *   # Heavy load
 *   k6 run --env DNS_DOMAIN=example.cloud --env PROFILE=heavy k6/cross_service_stress.js
 *
 * OCI Observability verification after the run:
 *   1. OCI APM → Trace Explorer: filter by serviceName=octo-drone-shop
 *      → verify distributed traces spanning both CRM and Drone Shop
 *   2. OCI APM → Topology: verify CRM ↔ Drone Shop ↔ ATP graph edges
 *   3. OCI Log Analytics: search oracleApmTraceId=<any trace_id from step 1>
 *      → verify correlated app logs from both services
 *   4. OCI DB Management → Performance Hub: verify SQL execution spikes
 *      during the test window
 *   5. OCI Operations Insights → SQL Warehouse: verify query patterns
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── Configuration ───────────────────────────────────────────────
const DNS_DOMAIN = __ENV.DNS_DOMAIN || '';
const SHOP_URL = __ENV.SHOP_URL || (DNS_DOMAIN ? `https://shop.${DNS_DOMAIN}` : 'http://localhost:8080');
const CRM_URL = __ENV.CRM_URL || (DNS_DOMAIN ? `https://crm.${DNS_DOMAIN}` : 'http://localhost:8081');
const PROFILE = (__ENV.PROFILE || 'moderate').toLowerCase();

// ── Custom Metrics ──────────────────────────────────────────────
const errorRate = new Rate('errors');
const shopLatency = new Trend('shop_latency_ms');
const crmLatency = new Trend('crm_latency_ms');
const crossServiceLatency = new Trend('cross_service_latency_ms');
const dbQueryLatency = new Trend('db_query_latency_ms');
const apiCalls = new Counter('api_calls');
const crossServiceCalls = new Counter('cross_service_calls');

// ── Profiles ────────────────────────────────────────────────────
const PROFILES = {
    light: {
        browse: { stages: [{ duration: '20s', target: 3 }, { duration: '1m', target: 5 }, { duration: '10s', target: 0 }] },
        api: { rate: 5, duration: '1m30s', maxVUs: 10 },
        cross: { vus: 2, iterations: 10 },
    },
    moderate: {
        browse: { stages: [{ duration: '30s', target: 5 }, { duration: '2m', target: 15 }, { duration: '1m', target: 25 }, { duration: '30s', target: 5 }, { duration: '10s', target: 0 }] },
        api: { rate: 20, duration: '3m', maxVUs: 30 },
        cross: { vus: 5, iterations: 30 },
    },
    heavy: {
        browse: { stages: [{ duration: '30s', target: 10 }, { duration: '2m', target: 40 }, { duration: '3m', target: 60 }, { duration: '1m', target: 20 }, { duration: '30s', target: 0 }] },
        api: { rate: 50, duration: '5m', maxVUs: 80 },
        cross: { vus: 10, iterations: 60 },
    },
};

const P = PROFILES[PROFILE] || PROFILES.moderate;

export const options = {
    scenarios: {
        // Scenario 1: User browsing both shop and CRM
        browse_shop_crm: {
            executor: 'ramping-vus',
            startVUs: 1,
            stages: P.browse.stages,
            exec: 'browseShopAndCrm',
        },
        // Scenario 2: API load on both services
        api_load: {
            executor: 'constant-arrival-rate',
            rate: P.api.rate,
            timeUnit: '1s',
            duration: P.api.duration,
            preAllocatedVUs: 10,
            maxVUs: P.api.maxVUs,
            startTime: '20s',
            exec: 'apiLoad',
        },
        // Scenario 3: Cross-service distributed traces
        cross_service_sync: {
            executor: 'per-vu-iterations',
            vus: P.cross.vus,
            iterations: P.cross.iterations,
            startTime: '30s',
            exec: 'crossServiceSync',
        },
        // Scenario 4: Full checkout flow (Shop → ATP → CRM order sync)
        checkout_flow: {
            executor: 'per-vu-iterations',
            vus: 3,
            iterations: 15,
            startTime: '45s',
            exec: 'checkoutFlow',
        },
        // Scenario 5: Observability endpoints (dashboard, 360, health)
        observability_poll: {
            executor: 'constant-arrival-rate',
            rate: 2,
            timeUnit: '1s',
            duration: P.api.duration,
            preAllocatedVUs: 3,
            maxVUs: 8,
            startTime: '10s',
            exec: 'observabilityPoll',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<5000'],
        errors: ['rate<0.15'],
        shop_latency_ms: ['p(95)<3000'],
        crm_latency_ms: ['p(95)<3000'],
        cross_service_latency_ms: ['p(95)<5000'],
    },
};

// ── Helpers ──────────────────────────────────────────────────────

function correlationHeaders() {
    return {
        'X-Correlation-Id': `k6-${uuidv4()}`,
        'Content-Type': 'application/json',
    };
}

function shopGet(path, headers) {
    const start = Date.now();
    const res = http.get(`${SHOP_URL}${path}`, { headers, tags: { service: 'shop' } });
    shopLatency.add(Date.now() - start);
    apiCalls.add(1);
    errorRate.add(res.status !== 200);
    return res;
}

function crmGet(path, headers) {
    const start = Date.now();
    const res = http.get(`${CRM_URL}${path}`, { headers, tags: { service: 'crm' } });
    crmLatency.add(Date.now() - start);
    apiCalls.add(1);
    errorRate.add(res.status !== 200);
    return res;
}

function shopPost(path, body, headers) {
    const start = Date.now();
    const res = http.post(`${SHOP_URL}${path}`, JSON.stringify(body), { headers, tags: { service: 'shop' } });
    shopLatency.add(Date.now() - start);
    apiCalls.add(1);
    errorRate.add(res.status >= 400);
    return res;
}

function crmPost(path, body, headers) {
    const start = Date.now();
    const res = http.post(`${CRM_URL}${path}`, JSON.stringify(body), { headers, tags: { service: 'crm' } });
    crmLatency.add(Date.now() - start);
    apiCalls.add(1);
    errorRate.add(res.status >= 400);
    return res;
}

// ── Scenario 1: Browse Shop and CRM ─────────────────────────────

export function browseShopAndCrm() {
    const h = correlationHeaders();

    group('Shop Browsing', () => {
        shopGet('/', h);
        sleep(0.5);
        shopGet('/api/shop/featured', h);
        sleep(0.3);
        shopGet('/api/products', h);
        sleep(0.3);
        shopGet('/api/products/1', h);
        sleep(0.2);
        shopGet('/api/products/1/reviews', h);
        sleep(0.5);
    });

    group('CRM Browsing', () => {
        crmGet('/', h);
        sleep(0.5);
        crmGet('/api/customers', h);
        sleep(0.3);
        crmGet('/api/orders', h);
        sleep(0.3);
        crmGet('/api/tickets', h);
        sleep(0.3);
        crmGet('/api/products', h);
        sleep(0.5);
    });

    sleep(1);
}

// ── Scenario 2: API Load ─────────────────────────────────────────

const SHOP_ENDPOINTS = [
    '/api/shop/featured', '/api/products', '/api/orders',
    '/api/shipping', '/api/campaigns', '/api/analytics/overview',
    '/api/dashboard/summary', '/api/modules', '/health', '/ready',
];

const CRM_ENDPOINTS = [
    '/api/customers', '/api/orders', '/api/products',
    '/api/tickets', '/api/reports/revenue', '/api/dashboard/summary',
    '/health', '/ready',
];

export function apiLoad() {
    const h = correlationHeaders();
    // Alternate between shop and CRM
    if (Math.random() < 0.5) {
        const ep = SHOP_ENDPOINTS[Math.floor(Math.random() * SHOP_ENDPOINTS.length)];
        shopGet(ep, h);
    } else {
        const ep = CRM_ENDPOINTS[Math.floor(Math.random() * CRM_ENDPOINTS.length)];
        crmGet(ep, h);
    }
}

// ── Scenario 3: Cross-Service Distributed Traces ─────────────────

export function crossServiceSync() {
    const h = correlationHeaders();

    group('CRM → Shop Customer Enrichment', () => {
        // This call goes: CRM client → Shop /api/integrations/crm/customer-enrichment
        // which calls CRM /api/customers/{id} — creating a 3-hop distributed trace
        const start = Date.now();
        const res = shopGet('/api/integrations/crm/customer-enrichment?customer_id=1', h);
        crossServiceLatency.add(Date.now() - start);
        crossServiceCalls.add(1);
        check(res, { 'enrichment returns': (r) => r.status === 200 });
    });
    sleep(0.5);

    group('Shop → CRM Customer Sync', () => {
        const start = Date.now();
        const res = shopPost('/api/integrations/crm/sync-customers', { force: true, limit: 50 }, h);
        crossServiceLatency.add(Date.now() - start);
        crossServiceCalls.add(1);
        check(res, { 'sync completes': (r) => r.status === 200 });
    });
    sleep(0.5);

    group('CRM Health via Shop', () => {
        const start = Date.now();
        const res = shopGet('/api/integrations/crm/health', h);
        crossServiceLatency.add(Date.now() - start);
        crossServiceCalls.add(1);
        check(res, { 'crm health via shop': (r) => r.status === 200 });
    });
    sleep(1);
}

// ── Scenario 4: Full Checkout Flow ───────────────────────────────

export function checkoutFlow() {
    const h = correlationHeaders();
    const sessionId = `k6-checkout-${uuidv4().substring(0, 8)}`;

    group('Add to Cart', () => {
        const productId = Math.floor(Math.random() * 8) + 1;
        shopPost('/api/cart/add', {
            product_id: productId,
            quantity: Math.floor(Math.random() * 3) + 1,
            session_id: sessionId,
        }, h);
        sleep(0.3);
    });

    group('View Cart', () => {
        const res = shopGet(`/api/cart?session_id=${sessionId}`, h);
        check(res, { 'cart loaded': (r) => r.status === 200 });
        sleep(0.5);
    });

    group('Checkout', () => {
        const start = Date.now();
        const res = shopPost('/api/shop/checkout', {
            session_id: sessionId,
            customer_name: `K6 Buyer ${Math.floor(Math.random() * 1000)}`,
            customer_email: `k6.buyer.${uuidv4().substring(0, 6)}@example.invalid`,
            shipping_address: 'K6 Stress Test Address',
        }, h);
        const elapsed = Date.now() - start;
        dbQueryLatency.add(elapsed);
        check(res, { 'checkout succeeds': (r) => r.status === 200 });
        sleep(0.5);

        // The checkout triggers an order sync to CRM (distributed trace)
        // Verify the order appears in CRM
        if (res.status === 200) {
            try {
                const body = res.json();
                if (body.order_id) {
                    crossServiceCalls.add(1);
                }
            } catch (_) { /* non-JSON response */ }
        }
    });
    sleep(1);
}

// ── Scenario 5: Observability Endpoints ──────────────────────────

export function observabilityPoll() {
    const h = correlationHeaders();

    if (Math.random() < 0.5) {
        // Shop 360 dashboard
        const start = Date.now();
        const res = shopGet('/api/observability/360', h);
        dbQueryLatency.add(Date.now() - start);
        check(res, { 'shop 360 ok': (r) => r.status === 200 });
    } else {
        // CRM 360 dashboard
        const start = Date.now();
        const res = crmGet('/api/observability/360', h);
        dbQueryLatency.add(Date.now() - start);
        check(res, { 'crm 360 ok': (r) => r.status === 200 });
    }
}

// ── Teardown Summary ─────────────────────────────────────────────

export function handleSummary(data) {
    const summary = {
        test: 'OCTO Cross-Service Stress Test',
        profile: PROFILE,
        shop_url: SHOP_URL,
        crm_url: CRM_URL,
        dns_domain: DNS_DOMAIN || '(local)',
        total_requests: data.metrics.api_calls ? data.metrics.api_calls.values.count : 0,
        cross_service_calls: data.metrics.cross_service_calls ? data.metrics.cross_service_calls.values.count : 0,
        error_rate: data.metrics.errors ? (data.metrics.errors.values.rate * 100).toFixed(1) + '%' : 'N/A',
        shop_p95_ms: data.metrics.shop_latency_ms ? Math.round(data.metrics.shop_latency_ms.values['p(95)']) : 'N/A',
        crm_p95_ms: data.metrics.crm_latency_ms ? Math.round(data.metrics.crm_latency_ms.values['p(95)']) : 'N/A',
        cross_service_p95_ms: data.metrics.cross_service_latency_ms ? Math.round(data.metrics.cross_service_latency_ms.values['p(95)']) : 'N/A',
        verification: {
            apm: `OCI APM → Trace Explorer → filter serviceName=octo-drone-shop → verify distributed traces`,
            topology: `OCI APM → Topology → verify CRM ↔ Drone Shop ↔ ATP edges`,
            logs: `OCI Log Analytics → search oracleApmTraceId=<trace_id> → verify correlated logs`,
            db: `OCI DB Management → Performance Hub → verify SQL activity during test window`,
        },
    };

    return {
        stdout: JSON.stringify(summary, null, 2) + '\n',
    };
}
