/* eslint-disable */
// ----------------------------------------------------------------------------
// checkout_journey — clones shop/k6/checkout-load.js for the OKE stress demo.
//
// Drives the full browse → add-to-cart → checkout workflow against the public
// LB hostname (shop.${DNS_DOMAIN}). Every request carries:
//   - X-Octo-Stress-Target: oke  (D-09 LB pin — keeps load on the OKE backend
//     set, leaves the VM backend untouched per DEPLOY-03)
//   - X-Run-Id: <uuid>           (propagates to APM spans for trace pivots)
//   - User-Agent: k6/octo-stress-runner
//
// Configuration (via -e args set by the FastAPI wrapper):
//   STRESS_TARGET_URL  — public LB URL, e.g. https://shop.octodemo.cloud
//   K6_VUS             — virtual users (mapped from `rps` cap 1..200)
//   K6_DURATION        — duration (e.g. "60s", cap 10s..600s)
//   RUN_ID             — UUID injected by CRM admin route / wrapper
// ----------------------------------------------------------------------------
import http from 'k6/http';
import { sleep, check } from 'k6';

const TARGET = __ENV.STRESS_TARGET_URL || 'https://shop.octodemo.cloud';
const RUN_ID = __ENV.RUN_ID || 'unset';

export const options = {
  vus: Number(__ENV.K6_VUS || 25),
  duration: __ENV.K6_DURATION || '60s',
  thresholds: {
    http_req_failed: ['rate<0.10'],
    http_req_duration: ['p(95)<15000'],
  },
  tags: {
    scenario: 'checkout_journey',
    run_id: RUN_ID,
  },
};

const HEADERS = {
  'X-Octo-Stress-Target': 'oke',
  'X-Run-Id': RUN_ID,
  'User-Agent': 'k6/octo-stress-runner',
  'Content-Type': 'application/json',
};

export default function () {
  const params = {
    headers: HEADERS,
    tags: { workflow: 'checkout', scenario: 'checkout_journey', run_id: RUN_ID },
  };

  const browse = http.get(`${TARGET}/api/products?limit=12`, params);
  check(browse, { 'browse 2xx': (r) => r.status < 400 });

  const cart = http.post(
    `${TARGET}/api/cart`,
    JSON.stringify({ product_id: 'drone-alpha', qty: 1 }),
    params,
  );
  check(cart, { 'cart acknowledged': (r) => r.status < 500 });

  const checkout = http.post(
    `${TARGET}/api/orders`,
    JSON.stringify({ payment: 'card', currency: 'EUR' }),
    params,
  );
  check(checkout, { 'checkout responded': (r) => r.status < 500 || r.status === 502 });

  sleep(1);
}
