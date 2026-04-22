/**
 * Availability Testing — tests/e2e/availability.spec.ts
 *
 * Verifies the shop behaves correctly under concurrent load and handles
 * malformed requests with proper error JSON (never a raw crash):
 *
 *   - 10 parallel /health requests all return 200
 *   - 5 parallel /ready requests all respond (200 or 503)
 *   - Malformed POST payloads return structured 4xx errors
 *   - Missing required fields return 422 (FastAPI validation)
 *   - Unknown endpoints return 404 (not 500)
 *   - Extremely long inputs are rejected safely
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

// ── Concurrent health checks ──────────────────────────────────────────────────

test.describe('Concurrent health checks — Drone Shop', () => {
  test('10 parallel /health requests all return 200', async ({ request }) => {
    const requests = Array.from({ length: 10 }, () =>
      apiGet(request, `${SHOP_URL}/health`),
    );
    const results = await Promise.all(requests);

    for (const { status } of results) {
      expect(status).toBe(200);
    }
  });

  test('5 parallel /ready requests all respond without crashing', async ({ request }) => {
    const requests = Array.from({ length: 5 }, () =>
      apiGet(request, `${SHOP_URL}/ready`),
    );
    const results = await Promise.all(requests);

    for (const { status } of results) {
      // 200 = ready; 503 = DB offline — both are valid non-crash responses.
      expect([200, 503]).toContain(status);
    }
  });

  test('5 parallel /api/shop/storefront requests all return 200', async ({ request }) => {
    const requests = Array.from({ length: 5 }, () =>
      apiGet(request, `${SHOP_URL}/api/shop/storefront`),
    );
    const results = await Promise.all(requests);

    for (const { status } of results) {
      expect(status).toBe(200);
    }
  });
});

// ── Concurrent CRM checks ─────────────────────────────────────────────────────

test.describe('Concurrent health checks — CRM Portal', () => {
  test('5 parallel /health requests to CRM all return 200', async ({ request }) => {
    const requests = Array.from({ length: 5 }, () =>
      apiGet(request, `${CRM_URL}/health`),
    );
    const results = await Promise.all(requests);

    for (const { status } of results) {
      expect(status).toBe(200);
    }
  });
});

// ── Mixed concurrent requests ─────────────────────────────────────────────────

test.describe('Mixed concurrent requests across both apps', () => {
  test('shop + CRM health checks in parallel all succeed', async ({ request }) => {
    const results = await Promise.all([
      ...Array.from({ length: 5 }, () => apiGet(request, `${SHOP_URL}/health`)),
      ...Array.from({ length: 5 }, () => apiGet(request, `${CRM_URL}/health`)),
    ]);

    for (const { status } of results) {
      expect(status).toBe(200);
    }
  });
});

// ── Malformed request handling ────────────────────────────────────────────────

test.describe('Malformed requests return structured error JSON', () => {
  test('POST /api/cart/add with empty body returns 4xx with JSON', async ({ request }) => {
    const { status, body } = await apiPost(request, `${SHOP_URL}/api/cart/add`, {});

    // FastAPI returns 422 for missing required fields; 400 for semantic errors.
    expect(status).toBeGreaterThanOrEqual(400);
    expect(status).toBeLessThan(500);

    // Body must be JSON (not HTML error page or raw traceback).
    expect(typeof body).toBe('object');
    expect(body).not.toBeNull();
  });

  test('POST /api/cart/add with null product_id returns 4xx', async ({ request }) => {
    const { status, body } = await apiPost(request, `${SHOP_URL}/api/cart/add`, {
      product_id: null,
      quantity: 1,
      session_id: 'malformed-test',
    });

    expect(status).toBeGreaterThanOrEqual(400);
    expect(status).toBeLessThan(500);
    expect(typeof body).toBe('object');
  });

  test('POST /api/cart/add with negative quantity returns 4xx or 200 (sanitized)', async ({ request }) => {
    // Negative quantity is a business logic edge case — may be rejected (400)
    // or clamped to zero (200). Either is acceptable; never a 5xx crash.
    const { status } = await apiPost(request, `${SHOP_URL}/api/cart/add`, {
      product_id: 1,
      quantity: -1,
      session_id: 'negative-qty-test',
    });

    expect(status).toBeLessThan(500);
  });

  test('POST /api/shop/checkout with missing customer_email returns 4xx', async ({ request }) => {
    const { status, body } = await apiPost(request, `${SHOP_URL}/api/shop/checkout`, {
      session_id: 'missing-email-test',
      // customer_email intentionally omitted
    });

    expect(status).toBeGreaterThanOrEqual(400);
    expect(status).toBeLessThan(500);
    expect(typeof body).toBe('object');
  });

  test('POST with non-JSON Content-Type to JSON endpoint returns 4xx', async ({ request }) => {
    const response = await request.post(`${SHOP_URL}/api/cart/add`, {
      headers: { 'Content-Type': 'text/plain' },
      data: 'not json at all',
    });

    expect(response.status()).toBeGreaterThanOrEqual(400);
    expect(response.status()).toBeLessThan(500);
  });
});

// ── Unknown endpoint handling ─────────────────────────────────────────────────

test.describe('Unknown endpoints return 404 not 500', () => {
  test('GET /api/nonexistent returns 404', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/nonexistent`);
    expect(status).toBe(404);
  });

  test('GET /api/integrations/nonexistent returns 404 or 405', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/integrations/nonexistent`);
    expect([404, 405]).toContain(status);
  });

  test('POST to a GET-only endpoint returns 405 not 500', async ({ request }) => {
    const { status } = await apiPost(request, `${SHOP_URL}/health`, {});
    // FastAPI returns 405 Method Not Allowed for wrong HTTP method.
    expect([405, 404]).toContain(status);
  });
});

// ── Extremely long inputs ─────────────────────────────────────────────────────

test.describe('Extremely long inputs are rejected safely', () => {
  test('POST /api/cart/add with 10000-char session_id does not crash', async ({ request }) => {
    const longId = 'a'.repeat(10_000);
    const { status } = await apiPost(request, `${SHOP_URL}/api/cart/add`, {
      product_id: 1,
      quantity: 1,
      session_id: longId,
    });

    // Should return a client error or succeed (if the DB accepts it), never 500.
    expect(status).toBeLessThan(500);
  });

  test('GET /api/orders with 5000-char customer_id query param does not crash', async ({ request }) => {
    const longId = 'x'.repeat(5_000);
    const { status } = await apiGet(
      request,
      `${SHOP_URL}/api/orders?customer_id=${longId}`,
    );
    expect(status).toBeLessThan(500);
  });
});

// ── Response time sanity ──────────────────────────────────────────────────────

test.describe('Response time sanity checks', () => {
  test('/health responds within 5 seconds', async ({ request }) => {
    const start = Date.now();
    const { status } = await apiGet(request, `${SHOP_URL}/health`);
    const elapsed = Date.now() - start;

    expect(status).toBe(200);
    // Even under load, health must return within 5s.
    expect(elapsed).toBeLessThan(5_000);
  });

  test('/api/shop/storefront responds within 15 seconds', async ({ request }) => {
    const start = Date.now();
    const { status } = await apiGet(request, `${SHOP_URL}/api/shop/storefront`);
    const elapsed = Date.now() - start;

    expect(status).toBe(200);
    expect(elapsed).toBeLessThan(15_000);
  });
});
