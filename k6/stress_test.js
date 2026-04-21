/*
 * Enterprise CRM Portal — Simulation & Chaos Stress Test
 *
 * Exercises the simulation/chaos engineering endpoints alongside normal CRM
 * traffic to generate rich OCI Observability data:
 *
 *   - OCI APM:  Distributed traces with error spans, slow spans, N+1 patterns
 *   - OCI Logging:  Structured JSON logs with severity spikes, security events
 *   - OCI Log Analytics:  Correlation via oracleApmTraceId across services
 *   - OCI Monitoring:  Custom business metrics (orders, revenue, error rates)
 *   - OCI DB Management:  SQL execution spikes, slow query patterns
 *
 * Usage:
 *   # Smoke test (1 VU, 30s)
 *   k6 run --env BASE_URL=https://crm.example.cloud --env LOGIN_PASS='<password>' --env PROFILE=smoke k6/stress_test.js
 *
 *   # Against any domain
 *   k6 run --env DNS_DOMAIN=example.cloud --env LOGIN_PASS='<password>' k6/stress_test.js
 *
 *   # Heavy load
 *   k6 run --env DNS_DOMAIN=example.cloud --env LOGIN_PASS='<password>' --env PROFILE=heavy k6/stress_test.js
 *
 * After the run, verify in OCI Console:
 *   1. APM → Trace Explorer → filter serviceName=enterprise-crm-portal
 *      → look for error spans (simulation.app_exception, simulation.error_burst)
 *   2. APM → Topology → verify CRM → ATP edge with elevated latency
 *   3. Log Analytics → search: oracleApmTraceId=<any trace_id>
 *      → verify app logs + DB logs correlate
 *   4. Monitoring → Metrics Explorer → custom namespace "enterprise_crm"
 *      → verify order_count, login_count, error_rate metrics
 *   5. DB Management → Performance Hub → verify SQL spikes during test window
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// ── Configuration ───────────────────────────────────────────────
const DNS_DOMAIN = __ENV.DNS_DOMAIN || '';
const BASE_URL = __ENV.BASE_URL || (DNS_DOMAIN ? `https://crm.${DNS_DOMAIN}` : 'http://localhost:8080');
const SHOP_URL = __ENV.SHOP_URL || (DNS_DOMAIN ? `https://shop.${DNS_DOMAIN}` : '');
const PROFILE = (__ENV.PROFILE || 'moderate').toLowerCase();
const LOGIN_USER = __ENV.LOGIN_USER || 'admin';
const LOGIN_PASS = __ENV.LOGIN_PASS || __ENV.BOOTSTRAP_ADMIN_PASSWORD || '';

if (!LOGIN_PASS) {
    throw new Error('Set LOGIN_PASS or BOOTSTRAP_ADMIN_PASSWORD before running this script.');
}

// ── Custom Metrics ──────────────────────────────────────────────
const errorRate = new Rate('errors');
const loginLatency = new Trend('login_latency_ms');
const simulationLatency = new Trend('simulation_latency_ms');
const orderGenLatency = new Trend('order_gen_latency_ms');
const chaosLatency = new Trend('chaos_latency_ms');
const dbStressLatency = new Trend('db_stress_latency_ms');
const crossServiceLatency = new Trend('cross_service_latency_ms');
const apiCalls = new Counter('api_calls');
const ordersGenerated = new Counter('orders_generated');
const chaosTriggered = new Counter('chaos_triggered');
const securityEvents = new Counter('security_events');

// ── Profiles ────────────────────────────────────────────────────
const PROFILES = {
    smoke: {
        normal:  { stages: [{ duration: '10s', target: 1 }, { duration: '20s', target: 1 }] },
        chaos:   { vus: 1, iterations: 3 },
        datagen: { vus: 1, iterations: 2 },
    },
    moderate: {
        normal:  { stages: [{ duration: '30s', target: 5 }, { duration: '2m', target: 15 }, { duration: '1m', target: 25 }, { duration: '30s', target: 5 }, { duration: '10s', target: 0 }] },
        chaos:   { vus: 3, iterations: 20 },
        datagen: { vus: 2, iterations: 15 },
    },
    heavy: {
        normal:  { stages: [{ duration: '30s', target: 10 }, { duration: '2m', target: 40 }, { duration: '3m', target: 60 }, { duration: '1m', target: 20 }, { duration: '30s', target: 0 }] },
        chaos:   { vus: 5, iterations: 40 },
        datagen: { vus: 5, iterations: 30 },
    },
};

const P = PROFILES[PROFILE] || PROFILES.moderate;

export const options = {
    scenarios: {
        // Scenario 1: Normal CRM browsing + CRUD with auth
        normal_traffic: {
            executor: 'ramping-vus',
            startVUs: 1,
            stages: P.normal.stages,
            exec: 'normalTraffic',
        },
        // Scenario 2: Chaos injection — triggers simulation incidents
        chaos_injection: {
            executor: 'per-vu-iterations',
            vus: P.chaos.vus,
            iterations: P.chaos.iterations,
            startTime: '15s',
            exec: 'chaosInjection',
        },
        // Scenario 3: Demo data generation under load
        data_generation: {
            executor: 'per-vu-iterations',
            vus: P.datagen.vus,
            iterations: P.datagen.iterations,
            startTime: '20s',
            exec: 'dataGeneration',
        },
        // Scenario 4: Cross-service proxy (CRM → Drone Shop)
        cross_service: {
            executor: 'per-vu-iterations',
            vus: 2,
            iterations: 10,
            startTime: '30s',
            exec: 'crossServiceProxy',
        },
        // Scenario 5: Observability endpoints (generates ATP load)
        observability: {
            executor: 'constant-arrival-rate',
            rate: 2,
            timeUnit: '1s',
            duration: P.normal.stages.reduce((s, st) => s + parseInt(st.duration), 0) + 's',
            preAllocatedVUs: 2,
            maxVUs: 5,
            startTime: '5s',
            exec: 'observabilityPoll',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<5000'],
        errors: ['rate<0.20'],  // Higher threshold — chaos generates errors
        login_latency_ms: ['p(95)<2000'],
        simulation_latency_ms: ['p(95)<12000'],  // Some simulations take 10s
        order_gen_latency_ms: ['p(95)<3000'],
    },
};

// ── Helpers ──────────────────────────────────────────────────────

function correlationHeaders() {
    return {
        'X-Correlation-Id': `k6-stress-${uuidv4()}`,
        'Content-Type': 'application/json',
    };
}

function loginAndGetSession() {
    const h = correlationHeaders();
    const start = Date.now();
    const res = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
        username: LOGIN_USER,
        password: LOGIN_PASS,
    }), { headers: h, tags: { name: 'login' } });
    loginLatency.add(Date.now() - start);
    apiCalls.add(1);

    if (res.status === 200) {
        try {
            const body = res.json();
            return body.session_id || '';
        } catch (_) {}
    }
    errorRate.add(1);
    return '';
}

function authedGet(path, sessionId) {
    const h = correlationHeaders();
    const res = http.get(`${BASE_URL}${path}`, {
        headers: h,
        cookies: { session_id: sessionId },
        tags: { name: path },
    });
    apiCalls.add(1);
    errorRate.add(res.status >= 400);
    return res;
}

function authedPost(path, body, sessionId) {
    const h = correlationHeaders();
    const res = http.post(`${BASE_URL}${path}`, JSON.stringify(body), {
        headers: h,
        cookies: { session_id: sessionId },
        tags: { name: path },
    });
    apiCalls.add(1);
    errorRate.add(res.status >= 400 && res.status !== 503);  // 503 = expected during chaos
    return res;
}

// ── Scenario 1: Normal CRM Traffic ──────────────────────────────

export function normalTraffic() {
    const sessionId = loginAndGetSession();
    if (!sessionId) return;

    group('Dashboard', () => {
        authedGet('/', sessionId);
        sleep(0.5);
        authedGet('/api/dashboard/summary', sessionId);
        sleep(0.3);
    });

    group('Customers', () => {
        authedGet('/api/customers', sessionId);
        sleep(0.3);
    });

    group('Orders', () => {
        authedGet('/api/orders', sessionId);
        sleep(0.3);
    });

    group('Products', () => {
        authedGet('/api/products', sessionId);
        sleep(0.3);
    });

    group('Tickets', () => {
        authedGet('/api/tickets', sessionId);
        sleep(0.3);
    });

    group('Integrations', () => {
        authedGet('/api/integrations/status', sessionId);
        sleep(0.3);
    });

    sleep(1);
}

// ── Scenario 2: Chaos Injection ─────────────────────────────────

const CHAOS_ACTIONS = [
    { path: '/api/simulate/db-latency', body: { delay_seconds: 2 }, name: 'db_latency' },
    { path: '/api/simulate/error-burst', body: { count: 5 }, name: 'error_burst' },
    { path: '/api/simulate/slow-query', body: { delay_seconds: 2 }, name: 'slow_query' },
    { path: '/api/simulate/n-plus-one', body: { count: 30 }, name: 'n_plus_one' },
    { path: '/api/simulate/app-exception', body: {}, name: 'app_exception' },
    { path: '/api/simulate/db-error', body: {}, name: 'db_error' },
];

export function chaosInjection() {
    const sessionId = loginAndGetSession();
    if (!sessionId) return;

    const action = CHAOS_ACTIONS[Math.floor(Math.random() * CHAOS_ACTIONS.length)];

    group(`Chaos: ${action.name}`, () => {
        const start = Date.now();
        const res = authedPost(action.path, action.body, sessionId);
        chaosLatency.add(Date.now() - start);
        chaosTriggered.add(1);

        check(res, {
            [`${action.name} completes`]: (r) => r.status === 200,
        });
    });

    // Generate traffic DURING chaos to measure impact
    group('Traffic during chaos', () => {
        const res = authedGet('/api/customers', sessionId);
        check(res, {
            'customers during chaos': (r) => r.status === 200 || r.status === 503,
        });
    });

    sleep(2);
}

// ── Scenario 3: Data Generation ─────────────────────────────────

export function dataGeneration() {
    const sessionId = loginAndGetSession();
    if (!sessionId) return;

    // Generate orders
    group('Generate Orders', () => {
        const start = Date.now();
        const res = authedPost('/api/simulate/generate-orders', {
            count: Math.floor(Math.random() * 5) + 1,
            status: ['processing', 'pending', 'shipped'][Math.floor(Math.random() * 3)],
        }, sessionId);
        orderGenLatency.add(Date.now() - start);

        if (res.status === 200) {
            try {
                const body = res.json();
                ordersGenerated.add(body.orders_created || 0);
            } catch (_) {}
        }
    });
    sleep(0.5);

    // Generate high-value order (triggers anomaly detection)
    if (Math.random() < 0.3) {
        group('High-Value Order', () => {
            const res = authedPost('/api/simulate/high-value-order', {}, sessionId);
            securityEvents.add(1);
            check(res, {
                'high-value order triggers alert': (r) => {
                    try { return r.json().alert_triggered === true; }
                    catch (_) { return false; }
                },
            });
        });
        sleep(0.5);
    }

    // Generate backlog (triggers backlog detection)
    if (Math.random() < 0.3) {
        group('Generate Backlog', () => {
            authedPost('/api/simulate/generate-backlog', { count: 3 }, sessionId);
        });
        sleep(0.5);
    }

    // Add random customer
    group('Add Customer', () => {
        authedPost('/api/simulate/add-customer', {}, sessionId);
    });

    sleep(1);
}

// ── Scenario 4: Cross-Service Proxy ─────────────────────────────

export function crossServiceProxy() {
    const sessionId = loginAndGetSession();
    if (!sessionId) return;

    // Skip if shop URL not configured
    group('Drone Shop Status', () => {
        const start = Date.now();
        const res = authedGet('/api/simulate/drone-shop/status', sessionId);
        crossServiceLatency.add(Date.now() - start);

        if (res.status === 200) {
            try {
                const data = res.json();
                if (data.status === 'skipped') {
                    return;  // Shop not configured
                }
            } catch (_) {}
        }
    });
    sleep(0.5);

    // Trigger sync from shop
    group('Sync from Drone Shop', () => {
        const start = Date.now();
        const res = authedPost('/api/simulate/sync-customers', {}, sessionId);
        crossServiceLatency.add(Date.now() - start);
        check(res, {
            'sync completes or reports error': (r) => r.status === 200,
        });
    });
    sleep(0.5);

    // Integration health
    group('Integration Health', () => {
        authedGet('/api/integrations/drone-shop/health', sessionId);
    });

    sleep(1);
}

// ── Scenario 5: Observability Poll ──────────────────────────────

export function observabilityPoll() {
    const sessionId = loginAndGetSession();
    if (!sessionId) return;

    const ENDPOINTS = [
        '/api/observability/360',
        '/api/observability/360/app-health',
        '/api/observability/360/db-health',
        '/api/observability/360/sync-health',
        '/api/observability/360/security',
        '/api/simulate/status',
    ];

    const ep = ENDPOINTS[Math.floor(Math.random() * ENDPOINTS.length)];
    const start = Date.now();
    const res = authedGet(ep, sessionId);
    dbStressLatency.add(Date.now() - start);

    check(res, {
        [`${ep} ok`]: (r) => r.status === 200,
    });
}

// ── Setup & Teardown ────────────────────────────────────────────

export function setup() {
    // Reset simulation state before the run
    const h = correlationHeaders();
    const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
        username: LOGIN_USER,
        password: LOGIN_PASS,
    }), { headers: h });

    if (loginRes.status === 200) {
        const sid = loginRes.json().session_id;
        http.post(`${BASE_URL}/api/simulate/reset`, '{}', {
            headers: h,
            cookies: { session_id: sid },
        });
        console.log(`[setup] Simulation state reset. Profile: ${PROFILE}, Base: ${BASE_URL}`);
    }

    return { started: new Date().toISOString() };
}

export function teardown(data) {
    // Reset simulation state after the run
    const h = correlationHeaders();
    const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
        username: LOGIN_USER,
        password: LOGIN_PASS,
    }), { headers: h });

    if (loginRes.status === 200) {
        const sid = loginRes.json().session_id;
        http.post(`${BASE_URL}/api/simulate/reset`, '{}', {
            headers: h,
            cookies: { session_id: sid },
        });
        console.log('[teardown] Simulation state reset.');
    }
}

// ── Summary ─────────────────────────────────────────────────────

export function handleSummary(data) {
    const summary = {
        test: 'Enterprise CRM Portal — Simulation Stress Test',
        profile: PROFILE,
        base_url: BASE_URL,
        shop_url: SHOP_URL || '(not configured)',
        dns_domain: DNS_DOMAIN || '(local)',
        total_requests: data.metrics.api_calls ? data.metrics.api_calls.values.count : 0,
        orders_generated: data.metrics.orders_generated ? data.metrics.orders_generated.values.count : 0,
        chaos_events: data.metrics.chaos_triggered ? data.metrics.chaos_triggered.values.count : 0,
        security_events: data.metrics.security_events ? data.metrics.security_events.values.count : 0,
        error_rate: data.metrics.errors ? (data.metrics.errors.values.rate * 100).toFixed(1) + '%' : 'N/A',
        p95_login_ms: data.metrics.login_latency_ms ? Math.round(data.metrics.login_latency_ms.values['p(95)']) : 'N/A',
        p95_order_gen_ms: data.metrics.order_gen_latency_ms ? Math.round(data.metrics.order_gen_latency_ms.values['p(95)']) : 'N/A',
        p95_chaos_ms: data.metrics.chaos_latency_ms ? Math.round(data.metrics.chaos_latency_ms.values['p(95)']) : 'N/A',
        oci_verification: {
            apm_traces: `APM → Trace Explorer → serviceName=enterprise-crm-portal → verify error/slow spans`,
            apm_topology: `APM → Topology → verify CRM → ATP edge, CRM → DroneShop edge`,
            log_analytics: `Log Analytics → oracleApmTraceId=<trace_id> → correlate app + DB logs`,
            monitoring: `Monitoring → enterprise_crm namespace → verify order_count, error_rate`,
            db_management: `DB Management → Performance Hub → SQL activity during test window`,
            ops_insights: `Operations Insights → SQL Warehouse → verify new query patterns`,
        },
    };

    return {
        stdout: JSON.stringify(summary, null, 2) + '\n',
    };
}
