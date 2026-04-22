/**
 * Journey: error-retry-loop.
 *
 * Intentionally hits failing endpoints so APM dashboards have reliable
 * 4xx/5xx signal. Used by the `app-exception-storm` profile in
 * octo-load-control.
 */

import type { BrowserContext } from "playwright";
import type { BrowserRunnerConfig } from "../src/config.js";

export async function runJourney(
  context: BrowserContext,
  config: BrowserRunnerConfig,
): Promise<void> {
  const page = await context.newPage();

  await page.setExtraHTTPHeaders({
    "X-Run-Id": config.runId,
    "X-Operator": config.operator,
    "X-Workflow-Id": `browser.${config.journey}`,
  });

  // 4xx — malformed payloads
  for (let i = 0; i < 5; i++) {
    await page.request
      .post(`${config.shopBaseUrl}/api/orders`, {
        data: { customer_id: 0, items: [] },
        headers: { "X-Run-Id": config.runId },
      })
      .catch(() => undefined);
  }

  // 404 — probe
  for (let i = 0; i < 3; i++) {
    await page.request
      .get(`${config.shopBaseUrl}/api/intentionally-missing-${i}`, {
        headers: { "X-Run-Id": config.runId },
      })
      .catch(() => undefined);
  }

  // Failed page load (network 404)
  await page
    .goto(`${config.shopBaseUrl}/page-that-does-not-exist`, {
      timeout: config.timeoutPerActionMs,
    })
    .catch(() => undefined);

  await page.close();
}
