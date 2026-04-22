/**
 * Entry point — dispatches to one of the journey modules based on
 * OCTO_BROWSER_JOURNEY env or argv[2].
 *
 * Exit codes:
 *   0 — all iterations completed
 *   1 — at least one iteration failed
 *   2 — invalid arguments / unknown journey
 */

import { chromium } from "playwright";
import pino from "pino";

import { loadConfig } from "./config.js";

import { runJourney as catalogToCheckout } from "../journeys/catalog-to-checkout.js";
import { runJourney as crmAdminStroll } from "../journeys/crm-admin-stroll.js";
import { runJourney as errorRetryLoop } from "../journeys/error-retry-loop.js";

const JOURNEYS: Record<string, typeof catalogToCheckout> = {
  "catalog-to-checkout": catalogToCheckout,
  "crm-admin-stroll": crmAdminStroll,
  "error-retry-loop": errorRetryLoop,
};

const log = pino({ level: process.env.OCTO_BROWSER_LOG_LEVEL ?? "info" });

async function main(): Promise<number> {
  const cfg = loadConfig();
  const journeyName = process.argv[2] ?? cfg.journey;
  const journey = JOURNEYS[journeyName];

  if (!journey) {
    log.error(
      { journey: journeyName, available: Object.keys(JOURNEYS) },
      "unknown journey",
    );
    return 2;
  }

  log.info(
    {
      journey: journeyName,
      run_id: cfg.runId,
      operator: cfg.operator,
      iterations: cfg.iterations,
      shop_base_url: cfg.shopBaseUrl,
      crm_base_url: cfg.crmBaseUrl,
    },
    "browser runner starting",
  );

  const browser = await chromium.launch({ headless: cfg.headless });
  let failures = 0;

  try {
    for (let i = 1; i <= cfg.iterations; i++) {
      const context = await browser.newContext({
        viewport: { width: 1280, height: 720 },
        userAgent: `octo-browser-runner/1.0 (run_id=${cfg.runId}; iter=${i})`,
        recordHar: cfg.captureHar
          ? { path: `${cfg.artifactsDir}/${journeyName}-${cfg.runId}-${i}.har` }
          : undefined,
      });
      try {
        await journey(context, cfg);
        log.info(
          { iteration: i, run_id: cfg.runId, journey: journeyName },
          "iteration ok",
        );
      } catch (err) {
        failures++;
        log.error(
          {
            iteration: i,
            run_id: cfg.runId,
            journey: journeyName,
            error: String(err),
          },
          "iteration failed",
        );
      } finally {
        await context.close();
      }

      if (i < cfg.iterations) {
        await new Promise((r) => setTimeout(r, cfg.waitBetweenIterationsMs));
      }
    }
  } finally {
    await browser.close();
  }

  log.info(
    { run_id: cfg.runId, iterations: cfg.iterations, failures },
    "browser runner done",
  );
  return failures === 0 ? 0 : 1;
}

main().then((code) => process.exit(code));
