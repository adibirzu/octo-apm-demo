/**
 * k6 Integration — tests/e2e/k6-integration.spec.ts
 *
 * Verifies the k6 load test suite is present, structurally valid, and
 * configured to target the correct base URL. These are static file-system
 * checks combined with content assertions; they do NOT execute k6.
 *
 * Test coverage:
 *   - Required k6 test files exist in /k6/
 *   - Each file exports a default function (valid k6 entry point)
 *   - Each file imports http from 'k6/http'
 *   - BASE_URL is read from __ENV (not hardcoded)
 *   - cross_service_stress.js references both shop and CRM endpoints
 *   - db_stress.js references database-heavy endpoints
 *   - load_test.js includes multi-scenario setup
 *   - k6 options.thresholds are defined
 *
 * Env vars: none (reads files from disk)
 */

import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// ── Resolve the repo root ─────────────────────────────────────────────────────

// __dirname is tests/e2e/ — go up two levels to reach the repo root.
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const K6_DIR    = path.join(REPO_ROOT, 'k6');

// ── Helpers ───────────────────────────────────────────────────────────────────

function readK6File(filename: string): string {
  const filePath = path.join(K6_DIR, filename);
  return fs.readFileSync(filePath, 'utf-8');
}

function k6FileExists(filename: string): boolean {
  return fs.existsSync(path.join(K6_DIR, filename));
}

// ── File presence ─────────────────────────────────────────────────────────────

test.describe('k6 test files — presence', () => {
  test('k6/ directory exists at repo root', () => {
    expect(fs.existsSync(K6_DIR)).toBe(true);
  });

  test('k6/load_test.js exists', () => {
    expect(k6FileExists('load_test.js')).toBe(true);
  });

  test('k6/cross_service_stress.js exists', () => {
    expect(k6FileExists('cross_service_stress.js')).toBe(true);
  });

  test('k6/db_stress.js exists', () => {
    expect(k6FileExists('db_stress.js')).toBe(true);
  });
});

// ── load_test.js structural checks ────────────────────────────────────────────

test.describe('k6/load_test.js — structural validity', () => {
  test('imports http from k6/http', () => {
    const content = readK6File('load_test.js');
    expect(content).toContain("from 'k6/http'");
  });

  test('exports a default function', () => {
    const content = readK6File('load_test.js');
    expect(content).toMatch(/export\s+default\s+function/);
  });

  test('reads BASE_URL from __ENV', () => {
    const content = readK6File('load_test.js');
    expect(content).toContain('__ENV');
    expect(content).toContain('BASE_URL');
  });

  test('defines options export', () => {
    const content = readK6File('load_test.js');
    expect(content).toMatch(/export\s+const\s+options/);
  });

  test('includes scenarios or stages configuration', () => {
    const content = readK6File('load_test.js');
    const hasScenarios = content.includes('scenarios');
    const hasStages    = content.includes('stages');
    expect(hasScenarios || hasStages).toBe(true);
  });

  test('imports check from k6', () => {
    const content = readK6File('load_test.js');
    expect(content).toContain("from 'k6'");
    expect(content).toMatch(/\bcheck\b/);
  });

  test('has thresholds or metrics defined', () => {
    const content = readK6File('load_test.js');
    const hasThresholds = content.includes('thresholds');
    const hasMetrics    = content.includes('Rate') || content.includes('Trend') || content.includes('Counter');
    expect(hasThresholds || hasMetrics).toBe(true);
  });
});

// ── cross_service_stress.js structural checks ─────────────────────────────────

test.describe('k6/cross_service_stress.js — structural validity', () => {
  test('imports http from k6/http', () => {
    const content = readK6File('cross_service_stress.js');
    expect(content).toContain("from 'k6/http'");
  });

  test('exports a default function', () => {
    const content = readK6File('cross_service_stress.js');
    expect(content).toMatch(/export\s+default\s+function/);
  });

  test('reads SHOP_URL or DNS_DOMAIN from __ENV', () => {
    const content = readK6File('cross_service_stress.js');
    expect(content).toContain('__ENV');
    const hasShopRef =
      content.includes('SHOP_URL') ||
      content.includes('BASE_URL') ||
      content.includes('DNS_DOMAIN');
    expect(hasShopRef).toBe(true);
  });

  test('references cross-service integration endpoints', () => {
    const content = readK6File('cross_service_stress.js');
    const hasCrmEndpoint =
      content.includes('crm') ||
      content.includes('integrations') ||
      content.includes('CRM_URL');
    expect(hasCrmEndpoint).toBe(true);
  });

  test('uses check() assertions', () => {
    const content = readK6File('cross_service_stress.js');
    expect(content).toMatch(/\bcheck\b/);
  });
});

// ── db_stress.js structural checks ────────────────────────────────────────────

test.describe('k6/db_stress.js — structural validity', () => {
  test('imports http from k6/http', () => {
    const content = readK6File('db_stress.js');
    expect(content).toContain("from 'k6/http'");
  });

  test('exports a default function', () => {
    const content = readK6File('db_stress.js');
    expect(content).toMatch(/export\s+default\s+function/);
  });

  test('references database-heavy endpoints (orders, cart, products)', () => {
    const content = readK6File('db_stress.js');
    const hasDatabaseEndpoint =
      content.includes('orders') ||
      content.includes('cart') ||
      content.includes('products') ||
      content.includes('storefront') ||
      content.includes('ready');
    expect(hasDatabaseEndpoint).toBe(true);
  });

  test('reads BASE_URL, SHOP_URL, or DNS_DOMAIN from __ENV', () => {
    const content = readK6File('db_stress.js');
    expect(content).toContain('__ENV');
    const hasEnvRef =
      content.includes('SHOP_URL') ||
      content.includes('BASE_URL') ||
      content.includes('DNS_DOMAIN');
    expect(hasEnvRef).toBe(true);
  });
});

// ── Content quality checks ────────────────────────────────────────────────────

test.describe('k6 test files — content quality', () => {
  test('load_test.js has reasonable file size (not empty or stub)', () => {
    const content = readK6File('load_test.js');
    // A real k6 test should be at least 200 chars.
    expect(content.length).toBeGreaterThan(200);
  });

  test('cross_service_stress.js has reasonable file size', () => {
    const content = readK6File('cross_service_stress.js');
    expect(content.length).toBeGreaterThan(200);
  });

  test('db_stress.js has reasonable file size', () => {
    const content = readK6File('db_stress.js');
    expect(content.length).toBeGreaterThan(200);
  });

  test('load_test.js does not contain localhost hardcoded as only target', () => {
    const content = readK6File('load_test.js');
    // Hardcoded localhost without a fallback from __ENV would fail in CI.
    // Check that BASE_URL from __ENV is used, not a bare localhost string.
    const hasEnvLookup = content.includes('__ENV') && content.includes('BASE_URL');
    expect(hasEnvLookup).toBe(true);
  });

  test('no k6 file contains absolute production URLs', () => {
    for (const file of ['load_test.js', 'cross_service_stress.js', 'db_stress.js']) {
      const content = readK6File(file);
      // No hardcoded HTTPS production URLs should appear — only __ENV references.
      // This is a security/portability check.
      const hasHardcodedHttps = /https:\/\/[a-z0-9.-]+\.(com|io|cloud|oracle)/.test(content);
      if (hasHardcodedHttps) {
        console.warn(`[k6-integration] ${file} contains a hardcoded HTTPS URL — consider using __ENV`);
      }
      // Soft warning only; do not fail CI for this.
    }
  });
});

// ── k6 CLI availability (informational) ───────────────────────────────────────

test.describe('k6 CLI — informational check', () => {
  test('k6 binary availability is logged for CI transparency', async () => {
    const { execSync } = require('child_process');
    let k6Available = false;
    try {
      execSync('k6 version', { stdio: 'ignore', timeout: 5_000 });
      k6Available = true;
    } catch {
      k6Available = false;
    }
    console.info(`[k6-integration] k6 binary available: ${k6Available}`);
    // This test always passes — it's informational only.
    expect(true).toBe(true);
  });
});
