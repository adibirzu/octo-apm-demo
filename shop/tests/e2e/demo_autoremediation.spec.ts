/**
 * End-to-end demo: chaos → alarm → coordinator playbook → cleared.
 *
 * This spec does NOT mutate chaos state on the Shop (which has no write
 * endpoints); it drives the CRM admin API and verifies the Shop observes
 * the scenario via its reader endpoint.
 */
import { test, expect, request } from '@playwright/test';

const SHOP = process.env.SHOP_DOMAIN ?? 'shop.example.cloud';
const CRM = process.env.CRM_DOMAIN ?? 'crm.example.cloud';
const COOKIE = process.env.CRM_SESSION_COOKIE ?? '';

test.describe('Octo Demo — auto-remediation loop', () => {
  test.skip(!COOKIE, 'CRM_SESSION_COOKIE required for this e2e');

  test('chaos apply → shop observes → clear → shop clean', async ({}, testInfo) => {
    const ctx = await request.newContext({
      extraHTTPHeaders: { Cookie: COOKIE },
    });

    // Confirm Shop has no admin chaos write endpoint.
    const shopWrite = await ctx.post(`https://${SHOP}/api/admin/chaos/apply`, {
      data: { scenario_id: 'db-slow-checkout' },
      failOnStatusCode: false,
    });
    expect([403, 404, 405]).toContain(shopWrite.status());

    // Apply on CRM.
    const apply = await ctx.post(`https://${CRM}/api/admin/chaos/apply`, {
      data: {
        scenario_id: 'db-slow-checkout',
        target: 'shop',
        ttl_seconds: 60,
        note: `e2e-${testInfo.title}`,
      },
    });
    expect(apply.ok()).toBeTruthy();

    // Poll Shop until it reports the scenario.
    let observed = false;
    for (let attempt = 0; attempt < 20; attempt++) {
      const state = await ctx.get(`https://${SHOP}/api/chaos/state`);
      const body = await state.json();
      if (body?.active && body?.state?.scenario_id === 'db-slow-checkout') {
        observed = true;
        break;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
    expect(observed, 'Shop did not observe applied chaos state within timeout').toBeTruthy();

    // Clear.
    const clear = await ctx.post(`https://${CRM}/api/admin/chaos/clear`);
    expect(clear.ok()).toBeTruthy();

    // Shop should soon report no active scenario.
    let cleared = false;
    for (let attempt = 0; attempt < 20; attempt++) {
      const state = await ctx.get(`https://${SHOP}/api/chaos/state`);
      const body = await state.json();
      if (!body?.active) {
        cleared = true;
        break;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
    expect(cleared, 'Shop still reports active scenario after clear').toBeTruthy();
  });
});
