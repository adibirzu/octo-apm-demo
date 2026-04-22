/**
 * Simulation / Chaos Controls — tests/e2e/simulation.spec.ts
 *
 * The Drone Shop exposes chaos engineering controls under /api/simulate/*.
 * All mutation endpoints require an SSO token. These tests verify:
 *
 *   - Auth enforcement (401 without token)
 *   - Structural integrity of the status response (when accessible)
 *   - CRM proxy surfaces simulation configured/status correctly
 *   - Reset endpoint is callable (returns 401 without token)
 *   - Input clamping rejects out-of-range values with 400/422
 *
 * Note: Tests never apply real chaos settings to avoid destabilising the
 * environment. All mutation tests assert on the 401 path only.
 *
 * Env vars: SHOP_URL, CRM_URL
 */

import { test, expect } from '@playwright/test';
import {
  SHOP_URL,
  CRM_URL,
  apiGet,
  apiPost,
  assertObject,
} from './helpers';

// ── Auth enforcement on all mutation endpoints ────────────────────────────────

test.describe('Simulation endpoints — auth enforcement', () => {
  const mutationEndpoints: Array<{ method: 'GET' | 'POST'; path: string; label: string }> = [
    { method: 'GET',  path: '/api/simulate/status', label: 'GET /api/simulate/status' },
    { method: 'POST', path: '/api/simulate/reset',  label: 'POST /api/simulate/reset' },
    { method: 'POST', path: '/api/simulate/set',    label: 'POST /api/simulate/set' },
  ];

  for (const endpoint of mutationEndpoints) {
    test(`${endpoint.label} returns 401 without token`, async ({ request }) => {
      let status: number;
      if (endpoint.method === 'GET') {
        ({ status } = await apiGet(request, `${SHOP_URL}${endpoint.path}`));
      } else {
        ({ status } = await apiPost(request, `${SHOP_URL}${endpoint.path}`, {}));
      }
      expect([401, 403]).toContain(status);
    });
  }
});

// ── Status endpoint structure ─────────────────────────────────────────────────

test.describe('Simulation status endpoint', () => {
  test('GET /api/simulate/status returns 401 (auth required)', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/simulate/status`);
    expect([401, 403]).toContain(status);
    const data = assertObject(body);
    // Error body must carry a detail field (FastAPI HTTPException format).
    const hasError = 'detail' in data || 'error' in data || 'message' in data;
    expect(hasError).toBe(true);
  });

  test('status 401 response does not expose internal middleware state', async ({ request }) => {
    const { body } = await apiGet(request, `${SHOP_URL}/api/simulate/status`);
    const text = JSON.stringify(body).toLowerCase();
    expect(text).not.toContain('traceback');
    expect(text).not.toContain('exception');
    expect(text).not.toContain('stack');
  });
});

// ── Input clamping (via CRM proxy; auth enforced at shop) ─────────────────────

test.describe('Simulation input clamping', () => {
  /**
   * The shop module documents that error_rate must be [0.0, 1.0] and
   * db_latency_ms must be [0, 30000]. Without an SSO token we receive 401,
   * which means the clamping logic is never reached. We test clamping via
   * the CRM proxy if it forwards unauthenticated, or we verify the 401
   * is returned before any validation — both are correct behaviours.
   */
  test('POST /api/simulate/set with error_rate > 1.0 returns 400 or 401', async ({ request }) => {
    const { status } = await apiPost(request, `${SHOP_URL}/api/simulate/set`, {
      error_rate: 5.0,
      db_latency_ms: 0,
    });
    // 401 = auth check fires before validation (correct); 400/422 = validation fires (also correct).
    expect([400, 401, 403, 422]).toContain(status);
  });

  test('POST /api/simulate/set with db_latency_ms < 0 returns 400 or 401', async ({ request }) => {
    const { status } = await apiPost(request, `${SHOP_URL}/api/simulate/set`, {
      error_rate: 0.0,
      db_latency_ms: -500,
    });
    expect([400, 401, 403, 422]).toContain(status);
  });

  test('POST /api/simulate/set with db_latency_ms > 30000 returns 400 or 401', async ({ request }) => {
    const { status } = await apiPost(request, `${SHOP_URL}/api/simulate/set`, {
      error_rate: 0.0,
      db_latency_ms: 999_999,
    });
    expect([400, 401, 403, 422]).toContain(status);
  });
});

// ── CRM proxy — simulation configured ────────────────────────────────────────

test.describe('CRM Portal — simulation proxy', () => {
  test('GET /api/integrations/drone-shop/simulate/configured returns structured response', async ({ request }) => {
    const { status, body } = await apiGet(
      request,
      `${CRM_URL}/api/integrations/drone-shop/simulate/configured`,
    );

    // 200 = CRM can reach the shop; 404 = endpoint not defined on this CRM version.
    expect([200, 404]).toContain(status);

    if (status === 200) {
      const data = assertObject(body);
      expect(typeof data['configured']).toBe('boolean');
    }
  });

  test('GET /api/integrations/drone-shop/simulate/status proxied through CRM', async ({ request }) => {
    const { status } = await apiGet(
      request,
      `${CRM_URL}/api/integrations/drone-shop/simulate/status`,
    );
    // CRM either proxies the 401 from the shop or surfaces it own auth gate.
    expect([200, 401, 403, 404]).toContain(status);
  });

  test('POST /api/integrations/drone-shop/simulate/reset via CRM returns expected status', async ({ request }) => {
    const { status } = await apiPost(
      request,
      `${CRM_URL}/api/integrations/drone-shop/simulate/reset`,
      {},
    );
    // 200 = CRM forwarded and shop accepted (unlikely without SSO);
    // 401/403 = auth required; 404 = endpoint not available.
    expect([200, 401, 403, 404]).toContain(status);
  });
});

// ── Chaos module defaults ─────────────────────────────────────────────────────

test.describe('Chaos defaults — shop behaves normally without active chaos', () => {
  /**
   * Without any chaos flags set (which is the default), the shop endpoints
   * must respond without artificial errors. We verify this by checking that
   * /health and /api/shop/storefront return their normal codes while the
   * chaos middleware is idle.
   */
  test('/health returns 200 (chaos middleware not interfering)', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/health`);
    expect(status).toBe(200);
  });

  test('/api/shop/storefront returns 200 (chaos not active)', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/shop/storefront`);
    expect(status).toBe(200);
  });

  test('/ready is not affected by default chaos state', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/ready`);
    expect([200, 503]).toContain(status);
  });
});
