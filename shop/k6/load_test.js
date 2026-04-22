/*
 * OCTO Drone Shop — k6 Load Test
 *
 * Multi-scenario testing: browsing, API load, geo-distributed, security probes
 *
 * Usage:
 *   k6 run --env BASE_URL=http://localhost:8080 k6/load_test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const errorRate = new Rate('errors');
const shopDuration = new Trend('shop_duration');
const geoLatency = new Trend('geo_latency');
const apiCalls = new Counter('api_calls');

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

export const options = {
    scenarios: {
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
        },
        api_load: {
            executor: 'constant-arrival-rate',
            rate: 20, timeUnit: '1s',
            duration: '3m', preAllocatedVUs: 10, maxVUs: 30,
            startTime: '30s',
        },
        geo_browse: {
            executor: 'per-vu-iterations',
            vus: 6, iterations: 20,
            startTime: '15s', exec: 'geo_browse',
        },
        security_probes: {
            executor: 'per-vu-iterations',
            vus: 3, iterations: 50,
            startTime: '1m',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<3000'],
        errors: ['rate<0.1'],
    },
};

// ── Browse Scenario ─────────────────────────────────────────

export default function() {
    group('Shopping Journey', () => {
        group('Landing', () => {
            const res = http.get(`${BASE_URL}/`);
            check(res, { 'landing loads': (r) => r.status === 200 });
            apiCalls.add(1); sleep(1);
        });

        group('Shop', () => {
            const start = Date.now();
            const res = http.get(`${BASE_URL}/api/shop/featured`);
            shopDuration.add(Date.now() - start);
            check(res, { 'featured loads': (r) => r.status === 200 });
            apiCalls.add(1); sleep(1);
        });

        group('Catalogue', () => {
            const res = http.get(`${BASE_URL}/api/products`);
            check(res, { 'products list': (r) => r.status === 200 });
            apiCalls.add(1); sleep(1);

            const detail = http.get(`${BASE_URL}/api/products/1`);
            check(detail, { 'product detail': (r) => r.status === 200 });
            apiCalls.add(1); sleep(0.5);

            const reviews = http.get(`${BASE_URL}/api/products/1/reviews`);
            check(reviews, { 'reviews load': (r) => r.status === 200 });
            apiCalls.add(1); sleep(0.5);
        });

        group('Cart', () => {
            http.post(`${BASE_URL}/api/cart/add`,
                JSON.stringify({ product_id: 1, quantity: 2 }),
                { headers: { 'Content-Type': 'application/json' } });
            apiCalls.add(1); sleep(0.5);

            const cart = http.get(`${BASE_URL}/api/cart?session_id=k6-session`);
            check(cart, { 'cart loads': (r) => r.status === 200 });
            apiCalls.add(1); sleep(0.5);
        });

        group('Orders', () => {
            const res = http.get(`${BASE_URL}/api/orders`);
            check(res, { 'orders list': (r) => r.status === 200 });
            apiCalls.add(1); sleep(1);
        });

        group('Shipping', () => {
            const res = http.get(`${BASE_URL}/api/shipping`);
            check(res, { 'shipping list': (r) => r.status === 200 });
            apiCalls.add(1); sleep(1);
        });

        group('Campaigns', () => {
            const res = http.get(`${BASE_URL}/api/campaigns`);
            check(res, { 'campaigns list': (r) => r.status === 200 });
            apiCalls.add(1); sleep(1);
        });

        group('Analytics', () => {
            const res = http.get(`${BASE_URL}/api/analytics/overview`);
            check(res, { 'analytics loads': (r) => r.status === 200 });
            apiCalls.add(1); sleep(1);
        });

        group('Health', () => {
            const res = http.get(`${BASE_URL}/health`);
            check(res, { 'health ok': (r) => r.status === 200 });
            apiCalls.add(1);
        });
    });
}

// ── API Load Scenario ───────────────────────────────────────

export function api_load() {
    const endpoints = [
        '/api/shop/featured', '/api/products', '/api/orders',
        '/api/shipping', '/api/campaigns', '/api/analytics/overview',
        '/api/analytics/funnel', '/api/dashboard/summary',
        '/api/shipping/warehouses', '/api/modules', '/health',
    ];
    const ep = endpoints[Math.floor(Math.random() * endpoints.length)];
    const res = http.get(`${BASE_URL}${ep}`);
    check(res, { 'api responds': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
    apiCalls.add(1);
}

// ── Security Probes ─────────────────────────────────────────

export function security_probes() {
    const attacks = [
        { url: `/api/products?search=' OR '1'='1`, name: 'sqli_search' },
        { url: `/api/products?search=' UNION SELECT * FROM users--`, name: 'sqli_union' },
        { url: `/api/products?sort_by=name; DROP TABLE products`, name: 'sqli_sort' },
        { url: `/api/analytics/geo?region=' OR '1'='1`, name: 'sqli_geo' },
        { url: `/api/products/1/reviews`, name: 'xss_review', method: 'POST',
          body: JSON.stringify({ rating: 5, comment: '<script>alert(1)</script>', author_name: 'xss' }) },
        { url: `/api/admin/config`, name: 'info_disclosure' },
        { url: `/api/admin/users`, name: 'admin_access' },
        { url: `/api/orders/999`, name: 'idor_order' },
        { url: `/api/campaigns/999`, name: 'idor_campaign' },
        { url: `/api/shop/wallet?user_id=999`, name: 'idor_wallet' },
        { url: `/api/shop/checkout`, name: 'csrf_checkout', method: 'POST',
          body: JSON.stringify({ items: [{ id: 1 }], total: 0.01 }) },
    ];

    const attack = attacks[Math.floor(Math.random() * attacks.length)];
    let res;
    if (attack.method === 'POST') {
        res = http.post(`${BASE_URL}${attack.url}`, attack.body,
            { headers: { 'Content-Type': 'application/json' }, tags: { attack_type: attack.name } });
    } else {
        res = http.get(`${BASE_URL}${attack.url}`, { tags: { attack_type: attack.name } });
    }
    apiCalls.add(1); sleep(0.5);
}

// ── Geo Browse ──────────────────────────────────────────────

const REGIONS = [
    'eu-central-1', 'us-east-1', 'us-west-2', 'ap-southeast-1',
    'ap-northeast-1', 'sa-east-1', 'af-south-1', 'me-south-1', 'ap-southeast-2',
];

export function geo_browse() {
    const region = REGIONS[Math.floor(Math.random() * REGIONS.length)];
    const headers = { 'X-Client-Region': region };

    group(`Geo [${region}]`, () => {
        const s1 = Date.now();
        const shop = http.get(`${BASE_URL}/api/shop/featured`, { headers });
        geoLatency.add(Date.now() - s1, { region });
        check(shop, { 'geo shop': (r) => r.status === 200 });
        apiCalls.add(1); sleep(0.5);

        const s2 = Date.now();
        const analytics = http.get(`${BASE_URL}/api/analytics/overview`, { headers });
        geoLatency.add(Date.now() - s2, { region });
        apiCalls.add(1); sleep(0.5);

        const s3 = Date.now();
        const shipping = http.get(`${BASE_URL}/api/shipping/by-region?region=${region}`, { headers });
        geoLatency.add(Date.now() - s3, { region });
        apiCalls.add(1); sleep(0.5);

        http.post(`${BASE_URL}/api/analytics/track`,
            JSON.stringify({ page: '/shop', visitor_region: region, load_time_ms: Date.now() - s1 }),
            { headers: { ...headers, 'Content-Type': 'application/json' } });
        apiCalls.add(1);
    });
}
