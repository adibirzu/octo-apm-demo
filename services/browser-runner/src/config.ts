/**
 * Runtime config for octo-browser-runner.
 *
 * Pulled entirely from env so the same binary runs as:
 *   - a K8s Job (one-shot, via OCTO_BROWSER_RUN_COUNT=1)
 *   - a CronJob (periodic synthetic)
 *   - a local dev run (`npm run run:catalog`)
 */

import { createHash } from "node:crypto";

export interface BrowserRunnerConfig {
  shopBaseUrl: string;
  crmBaseUrl: string;

  runId: string;
  operator: string;
  syntheticUserDomain: string;
  syntheticUsers: SyntheticUserIdentity[];
  selectedSyntheticUser?: SyntheticUserIdentity;

  journey: string;
  iterations: number;

  artifactsDir: string;
  captureScreenshots: boolean;
  captureHar: boolean;
  headless: boolean;

  waitBetweenIterationsMs: number;
  timeoutPerActionMs: number;
}

export interface SyntheticUserIdentity {
  username: string;
  email: string;
  displayName: string;
  domain: string;
}

const DEFAULT_SYNTHETIC_USER_DOMAIN = "apex.example.test";
const DEFAULT_SYNTHETIC_USER_NAMES = [
  ["alex", "chen", "Alex Chen"],
  ["maya", "ionescu", "Maya Ionescu"],
  ["nora", "patel", "Nora Patel"],
  ["daniel", "rossi", "Daniel Rossi"],
  ["irina", "marin", "Irina Marin"],
  ["samuel", "wright", "Samuel Wright"],
  ["elena", "garcia", "Elena Garcia"],
  ["noah", "kim", "Noah Kim"],
  ["sofia", "andersen", "Sofia Andersen"],
  ["matei", "popa", "Matei Popa"],
  ["lina", "hoffman", "Lina Hoffman"],
  ["omar", "saleh", "Omar Saleh"],
] as const;

const DOMAIN_RE = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/;

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

function normalizeDomain(domain: string): string {
  const normalized = (domain || DEFAULT_SYNTHETIC_USER_DOMAIN).trim().toLowerCase();
  if (normalized.includes("@") || normalized.includes("/") || !DOMAIN_RE.test(normalized)) {
    throw new Error(`Invalid synthetic user domain: ${domain}`);
  }
  return normalized;
}

function displayNameFromEmail(email: string): string {
  const local = email.split("@")[0] || "synthetic.user";
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function identityFromEmail(email: string): SyntheticUserIdentity {
  const normalized = email.trim().toLowerCase();
  const [local, domain = ""] = normalized.split("@");
  if (!local || !DOMAIN_RE.test(domain)) {
    throw new Error(`Invalid synthetic user e-mail: ${email}`);
  }
  return {
    username: local,
    email: normalized,
    displayName: displayNameFromEmail(normalized),
    domain,
  };
}

export function buildSyntheticUsers(domain: string, explicitList = ""): SyntheticUserIdentity[] {
  const list = explicitList
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  if (list.length > 0) {
    return list.map(identityFromEmail);
  }

  const safeDomain = normalizeDomain(domain);
  return DEFAULT_SYNTHETIC_USER_NAMES.map(([first, last, displayName]) => {
    const username = `${first}.${last}`;
    return {
      username,
      email: `${username}@${safeDomain}`,
      displayName,
      domain: safeDomain,
    };
  });
}

export function selectSyntheticUser(config: BrowserRunnerConfig, iteration: number): SyntheticUserIdentity {
  const pool = config.syntheticUsers.length
    ? config.syntheticUsers
    : buildSyntheticUsers(config.syntheticUserDomain, "");
  const index = Math.max(0, iteration - 1) % pool.length;
  return pool[index];
}

export function syntheticIdentityHeaders(user?: SyntheticUserIdentity): Record<string, string> {
  if (!user) return {};
  const syntheticUserHash = createHash("sha256").update(user.email).digest("hex").slice(0, 16);
  return {
    "X-Synthetic-User": user.username,
    "X-Synthetic-User-Domain": user.domain,
    "X-Synthetic-User-Hash": syntheticUserHash,
  };
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
  const syntheticUserDomain = env("OCTO_BROWSER_SYNTHETIC_USER_DOMAIN", DEFAULT_SYNTHETIC_USER_DOMAIN);
  return {
    shopBaseUrl: env("OCTO_BROWSER_SHOP_URL", "https://shop.example.test"),
    crmBaseUrl: env("OCTO_BROWSER_CRM_URL", "https://crm.example.test"),

    runId: env("OCTO_BROWSER_RUN_ID") || generateRunId(),
    operator: env("OCTO_BROWSER_OPERATOR", "browser-runner"),
    syntheticUserDomain: normalizeDomain(syntheticUserDomain),
    syntheticUsers: buildSyntheticUsers(
      syntheticUserDomain,
      env("OCTO_BROWSER_SYNTHETIC_USERS", env("OCTO_BROWSER_SYNTHETIC_USER_EMAIL", "")),
    ),

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
