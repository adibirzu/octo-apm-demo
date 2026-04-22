/**
 * Journey: crm-admin-stroll.
 *
 * A CRM operator's typical session:
 *   1. Land on admin dashboard.
 *   2. Open the customers list.
 *   3. Open the tickets list.
 *   4. Open the catalog page.
 *
 * No writes — just a read-heavy stroll that generates APM latency
 * distribution + RUM timing signal.
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

  for (const path of ["/", "/customers", "/tickets", "/catalog"]) {
    await page
      .goto(`${config.crmBaseUrl}${path}`, { timeout: config.timeoutPerActionMs })
      .catch(() => undefined);
    await page.waitForLoadState("domcontentloaded", {
      timeout: config.timeoutPerActionMs,
    }).catch(() => undefined);
  }

  if (config.captureScreenshots) {
    await page.screenshot({
      path: `${config.artifactsDir}/crm-admin-${config.runId}.png`,
      fullPage: true,
    });
  }

  await page.close();
}
