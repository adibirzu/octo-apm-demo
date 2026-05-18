import { defineConfig, devices } from '@playwright/test';

const shopUrl = process.env.OCTO_LIVE_SHOP_URL ?? process.env.SHOP_URL ?? 'http://localhost:8080';
const isLive = shopUrl.startsWith('https://');

export default defineConfig({
  testDir: '.',
  testMatch: 'octo-apm-demo-synthetic.spec.ts',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  timeout: 360_000,
  use: {
    baseURL: shopUrl,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: isLive ? 45_000 : 20_000,
    navigationTimeout: isLive ? 45_000 : 20_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
