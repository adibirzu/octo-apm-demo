/*
 * Enterprise CRM Portal — Order-to-Cash SLO Validation
 *
 * End-to-end business flow test that validates both correctness and performance.
 * Unlike load_test.js (which focuses on traffic generation), this test verifies
 * that complete business workflows succeed within SLO thresholds.
 *
 * Usage:
 *   k6 run --env BASE_URL=http://localhost:8080 k6/order_to_cash.js
 */

import http from 'k6/http';
import { check, group, sleep, fail } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';

// Custom metrics for business flow visibility
const flowDuration = new Trend('crm_order_to_cash_duration', true);
const loginLatency = new Trend('crm_login_latency', true);
const orderCreateLatency = new Trend('crm_order_create_latency', true);
const invoiceLatency = new Trend('crm_invoice_latency', true);
const flowSuccess = new Rate('crm_order_to_cash_success');
const flowErrors = new Counter('crm_order_to_cash_errors');

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const LOGIN_USER = __ENV.LOGIN_USER || 'admin';
const LOGIN_PASS = __ENV.LOGIN_PASS || __ENV.BOOTSTRAP_ADMIN_PASSWORD || '';

if (!LOGIN_PASS) {
    fail('Set LOGIN_PASS or BOOTSTRAP_ADMIN_PASSWORD before running this script.');
}

export const options = {
    scenarios: {
        // Steady-state business flow
        order_to_cash: {
            executor: 'ramping-vus',
            startVUs: 2,
            stages: [
                { duration: '1m', target: 10 },
                { duration: '3m', target: 20 },
                { duration: '2m', target: 30 },
                { duration: '1m', target: 5 },
                { duration: '30s', target: 0 },
            ],
            tags: { flow: 'order_to_cash' },
        },

        // SLO canary — single VU running continuously to detect availability drops
        slo_canary: {
            executor: 'constant-arrival-rate',
            rate: 1,
            timeUnit: '10s',
            duration: '7m30s',
            preAllocatedVUs: 1,
            maxVUs: 2,
            exec: 'sloCanary',
            tags: { flow: 'slo_canary' },
        },
    },

    thresholds: {
        // SLO thresholds
        'http_req_failed{flow:order_to_cash}': ['rate<0.01'],        // 99% success
        'http_req_duration{flow:order_to_cash}': ['p(95)<900'],       // p95 < 900ms
        'crm_order_to_cash_success': ['rate>0.95'],                   // 95% flow completion
        'crm_login_latency': ['p(95)<2000'],                          // login < 2s p95
        'crm_order_create_latency': ['p(95)<1500'],                   // order create < 1.5s p95
        'checks{flow:slo_canary}': ['rate>0.99'],                     // canary 99% pass
    },
};

const HEADERS = { 'Content-Type': 'application/json' };

// ── Main Order-to-Cash Flow ──────────────────────────────────────

export default function () {
    const flowStart = Date.now();
    let flowOk = true;

    group('1. Login', () => {
        const start = Date.now();
        const res = http.post(`${BASE_URL}/api/auth/login`,
            JSON.stringify({ username: LOGIN_USER, password: LOGIN_PASS }),
            { headers: HEADERS }
        );
        loginLatency.add(Date.now() - start);

        const loginOk = check(res, {
            'login status 200': (r) => r.status === 200,
            'login returns session': (r) => {
                try { return JSON.parse(r.body).status === 'success'; }
                catch { return false; }
            },
        });
        if (!loginOk) { flowOk = false; flowErrors.add(1); }
        sleep(0.5);
    });

    group('2. Browse Customers', () => {
        const res = http.get(`${BASE_URL}/api/customers`);
        const ok = check(res, {
            'customers loads': (r) => r.status === 200,
            'customers has data': (r) => {
                try { return JSON.parse(r.body).customers.length > 0; }
                catch { return false; }
            },
        });
        if (!ok) flowOk = false;
        sleep(0.5);
    });

    group('3. Browse Products', () => {
        const res = http.get(`${BASE_URL}/api/products`);
        const ok = check(res, {
            'products loads': (r) => r.status === 200,
            'products has data': (r) => {
                try { return JSON.parse(r.body).products.length > 0; }
                catch { return false; }
            },
        });
        if (!ok) flowOk = false;
        sleep(0.5);
    });

    group('4. Create Order', () => {
        const start = Date.now();
        const res = http.post(`${BASE_URL}/api/orders`,
            JSON.stringify({
                customer_id: 1,
                items: [{ product_id: 1, quantity: 2 }],
                notes: `k6 load test order VU=${__VU} iter=${__ITER}`,
            }),
            { headers: HEADERS }
        );
        orderCreateLatency.add(Date.now() - start);

        const ok = check(res, {
            'order created': (r) => r.status === 200,
            'order has id': (r) => {
                try { return JSON.parse(r.body).order_id > 0; }
                catch { return false; }
            },
        });
        if (!ok) { flowOk = false; flowErrors.add(1); }
        sleep(0.5);
    });

    group('5. Check Invoices', () => {
        const start = Date.now();
        const res = http.get(`${BASE_URL}/api/invoices`);
        invoiceLatency.add(Date.now() - start);

        check(res, {
            'invoices loads': (r) => r.status === 200,
        });
        sleep(0.5);
    });

    group('6. Check Dashboard', () => {
        const res = http.get(`${BASE_URL}/api/dashboard/summary`);
        check(res, {
            'dashboard loads': (r) => r.status === 200,
            'dashboard has stats': (r) => {
                try { return JSON.parse(r.body).total_customers !== undefined; }
                catch { return false; }
            },
        });
        sleep(0.5);
    });

    flowDuration.add(Date.now() - flowStart);
    flowSuccess.add(flowOk);
}

// ── SLO Canary ───────────────────────────────────────────────────

export function sloCanary() {
    // Health
    const health = http.get(`${BASE_URL}/health`);
    check(health, { 'health ok': (r) => r.status === 200 });

    // Readiness (DB check)
    const ready = http.get(`${BASE_URL}/ready`);
    check(ready, {
        'ready ok': (r) => r.status === 200,
        'db connected': (r) => {
            try { return JSON.parse(r.body).database === 'connected'; }
            catch { return false; }
        },
    });

    // Quick API check
    const dash = http.get(`${BASE_URL}/api/dashboard/summary`);
    check(dash, { 'dashboard ok': (r) => r.status === 200 });
}
