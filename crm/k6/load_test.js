/*
 * Enterprise CRM Portal — k6 Load Test
 *
 * Multi-location end-to-end testing for performance and security.
 * Inspired by: https://grafana.com/blog/load-testing-websites/
 *
 * Usage:
 *   k6 run --env BASE_URL=http://localhost:8080 k6/load_test.js
 *   k6 run --env BASE_URL=https://crm.example.com k6/load_test.js
 *
 * k6 Cloud (multi-location):
 *   k6 cloud k6/load_test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const loginDuration = new Trend('login_duration');
const dashboardDuration = new Trend('dashboard_duration');
const searchDuration = new Trend('search_duration');
const geoLatency = new Trend('geo_latency');
const apiCalls = new Counter('api_calls');

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const LOGIN_USER = __ENV.LOGIN_USER || 'admin';
const LOGIN_PASS = __ENV.LOGIN_PASS || __ENV.BOOTSTRAP_ADMIN_PASSWORD || '';

if (!LOGIN_PASS) {
    throw new Error('Set LOGIN_PASS or BOOTSTRAP_ADMIN_PASSWORD before running this script.');
}

export const options = {
    // Ramp-up scenario simulating real user patterns
    scenarios: {
        // Normal browsing users
        browse: {
            executor: 'ramping-vus',
            startVUs: 1,
            stages: [
                { duration: '30s', target: 5 },
                { duration: '1m', target: 15 },
                { duration: '2m', target: 25 },
                { duration: '30s', target: 5 },
                { duration: '10s', target: 0 },
            ],
            gracefulRampDown: '10s',
        },
        // API load (higher throughput)
        api_load: {
            executor: 'constant-arrival-rate',
            rate: 20,
            timeUnit: '1s',
            duration: '3m',
            preAllocatedVUs: 10,
            maxVUs: 30,
            startTime: '30s', // start after browse ramp-up
        },
        // Geo-distributed browsing (simulates users from different regions)
        geo_browse: {
            executor: 'per-vu-iterations',
            vus: 6,
            iterations: 20,
            startTime: '15s',
            exec: 'geo_browse',
        },
        // Attack simulation (SQLi, XSS probes)
        security_probes: {
            executor: 'per-vu-iterations',
            vus: 3,
            iterations: 50,
            startTime: '1m',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<3000', 'p(99)<5000'],
        errors: ['rate<0.1'],
        login_duration: ['p(95)<2000'],
        dashboard_duration: ['p(95)<3000'],
    },
};

// ── Browsing Scenario ───────────────────────────────────────────

export default function() {
    group('User Journey', () => {
        // 1. Load landing page
        group('Landing Page', () => {
            const res = http.get(`${BASE_URL}/`);
            check(res, { 'landing page loads': (r) => r.status === 200 });
            errorRate.add(res.status !== 200);
            apiCalls.add(1);
            sleep(1);
        });

        // 2. Login
        group('Login', () => {
            const start = Date.now();
            const res = http.post(`${BASE_URL}/api/auth/login`,
                JSON.stringify({ username: LOGIN_USER, password: LOGIN_PASS }),
                { headers: { 'Content-Type': 'application/json' } }
            );
            loginDuration.add(Date.now() - start);
            check(res, { 'login succeeds': (r) => r.status === 200 });
            errorRate.add(res.status !== 200);
            apiCalls.add(1);
            sleep(0.5);
        });

        // 3. Dashboard
        group('Dashboard', () => {
            const start = Date.now();
            const res = http.get(`${BASE_URL}/api/dashboard/summary`);
            dashboardDuration.add(Date.now() - start);
            check(res, { 'dashboard loads': (r) => r.status === 200 });
            errorRate.add(res.status !== 200);
            apiCalls.add(1);
            sleep(2);
        });

        // 4. Browse customers
        group('Customers', () => {
            const res = http.get(`${BASE_URL}/api/customers`);
            check(res, { 'customers list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);

            // View a specific customer
            const detail = http.get(`${BASE_URL}/api/customers/1`);
            check(detail, { 'customer detail loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 5. Search customers
        group('Search', () => {
            const start = Date.now();
            const res = http.get(`${BASE_URL}/api/customers?search=Acme`);
            searchDuration.add(Date.now() - start);
            check(res, { 'search works': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 6. Browse orders
        group('Orders', () => {
            const res = http.get(`${BASE_URL}/api/orders`);
            check(res, { 'orders list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 7. Browse products
        group('Products', () => {
            const res = http.get(`${BASE_URL}/api/products`);
            check(res, { 'products list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 8. Check invoices
        group('Invoices', () => {
            const res = http.get(`${BASE_URL}/api/invoices`);
            check(res, { 'invoices list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 9. Support tickets
        group('Tickets', () => {
            const res = http.get(`${BASE_URL}/api/tickets`);
            check(res, { 'tickets list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 10. Campaigns
        group('Campaigns', () => {
            const res = http.get(`${BASE_URL}/api/campaigns`);
            check(res, { 'campaigns list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 11. Shipping
        group('Shipping', () => {
            const res = http.get(`${BASE_URL}/api/shipping`);
            check(res, { 'shipping list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 12. Analytics overview
        group('Analytics', () => {
            const res = http.get(`${BASE_URL}/api/analytics/overview`);
            check(res, { 'analytics loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 13. Health check
        group('Health', () => {
            const res = http.get(`${BASE_URL}/health`);
            check(res, { 'health ok': (r) => r.status === 200 });
            apiCalls.add(1);
        });
    });
}

// ── API Load Scenario ───────────────────────────────────────────

export function api_load() {
    const endpoints = [
        '/api/dashboard/summary',
        '/api/customers',
        '/api/orders',
        '/api/products',
        '/api/invoices',
        '/api/tickets',
        '/api/campaigns',
        '/api/shipping',
        '/api/shipping/warehouses',
        '/api/analytics/overview',
        '/api/analytics/funnel',
        '/api/modules',
        '/health',
        '/ready',
    ];

    const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
    const res = http.get(`${BASE_URL}${endpoint}`);
    check(res, { 'api responds': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
    apiCalls.add(1);
}

// ── Security Probes Scenario ────────────────────────────────────

export function security_probes() {
    const attacks = [
        // SQLi probes
        { url: `/api/customers?search=' OR '1'='1`, name: 'sqli_basic' },
        { url: `/api/customers?search=' UNION SELECT * FROM users--`, name: 'sqli_union' },
        { url: `/api/customers?sort_by=name; DROP TABLE customers`, name: 'sqli_drop' },
        { url: `/api/products?category=' OR 1=1--`, name: 'sqli_products' },

        // XSS probes
        { url: `/api/tickets?search=<script>alert(1)</script>`, name: 'xss_reflected' },
        { url: `/api/customers?search=<img onerror=alert(1) src=x>`, name: 'xss_img' },

        // Path traversal
        { url: `/api/files/download?path=../../../etc/passwd`, name: 'path_traversal' },

        // SSRF
        {
            url: `/api/files/import-url`,
            name: 'ssrf_metadata',
            method: 'POST',
            body: JSON.stringify({ url: 'http://169.254.169.254/latest/meta-data/' }),
        },

        // Analytics SQLi (geo endpoint)
        { url: `/api/analytics/geo?region=' OR '1'='1`, name: 'sqli_analytics_geo' },
        { url: `/api/analytics/geo?region=us-east-1' UNION SELECT * FROM users--`, name: 'sqli_analytics_union' },

        // Campaign XSS via lead notes
        {
            url: `/api/campaigns/1/leads`,
            name: 'xss_lead_notes',
            method: 'POST',
            body: JSON.stringify({ email: 'test@evil.com', name: 'Test', notes: '<script>document.cookie</script>' }),
        },

        // IDOR on campaigns and shipping
        { url: `/api/campaigns/999`, name: 'idor_campaign' },
        { url: `/api/shipping/999`, name: 'idor_shipment' },

        // Admin access (no auth)
        { url: `/api/admin/config`, name: 'admin_config_access' },
        { url: `/api/admin/users`, name: 'admin_user_list' },
    ];

    const attack = attacks[Math.floor(Math.random() * attacks.length)];

    let res;
    if (attack.method === 'POST') {
        res = http.post(`${BASE_URL}${attack.url}`, attack.body, {
            headers: { 'Content-Type': 'application/json' },
            tags: { attack_type: attack.name },
        });
    } else {
        res = http.get(`${BASE_URL}${attack.url}`, {
            tags: { attack_type: attack.name },
        });
    }

    apiCalls.add(1);
    sleep(0.5);
}

// ── Geo-distributed Browsing Scenario ─────────────────────────

const REGIONS = [
    'eu-central-1',    // Frankfurt (local)
    'us-east-1',       // Virginia
    'us-west-2',       // Oregon
    'ap-southeast-1',  // Singapore
    'ap-northeast-1',  // Tokyo
    'sa-east-1',       // São Paulo
    'af-south-1',      // Cape Town
    'me-south-1',      // Bahrain
    'ap-southeast-2',  // Sydney
];

export function geo_browse() {
    // Each VU simulates a user from a random region
    const region = REGIONS[Math.floor(Math.random() * REGIONS.length)];
    const headers = { 'X-Client-Region': region };

    group(`Geo Browse [${region}]`, () => {
        // 1. Dashboard from this region
        const start1 = Date.now();
        const dash = http.get(`${BASE_URL}/api/dashboard/summary`, { headers });
        geoLatency.add(Date.now() - start1, { region: region });
        check(dash, { 'geo dashboard loads': (r) => r.status === 200 });
        apiCalls.add(1);
        sleep(0.5);

        // 2. Analytics overview
        const start2 = Date.now();
        const analytics = http.get(`${BASE_URL}/api/analytics/overview`, { headers });
        geoLatency.add(Date.now() - start2, { region: region });
        check(analytics, { 'geo analytics loads': (r) => r.status === 200 });
        apiCalls.add(1);
        sleep(0.5);

        // 3. Shipping by region
        const start3 = Date.now();
        const shipping = http.get(`${BASE_URL}/api/shipping/by-region?region=${region}`, { headers });
        geoLatency.add(Date.now() - start3, { region: region });
        check(shipping, { 'geo shipping loads': (r) => r.status === 200 });
        apiCalls.add(1);
        sleep(0.5);

        // 4. Performance stats for this region
        const start4 = Date.now();
        const perf = http.get(`${BASE_URL}/api/analytics/performance?region=${region}`, { headers });
        geoLatency.add(Date.now() - start4, { region: region });
        check(perf, { 'geo performance loads': (r) => r.status === 200 });
        apiCalls.add(1);
        sleep(0.5);

        // 5. Track a page view from this region
        http.post(`${BASE_URL}/api/analytics/track`,
            JSON.stringify({
                page: '/dashboard',
                visitor_region: region,
                load_time_ms: Date.now() - start1,
            }),
            { headers: { ...headers, 'Content-Type': 'application/json' } }
        );
        apiCalls.add(1);

        // 6. Campaigns
        const camps = http.get(`${BASE_URL}/api/campaigns`, { headers });
        check(camps, { 'geo campaigns loads': (r) => r.status === 200 });
        apiCalls.add(1);
        sleep(0.5);
    });
}
