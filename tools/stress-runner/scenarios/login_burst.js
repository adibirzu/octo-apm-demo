/* eslint-disable */
// ----------------------------------------------------------------------------
// login_burst — repeated POST /api/auth/login for the OKE stress demo.
//
// Demo test users ONLY — NEVER real PII (T-07-14 mitigation). The burst
// pattern exercises auth + session + rate-limit paths under HPA pressure.
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
    http_req_failed: ['rate<0.30'],
    http_req_duration: ['p(95)<5000'],
  },
  tags: {
    scenario: 'login_burst',
    run_id: RUN_ID,
  },
};

const HEADERS = {
  'X-Octo-Stress-Target': 'oke',
  'X-Run-Id': RUN_ID,
  'User-Agent': 'k6/octo-stress-runner',
  'Content-Type': 'application/json',
};

// Demo test users only — credentials are read from __ENV (set by the
// FastAPI wrapper from a k8s Secret), NEVER hardcoded (T-07-14 mitigation
// + global no-secrets-in-source rule).
const DEMO_USERNAME = __ENV.STRESS_DEMO_USERNAME || 'demo-user';
const DEMO_TOKEN_REF = __ENV.STRESS_DEMO_TOKEN_REF || '';

export default function () {
  const params = {
    headers: HEADERS,
    tags: { workflow: 'login', scenario: 'login_burst', run_id: RUN_ID },
  };

  // Suffix-varied demo identifier so successive iterations exercise the
  // multi-user auth path. The credential value itself comes from the
  // STRESS_DEMO_TOKEN_REF env (k8s Secret injected by the wrapper).
  const variant = `${DEMO_USERNAME}-${(__ITER % 3) + 1}`;
  const payload = { username: variant, token_ref: DEMO_TOKEN_REF };
  const res = http.post(
    `${TARGET}/api/auth/login`,
    JSON.stringify(payload),
    params,
  );
  check(res, {
    'login responded': (r) => r.status < 500 || r.status === 502,
  });

  sleep(0.1);
}
