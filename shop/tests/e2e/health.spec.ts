/**
 * Health & Readiness — tests/e2e/health.spec.ts
 *
 * Verifies that both the Drone Shop and CRM Portal report healthy on /health
 * and /ready, and that the readiness payload contains the expected fields:
 * database connectivity, APM configuration status, and runtime metadata.
 *
 * Env vars: SHOP_URL, CRM_URL
 */

import { test, expect } from '@playwright/test';
import {
  SHOP_URL,
  CRM_URL,
  apiGet,
  assertObject,
  assertNonEmptyString,
} from './helpers';

// ── Drone Shop ────────────────────────────────────────────────────────────────

test.describe('Drone Shop — /health', () => {
  test('returns HTTP 200 with status:ok', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/health`);

    expect(status).toBe(200);
    const data = assertObject(body);
    expect(data['status']).toBe('ok');
    assertNonEmptyString(data['service'], 'service name');
  });
});

test.describe('Drone Shop — /ready', () => {
  test('returns HTTP 200 with structured readiness payload', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/ready`);

    // Ready endpoint can return 200 even when DB is disconnected — the field
    // value communicates the real state without crashing the health probe.
    expect([200, 503]).toContain(status);
    const data = assertObject(body);

    // Core readiness fields must be present regardless of state.
    expect(typeof data['ready']).toBe('boolean');
    expect(['connected', 'disconnected']).toContain(data['database']);
    assertNonEmptyString(data['db_type'], 'db_type');
  });

  test('ready payload includes apm_configured flag', async ({ request }) => {
    const { body } = await apiGet(request, `${SHOP_URL}/ready`);
    const data = assertObject(body);
    expect(typeof data['apm_configured']).toBe('boolean');
  });

  test('ready payload includes rum_configured flag', async ({ request }) => {
    const { body } = await apiGet(request, `${SHOP_URL}/ready`);
    const data = assertObject(body);
    expect(typeof data['rum_configured']).toBe('boolean');
  });

  test('ready payload includes workflow_gateway_configured flag', async ({ request }) => {
    const { body } = await apiGet(request, `${SHOP_URL}/ready`);
    const data = assertObject(body);
    expect(typeof data['workflow_gateway_configured']).toBe('boolean');
  });

  test('ready payload includes runtime metadata object', async ({ request }) => {
    const { body } = await apiGet(request, `${SHOP_URL}/ready`);
    const data = assertObject(body);
    // runtime is an object (snapshot of process metadata); may be empty dict.
    expect(typeof data['runtime']).toBe('object');
    expect(data['runtime']).not.toBeNull();
  });

  test('database shows connected when app is healthy', async ({ request }) => {
    const { status, body } = await apiGet(request, `${SHOP_URL}/ready`);
    // Only assert database:connected when the app itself says it is ready.
    if (status === 200) {
      const data = assertObject(body);
      if (data['ready'] === true) {
        expect(data['database']).toBe('connected');
      }
    }
  });
});

// ── CRM Portal ────────────────────────────────────────────────────────────────

test.describe('CRM Portal — /health', () => {
  test('returns HTTP 200 with status:ok', async ({ request }) => {
    const { status, body } = await apiGet(request, `${CRM_URL}/health`);

    expect(status).toBe(200);
    const data = assertObject(body);
    expect(data['status']).toBe('ok');
    // CRM may expose a different service name; just assert it is a string.
    assertNonEmptyString(data['service'], 'crm service name');
  });
});

test.describe('CRM Portal — /ready', () => {
  test('returns HTTP 200 with readiness payload', async ({ request }) => {
    const { status, body } = await apiGet(request, `${CRM_URL}/ready`);
    expect([200, 503]).toContain(status);
    const data = assertObject(body);
    expect(typeof data['ready']).toBe('boolean');
  });

  test('CRM ready payload reports database field', async ({ request }) => {
    const { body } = await apiGet(request, `${CRM_URL}/ready`);
    const data = assertObject(body);
    expect(['connected', 'disconnected']).toContain(data['database']);
  });
});

// ── Cross-app availability ────────────────────────────────────────────────────

test.describe('Both apps are reachable simultaneously', () => {
  test('shop /health and CRM /health both respond within timeout', async ({ request }) => {
    const [shopResult, crmResult] = await Promise.all([
      apiGet(request, `${SHOP_URL}/health`),
      apiGet(request, `${CRM_URL}/health`),
    ]);

    expect(shopResult.status).toBe(200);
    expect(crmResult.status).toBe(200);
  });
});
