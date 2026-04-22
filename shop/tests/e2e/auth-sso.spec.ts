/**
 * Authentication & SSO — tests/e2e/auth-sso.spec.ts
 *
 * Verifies SSO configuration status and auth-gated endpoint behaviour:
 *
 *   - /api/auth/sso/status  — SSO status without token
 *   - /api/auth/sso/login   — Login redirect or payload
 *   - /api/simulate/status  — Requires SSO token (returns 401 without)
 *   - /api/simulate/reset   — Requires SSO token (returns 401 without)
 *   - /login page           — SSO button visible in HTML
 *   - Profile endpoint      — Returns 401 without a Bearer token
 *
 * Env vars: SHOP_URL
 */

import { test, expect, Page } from '@playwright/test';
import {
  SHOP_URL,
  apiGet,
  apiPost,
  assertObject,
} from './helpers';

function expectNoPrivateClusterLeak(body: unknown): void {
  const serialized = JSON.stringify(body).toLowerCase();
  expect(serialized).not.toContain('.svc.cluster.local');
  expect(serialized).not.toContain('.cluster.local');
}

// ── SSO Status ────────────────────────────────────────────────────────────────

test.describe('SSO Status', () => {
  test('GET /api/auth/sso/status returns 200 with configured field', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/auth/sso/status`);

    expect(status).toBe(200);
    const data = assertObject(body);

    // Must expose whether SSO / IDCS is configured.
    const hasConfigured =
      'configured' in data ||
      'sso_configured' in data ||
      'idcs_configured' in data;
    expect(hasConfigured).toBe(true);
  });

  test('SSO status response includes provider or endpoint info when configured', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/auth/sso/status`);
    expect(status).toBe(200);
    const data = assertObject(body);

    const isConfigured =
      data['configured'] === true ||
      data['sso_configured'] === true ||
      data['idcs_configured'] === true;

    if (isConfigured) {
      // When SSO is configured, the status should include at minimum an
      // endpoint URL or provider name.
      const hasProviderInfo =
        'provider' in data ||
        'idcs_url' in data ||
        'login_url' in data ||
        'auth_url' in data ||
        'client_id' in data;
      expect(hasProviderInfo).toBe(true);
    }
  });
});

// ── SSO Login ─────────────────────────────────────────────────────────────────

test.describe('SSO Login', () => {
  test('GET /api/auth/sso/login returns redirect URL or 404 when not configured', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/auth/sso/login`);

    // 200 = login URL returned; 302 = redirect to IdP;
    // 404 = endpoint exists but SSO not configured; 422 = missing required params.
    expect([200, 302, 404, 422]).toContain(status);

    if (status === 200) {
      const data = assertObject(body);
      const hasLoginUrl =
        'login_url' in data || 'redirect_url' in data || 'url' in data || 'auth_url' in data;
      expect(hasLoginUrl).toBe(true);
    }
  });
});

// ── Auth-gated simulation endpoints ──────────────────────────────────────────

test.describe('Simulation endpoints require SSO authentication', () => {
  test('GET /api/simulate/status returns 401 without Bearer token', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/simulate/status`);
    // Simulation endpoints are protected by require_sso_user.
    // Without a valid token the response must be 401 or 403.
    expect([401, 403]).toContain(status);
  });

  test('POST /api/simulate/reset returns 401 without Bearer token', async ({ request }) => {
    const { status } = await apiPost(
      request,
      `${SHOP_URL}/api/simulate/reset`,
      {},
    );
    expect([401, 403]).toContain(status);
  });

  test('POST /api/simulate/set returns 401 without Bearer token', async ({ request }) => {
    const { status } = await apiPost(
      request,
      `${SHOP_URL}/api/simulate/set`,
      { error_rate: 0.1, db_latency_ms: 0 },
    );
    expect([401, 403]).toContain(status);
  });

  test('401 response body contains error message (not a stack trace)', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/simulate/status`);
    if (status === 401 || status === 403) {
      const text = JSON.stringify(body).toLowerCase();
      // Must not expose internal implementation details.
      expect(text).not.toContain('traceback');
      // Must include some error indication.
      const hasErrorField =
        text.includes('detail') ||
        text.includes('error') ||
        text.includes('unauthorized') ||
        text.includes('forbidden');
      expect(hasErrorField).toBe(true);
    }
  });
});

// ── Profile / auth endpoints require token ────────────────────────────────────

test.describe('Auth profile endpoint', () => {
  test('GET /api/auth/profile returns 401 without Bearer token', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/auth/profile`);
    expect([401, 403, 404]).toContain(status);
  });

  test('GET /api/auth/profile with malformed token returns 401', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/auth/profile`, {
      Authorization: 'Bearer this-is-not-a-real-token',
    });
    expect([401, 403]).toContain(status);
  });

  test('GET /api/orders returns 401 without Bearer token', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/orders`);
    expect([401, 403]).toContain(status);
  });

  test('GET /api/orders/1 returns 401 without Bearer token', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/orders/1`);
    expect([401, 403]).toContain(status);
  });
});

// ── Login page UI ─────────────────────────────────────────────────────────────

test.describe('Login page UI', () => {
  test('GET /login renders HTML page', async ({ page }: { page: Page }) => {
    const response = await page.goto(`${SHOP_URL}/login`);
    expect(response?.status()).toBe(200);
    const contentType = response?.headers()['content-type'] ?? '';
    expect(contentType).toContain('text/html');
  });

  test('login page body is non-empty', async ({ page }: { page: Page }) => {
    await page.goto(`${SHOP_URL}/login`);
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(0);
  });

  test('login page contains SSO-related text or button when IDCS configured', async ({ request, page }) => {
    // Check SSO status first.
    const { body: statusBody } = await apiGet(request, `${SHOP_URL}/api/auth/sso/status`);
    const statusData = assertObject(statusBody);
    const ssoConfigured =
      statusData['configured'] === true ||
      statusData['sso_configured'] === true ||
      statusData['idcs_configured'] === true;

    if (!ssoConfigured) {
      // SSO not configured — skip the button check.
      test.skip();
      return;
    }

    await page.goto(`${SHOP_URL}/login`);

    // Look for any element that indicates SSO sign-in capability.
    const ssoButton = page.locator(
      'button:has-text("SSO"), a:has-text("SSO"), button:has-text("Sign in with"), a:has-text("Sign in with"), [data-testid="sso-login"]',
    );
    const count = await ssoButton.count();
    expect(count).toBeGreaterThan(0);
  });
});

// ── Token validation ──────────────────────────────────────────────────────────

test.describe('Token validation edge cases', () => {
  test('empty Authorization header is rejected on protected endpoints', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/simulate/status`, {
      Authorization: '',
    });
    expect([401, 403]).toContain(status);
  });

  test('Auth header with wrong scheme is rejected', async ({ request }) => {
    const { status } = await apiGet(request, `${SHOP_URL}/api/simulate/status`, {
      Authorization: 'Basic dXNlcjpwYXNz',
    });
    expect([401, 403]).toContain(status);
  });
});

// ── Public payloads must not leak private service DNS ────────────────────────

test.describe('Public responses redact private service hosts', () => {
  test('GET /api/integrations/status does not expose cluster-local CRM hostnames', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/integrations/status`);
    expect(status).toBe(200);
    expectNoPrivateClusterLeak(body);
  });

  test('GET /api/integrations/crm/health does not expose cluster-local CRM hostnames', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/integrations/crm/health`);
    expect([200, 503]).toContain(status);
    expectNoPrivateClusterLeak(body);
  });

  test('GET /api/observability/360 does not expose cluster-local integration URLs', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/api/observability/360`);
    expect(status).toBe(200);
    expectNoPrivateClusterLeak(body);
  });
});
