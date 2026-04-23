/**
 * IDCS OIDC + PKCE end-to-end spec.
 *
 * Drives a full Authorization Code + PKCE round-trip against a real
 * IDCS identity domain. Uses test user credentials provisioned in the
 * IDCS "OCTO APM Demo — Test" confidential application.
 *
 * Provisioning requirements (one-time per tenancy):
 *
 *   1. In IDCS → Applications → Add Application → Confidential Application
 *   2. Client type: Confidential. Allowed grants: Authorization Code, Refresh Token.
 *   3. Redirect URI: https://shop.${DNS_DOMAIN}/api/auth/sso/callback
 *   4. Post-logout redirect URI: https://shop.${DNS_DOMAIN}/login
 *   5. Scopes: openid, profile, email
 *   6. Create a test user (OCTO_E2E_TEST_USER_EMAIL / OCTO_E2E_TEST_USER_PASSWORD)
 *      and assign it to the app.
 *
 * Skipped in CI when the SSO_E2E_ENABLED env var is not set — OIDC
 * flows are flakey without a live IDCS, so the spec opts in explicitly.
 */

import { expect, test } from '@playwright/test';

const SSO_ENABLED = process.env.SSO_E2E_ENABLED === '1';
const SHOP_BASE = process.env.SHOP_BASE_URL || 'https://shop.cyber-sec.ro';
const TEST_EMAIL = process.env.OCTO_E2E_TEST_USER_EMAIL || '';
const TEST_PASSWORD = process.env.OCTO_E2E_TEST_USER_PASSWORD || '';

test.describe('IDCS OIDC + PKCE SSO', () => {
  test.skip(!SSO_ENABLED, 'set SSO_E2E_ENABLED=1 to run IDCS E2E');
  test.skip(!TEST_EMAIL || !TEST_PASSWORD, 'set OCTO_E2E_TEST_USER_EMAIL + OCTO_E2E_TEST_USER_PASSWORD');

  test('completes authorization-code round-trip and establishes a session', async ({ page, context }) => {
    // ── 1. Start at an authenticated route → app redirects to /login
    await page.goto(`${SHOP_BASE}/admin`, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/login/);

    // ── 2. Click the "Sign in with OCI Identity" SSO button
    const ssoButton = page.locator('[data-testid="sso-login"]');
    await expect(ssoButton).toBeVisible({ timeout: 5_000 });
    await ssoButton.click();

    // ── 3. App redirects to IDCS with: response_type=code, code_challenge,
    //       state, scope=openid profile email. Assert the URL shape.
    await page.waitForURL(/\.identity\.oraclecloud\.com\/ui\/v1\/signin/, { timeout: 10_000 });
    const authorizeUrl = new URL(page.url());
    expect(authorizeUrl.searchParams.get('response_type')).toBe('code');
    expect(authorizeUrl.searchParams.get('code_challenge_method')).toBe('S256');
    expect(authorizeUrl.searchParams.get('code_challenge')).toBeTruthy();
    expect(authorizeUrl.searchParams.get('state')).toBeTruthy();
    expect(authorizeUrl.searchParams.get('scope')).toContain('openid');

    // ── 4. Type credentials on the IDCS sign-in page
    await page.fill('input[name="userName"]', TEST_EMAIL);
    await page.click('[data-id="btn-signin-next"], button[type="submit"]');
    await page.fill('input[name="password"]', TEST_PASSWORD);
    await page.click('[data-id="btn-signin"], button[type="submit"]');

    // ── 5. IDCS redirects back to the callback; app exchanges code for tokens
    await page.waitForURL(`${SHOP_BASE}/**`, { timeout: 20_000 });

    // ── 6. Session cookie set + /api/auth/whoami returns 200 with our email
    const whoami = await page.request.get(`${SHOP_BASE}/api/auth/whoami`);
    expect(whoami.status()).toBe(200);
    const whoamiBody = await whoami.json();
    expect(whoamiBody.authenticated).toBe(true);
    expect(String(whoamiBody.email || '').toLowerCase()).toBe(TEST_EMAIL.toLowerCase());

    // ── 7. Admin route now accessible
    await page.goto(`${SHOP_BASE}/admin`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-testid="admin-heading"]')).toBeVisible({ timeout: 5_000 });

    // ── 8. Logout clears session + redirects to post-logout URL
    await page.click('[data-testid="logout"]');
    await page.waitForURL(/\/login/, { timeout: 10_000 });
    const whoamiAfter = await page.request.get(`${SHOP_BASE}/api/auth/whoami`);
    // 401 (or 200 with authenticated=false) depending on app policy
    if (whoamiAfter.status() === 200) {
      const body = await whoamiAfter.json();
      expect(body.authenticated).toBe(false);
    } else {
      expect(whoamiAfter.status()).toBe(401);
    }
  });

  test('rejects callback with a mismatched state parameter', async ({ page }) => {
    // Drive the callback directly with a forged state — app must refuse.
    const badCallback = `${SHOP_BASE}/api/auth/sso/callback?code=forged&state=attacker-controlled`;
    const resp = await page.request.get(badCallback, { maxRedirects: 0 });
    expect([400, 401, 403]).toContain(resp.status());
  });

  test('rejects callback with no code', async ({ page }) => {
    const resp = await page.request.get(`${SHOP_BASE}/api/auth/sso/callback`, { maxRedirects: 0 });
    expect([400, 401, 403]).toContain(resp.status());
  });

  test('JWKS endpoint is fetched and id_token signature is validated', async ({ page }) => {
    // Indirect assertion: /api/auth/sso/callback with a valid code but a
    // tampered id_token must fail. Direct assertion requires synthesizing
    // a forged token, which is out of scope here; we rely on PyJWT's
    // tamper-detection in integration tests in the shop/ package.
    test.skip(true, 'covered by shop/tests/test_sso_pkce.py unit coverage');
  });
});
