/**
 * Playwright configuration for OCTO Drone Shop E2E test suite.
 *
 * Target environments:
 *   - Local docker-compose:  SHOP_URL=http://localhost:8080  CRM_URL=http://localhost:8081
 *   - OKE live deployment:   SHOP_URL=https://shop.<DNS_DOMAIN>  CRM_URL=https://crm.<DNS_DOMAIN>
 *
 * Key env vars:
 *   SHOP_URL           - Drone Shop base URL (default: http://localhost:8080)
 *   CRM_URL            - Enterprise CRM Portal base URL (default: http://localhost:8081)
 *   COORDINATOR_URL    - OCI Coordinator internal URL (optional, skips coordinator tests if absent)
 *   DNS_DOMAIN         - DNS domain for live OKE (optional)
 *   CI                 - Set by CI systems; activates forbidOnly, single retry, and reporter changes
 */

import { defineConfig, devices } from '@playwright/test';

const shopUrl = process.env.SHOP_URL ?? 'http://localhost:8080';
const crmUrl  = process.env.CRM_URL  ?? 'http://localhost:8081';

// Longer timeouts for live OKE deployments that cross real network boundaries.
const isLive   = shopUrl.startsWith('https://');
const timeout  = isLive ? 45_000 : 20_000;
const navTimeout = isLive ? 30_000 : 15_000;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 4,
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['junit', { outputFile: 'test-results/junit.xml' }],
    ['list'],
  ],
  outputDir: 'test-results',

  use: {
    baseURL: shopUrl,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: timeout,
    navigationTimeout: navTimeout,

    // Propagate URLs to tests via storageState isn't practical here;
    // we pass them through process.env which tests read directly.
    extraHTTPHeaders: {
      'X-Test-Suite': 'octo-drone-shop-e2e',
    },
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // API-only specs run in a lightweight project without a real browser.
    {
      name: 'api',
      testMatch: [
        '**/health.spec.ts',
        '**/cross-service.spec.ts',
        '**/melts.spec.ts',
        '**/auth-sso.spec.ts',
        '**/simulation.spec.ts',
        '**/availability.spec.ts',
        '**/k6-integration.spec.ts',
      ],
      use: {
        ...devices['Desktop Chrome'],
        // API tests run in headless mode with no viewport needed.
        viewport: null,
      },
    },
  ],

  // Env vars surfaced to every test file via process.env.
  // Playwright does NOT auto-inject these; tests read process.env directly.
  globalSetup: undefined,
  globalTeardown: undefined,
});
