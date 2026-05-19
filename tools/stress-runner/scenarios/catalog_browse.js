/* eslint-disable */
// ----------------------------------------------------------------------------
// catalog_browse — read-only catalog walk for the OKE stress demo.
//
// Hits GET /api/products and GET /api/products/{id} only. Lower-write
// scenario useful for isolating cache/DB read paths from POST-heavy load.
// Headers + env contract identical to checkout_journey.js.
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
    http_req_duration: ['p(95)<8000'],
  },
  tags: {
    scenario: 'catalog_browse',
    run_id: RUN_ID,
  },
};

const HEADERS = {
  'X-Octo-Stress-Target': 'oke',
  'X-Run-Id': RUN_ID,
  'User-Agent': 'k6/octo-stress-runner',
};

const SAMPLE_PRODUCT_IDS = ['drone-alpha', 'drone-bravo', 'drone-charlie'];

export default function () {
  const params = {
    headers: HEADERS,
    tags: { workflow: 'browse', scenario: 'catalog_browse', run_id: RUN_ID },
  };

  const list = http.get(`${TARGET}/api/products?limit=24`, params);
  check(list, { 'list 2xx': (r) => r.status < 400 });

  const pid = SAMPLE_PRODUCT_IDS[__ITER % SAMPLE_PRODUCT_IDS.length];
  const detail = http.get(`${TARGET}/api/products/${pid}`, params);
  check(detail, { 'detail 2xx or 404': (r) => r.status < 500 });

  sleep(0.5);
}
