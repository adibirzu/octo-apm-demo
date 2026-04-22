/**
 * Runtime config for octo-browser-runner.
 *
 * Pulled entirely from env so the same binary runs as:
 *   - a K8s Job (one-shot, via OCTO_BROWSER_RUN_COUNT=1)
 *   - a CronJob (periodic synthetic)
 *   - a local dev run (`npm run run:catalog`)
 */

export interface BrowserRunnerConfig {
  shopBaseUrl: string;
  crmBaseUrl: string;

  runId: string;
  operator: string;

  journey: string;
  iterations: number;

  artifactsDir: string;
  captureScreenshots: boolean;
  captureHar: boolean;
  headless: boolean;

  waitBetweenIterationsMs: number;
  timeoutPerActionMs: number;
}

function env(key: string, fallback = ""): string {
  return process.env[key] ?? fallback;
}

function envInt(key: string, fallback: number): number {
  const v = process.env[key];
  if (!v) return fallback;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : fallback;
}

function envBool(key: string, fallback: boolean): boolean {
  const v = process.env[key];
  if (!v) return fallback;
  return ["1", "true", "yes", "on"].includes(v.toLowerCase());
}

function generateRunId(): string {
  // W3C-compatible UUID v4 via crypto
  // Node 18+ has crypto.randomUUID().
  // The runner accepts an explicit runId via env so load-control can
  // inject its own and ensure every signal joins across the platform.
  return (globalThis as any).crypto?.randomUUID?.() ?? randomHex(32);
}

function randomHex(chars: number): string {
  let out = "";
  for (let i = 0; i < chars; i++) out += ((Math.random() * 16) | 0).toString(16);
  return out;
}

export function loadConfig(): BrowserRunnerConfig {
  return {
    shopBaseUrl: env("OCTO_BROWSER_SHOP_URL", "https://drone.octodemo.cloud"),
    crmBaseUrl: env("OCTO_BROWSER_CRM_URL", "https://backend.octodemo.cloud"),

    runId: env("OCTO_BROWSER_RUN_ID") || generateRunId(),
    operator: env("OCTO_BROWSER_OPERATOR", "browser-runner"),

    journey: env("OCTO_BROWSER_JOURNEY", "catalog-to-checkout"),
    iterations: envInt("OCTO_BROWSER_ITERATIONS", 1),

    artifactsDir: env("OCTO_BROWSER_ARTIFACTS_DIR", "/tmp/octo-browser-runner"),
    captureScreenshots: envBool("OCTO_BROWSER_CAPTURE_SCREENSHOTS", true),
    captureHar: envBool("OCTO_BROWSER_CAPTURE_HAR", true),
    headless: envBool("OCTO_BROWSER_HEADLESS", true),

    waitBetweenIterationsMs: envInt("OCTO_BROWSER_WAIT_MS", 2000),
    timeoutPerActionMs: envInt("OCTO_BROWSER_TIMEOUT_MS", 15000),
  };
}
