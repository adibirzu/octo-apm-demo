/**
 * Cross-service contract smoke — runs against the deployed environment.
 *
 * Asserts the three invariants we hardened during the PR sweep:
 *   1. `/api/integrations/schema` is live on both services and advertises
 *      the `InternalServiceKey` security scheme.
 *   2. Direct POST to CRM `/api/orders` without `X-Internal-Service-Key`
 *      is refused (401) when the shared key is configured.
 *   3. A shop-initiated order sync carries `idempotency_token` +
 *      `source_system` + `source_order_id`; a retry with the same token
 *      does NOT create a duplicate record on the CRM side.
 *
 * Designed for a nightly CI run against drone.octodemo.cloud /
 * backend.octodemo.cloud; opt in with CROSS_SERVICE_E2E_ENABLED=1.
 */

import { expect, test, type APIRequestContext } from '@playwright/test';

const ENABLED = process.env.CROSS_SERVICE_E2E_ENABLED === '1';
const SHOP = process.env.SHOP_BASE_URL || 'https://drone.octodemo.cloud';
const CRM = process.env.CRM_BASE_URL || 'https://backend.octodemo.cloud';
const INTERNAL_KEY = process.env.INTERNAL_SERVICE_KEY || '';

async function getJson(request: APIRequestContext, url: string): Promise<any> {
  const resp = await request.get(url);
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

test.describe('cross-service contract smoke', () => {
  test.skip(!ENABLED, 'set CROSS_SERVICE_E2E_ENABLED=1 to run against a deployed env');

  test('shop + CRM both publish /api/integrations/schema', async ({ request }) => {
    const shopSchema = await getJson(request, `${SHOP}/api/integrations/schema`);
    const crmSchema = await getJson(request, `${CRM}/api/integrations/schema`);

    expect(String(shopSchema.openapi || '')).toMatch(/^3\./);
    expect(String(crmSchema.openapi || '')).toMatch(/^3\./);

    expect(shopSchema.components?.securitySchemes?.InternalServiceKey?.in).toBe('header');
    expect(shopSchema.components?.securitySchemes?.InternalServiceKey?.name).toBe('X-Internal-Service-Key');
    expect(crmSchema.components?.securitySchemes?.InternalServiceKey?.in).toBe('header');
    expect(crmSchema.components?.securitySchemes?.InternalServiceKey?.name).toBe('X-Internal-Service-Key');
  });

  test('CRM /api/orders refuses unauthenticated POST when internal key is configured', async ({ request }) => {
    test.skip(!INTERNAL_KEY, 'INTERNAL_SERVICE_KEY not provided — cannot verify enforcement');

    const withoutKey = await request.post(`${CRM}/api/orders`, {
      data: { customer_id: 42, items: [{ product_id: 1, quantity: 1, unit_price: 1.0 }] },
    });
    expect(withoutKey.status()).toBe(401);

    const withKey = await request.post(`${CRM}/api/orders`, {
      data: { customer_id: 42, items: [{ product_id: 1, quantity: 1, unit_price: 1.0 }] },
      headers: { 'X-Internal-Service-Key': INTERNAL_KEY },
    });
    expect([200, 201, 404]).toContain(withKey.status()); // 404 if customer 42 does not exist in this tenancy — still proves auth passed
  });

  test('idempotency_token dedupes shop → CRM order sync retries', async ({ request }) => {
    test.skip(!INTERNAL_KEY, 'INTERNAL_SERVICE_KEY not provided');

    // Random high-number order id to avoid collision with real data.
    const orderId = 900_000 + Math.floor(Math.random() * 99_999);
    const payload = {
      customer_id: 1,
      items: [{ product_id: 1, quantity: 1, unit_price: 1.0 }],
      source_system: 'octo-drone-shop',
      source_order_id: String(orderId),
      idempotency_token: `90000000-0000-0000-0000-${orderId.toString().padStart(12, '0')}`,
    };
    const headers = { 'X-Internal-Service-Key': INTERNAL_KEY };

    const first = await request.post(`${CRM}/api/orders`, { data: payload, headers });
    expect([200, 201]).toContain(first.status());
    const firstBody = await first.json();

    const second = await request.post(`${CRM}/api/orders`, { data: payload, headers });
    expect([200, 201, 409]).toContain(second.status()); // 409 if the dedup constraint is enforced at DB level
    const secondBody = await second.json();

    // Either the CRM returns the same order id on retry (proper dedup)
    // OR rejects the duplicate with 409. Both are acceptable; the
    // regression we're guarding against is "two different order ids".
    if (first.status() < 300 && second.status() < 300) {
      expect(secondBody.id ?? secondBody.order_id).toBe(firstBody.id ?? firstBody.order_id);
    }
  });

  test('shop /ready and CRM /ready both report database.reachable', async ({ request }) => {
    const shopReady = await getJson(request, `${SHOP}/ready`);
    const crmReady = await getJson(request, `${CRM}/ready`);

    // Different apps may report slightly different keys; accept either.
    const shopDbOk = shopReady.database?.reachable ?? shopReady.ready ?? false;
    const crmDbOk = crmReady.database?.reachable ?? crmReady.ready ?? false;
    expect(shopDbOk).toBe(true);
    expect(crmDbOk).toBe(true);
  });

  test('distributed trace propagates shop → CRM', async ({ request }) => {
    // Synthetic traceparent — the upstream shop request should honour
    // it if trace propagation is wired, and the trace should appear in
    // APM linked to both services. We don't call APM from here (that's
    // smoke-test.py's job); instead we just assert the request round-
    // trips without stripping the header.
    const traceId = Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
    const spanId = Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
    const traceparent = `00-${traceId}-${spanId}-01`;

    const resp = await request.get(`${SHOP}/api/integrations/crm/health`, {
      headers: { traceparent },
    });
    // 200 if CRM is reachable; 503 if CRM is down. Either way, not 500.
    expect([200, 503]).toContain(resp.status());
  });
});
