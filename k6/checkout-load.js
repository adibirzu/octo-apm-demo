/* eslint-disable */
// ----------------------------------------------------------------------------
// Checkout load scenario — drives the `checkout` workflow_id hard enough to
// produce a p95 signal in Log Analytics when chaos is active.
//
// Usage: k6 run -e SHOP_DOMAIN=shop.octodemo.cloud k6/checkout-load.js
// ----------------------------------------------------------------------------
import http from 'k6/http';
import { sleep, check } from 'k6';

const SHOP = __ENV.SHOP_DOMAIN || 'shop.octodemo.cloud';
const BASE = `https://${SHOP}`;

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || '2m',
  thresholds: {
    http_req_failed: ['rate<0.50'],   // allow chaos-induced failures
    http_req_duration: ['p(95)<15000'],
  },
};

export default function () {
  const params = {
    headers: {
      'X-Request-Id': `k6-${__VU}-${__ITER}`,
      'User-Agent': 'k6/octo-demo',
    },
    tags: { workflow: 'checkout' },
  };

  // Browse → add → checkout. We intentionally hit the real surface areas
  // that the workflow_context middleware maps to `browse-catalog`,
  // `add-to-cart`, and `checkout`.
  const browse = http.get(`${BASE}/api/products?limit=12`, params);
  check(browse, { 'browse 2xx': (r) => r.status < 400 });

  const cart = http.post(
    `${BASE}/api/cart`,
    JSON.stringify({ product_id: 'drone-alpha', qty: 1 }),
    { ...params, headers: { ...params.headers, 'Content-Type': 'application/json' } }
  );
  check(cart, { 'cart acknowledged': (r) => r.status < 500 });

  const checkout = http.post(
    `${BASE}/api/orders`,
    JSON.stringify({ payment: 'card', currency: 'EUR' }),
    { ...params, headers: { ...params.headers, 'Content-Type': 'application/json' } }
  );
  check(checkout, { 'checkout responded': (r) => r.status < 500 || r.status === 502 });

  sleep(1);
}
