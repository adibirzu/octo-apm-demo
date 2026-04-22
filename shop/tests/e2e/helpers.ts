/**
 * Shared helpers for the OCTO Drone Shop E2E test suite.
 *
 * All helpers are pure functions — no shared mutable state between tests.
 */

import { APIRequestContext, expect } from '@playwright/test';

// ── Environment ──────────────────────────────────────────────────────────────

export const SHOP_URL        = process.env.SHOP_URL        ?? 'http://localhost:8080';
export const CRM_URL         = process.env.CRM_URL         ?? 'http://localhost:8081';
export const COORDINATOR_URL = process.env.COORDINATOR_URL ?? '';

/** True when running against a live OKE deployment (HTTPS). */
export const IS_LIVE = SHOP_URL.startsWith('https://');

/**
 * Adjusted timeout (ms) for assertions that involve cross-service calls or
 * database queries — these can be slower on the live environment.
 */
export const INTEGRATION_TIMEOUT_MS = IS_LIVE ? 30_000 : 10_000;

// ── HTTP helpers ──────────────────────────────────────────────────────────────

export interface JsonResponse {
  status: number;
  body: unknown;
  headers: Record<string, string>;
}

/**
 * Perform a GET request using Playwright's API context and return parsed JSON
 * together with the status code and response headers.
 */
export async function apiGet(
  request: APIRequestContext,
  url: string,
  headers?: Record<string, string>,
): Promise<JsonResponse> {
  const response = await request.get(url, { headers });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = await response.text();
  }
  return {
    status: response.status(),
    body,
    headers: response.headers() as Record<string, string>,
  };
}

/**
 * Perform a POST request using Playwright's API context.
 */
export async function apiPost(
  request: APIRequestContext,
  url: string,
  payload?: unknown,
  headers?: Record<string, string>,
): Promise<JsonResponse> {
  const response = await request.post(url, {
    data: payload,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = await response.text();
  }
  return {
    status: response.status(),
    body,
    headers: response.headers() as Record<string, string>,
  };
}

/**
 * Perform a PUT request using Playwright's API context.
 */
export async function apiPut(
  request: APIRequestContext,
  url: string,
  payload?: unknown,
  headers?: Record<string, string>,
): Promise<JsonResponse> {
  const response = await request.put(url, {
    data: payload,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = await response.text();
  }
  return {
    status: response.status(),
    body,
    headers: response.headers() as Record<string, string>,
  };
}

// ── Assertion helpers ─────────────────────────────────────────────────────────

/**
 * Assert that a response body is a plain object (not an array or primitive).
 * Returns the body typed as a Record for follow-up property assertions.
 */
export function assertObject(body: unknown): Record<string, unknown> {
  expect(body).not.toBeNull();
  expect(typeof body).toBe('object');
  expect(Array.isArray(body)).toBe(false);
  return body as Record<string, unknown>;
}

/**
 * Assert that a value is a non-empty string.
 */
export function assertNonEmptyString(value: unknown, label: string): void {
  expect(typeof value, `${label} should be a string`).toBe('string');
  expect((value as string).length, `${label} should be non-empty`).toBeGreaterThan(0);
}

/**
 * Assert distributed trace headers exist and are non-empty.
 * Accepts either X-Trace-Id or traceparent (W3C).
 */
export function assertTraceHeaders(headers: Record<string, string>): void {
  const hasTraceId    = typeof headers['x-trace-id']    === 'string' && headers['x-trace-id'].length > 0;
  const hasTraceparent = typeof headers['traceparent']  === 'string' && headers['traceparent'].length > 0;
  const hasCorrelation = typeof headers['x-correlation-id'] === 'string' && headers['x-correlation-id'].length > 0;

  // At least one trace identifier must be present.
  const hasAnyTrace = hasTraceId || hasTraceparent;
  expect(
    hasAnyTrace,
    `Expected at least one trace header (x-trace-id or traceparent) in: ${JSON.stringify(headers)}`,
  ).toBe(true);

  // Correlation ID is optional but encouraged.
  if (hasCorrelation) {
    expect(headers['x-correlation-id'].length).toBeGreaterThan(0);
  }
}

// ── Retry helper ──────────────────────────────────────────────────────────────

/**
 * Retry an async function up to `maxAttempts` times with `delayMs` between
 * attempts. Useful for eventually-consistent checks (e.g., after a sync).
 */
export async function retryAsync<T>(
  fn: () => Promise<T>,
  maxAttempts = 3,
  delayMs = 1_000,
): Promise<T> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastError;
}
