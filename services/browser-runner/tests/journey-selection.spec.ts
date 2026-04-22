/**
 * Unit tests — verify the journey registry is well-formed and the
 * config loader honours env vars. These tests do NOT launch a real
 * browser (that's what running the journey is for); they assert the
 * scaffolding is sound.
 */

import { expect, test } from "@playwright/test";

import { loadConfig } from "../src/config.js";

test.describe("config loader", () => {
  test("honours OCTO_BROWSER_SHOP_URL env", () => {
    process.env.OCTO_BROWSER_SHOP_URL = "https://shop.test.invalid";
    try {
      const cfg = loadConfig();
      expect(cfg.shopBaseUrl).toBe("https://shop.test.invalid");
    } finally {
      delete process.env.OCTO_BROWSER_SHOP_URL;
    }
  });

  test("generates a runId when not provided", () => {
    delete process.env.OCTO_BROWSER_RUN_ID;
    const cfg = loadConfig();
    expect(cfg.runId).toMatch(/^[0-9a-f-]{32,}$/);
  });

  test("honours OCTO_BROWSER_RUN_ID env", () => {
    process.env.OCTO_BROWSER_RUN_ID = "fixed-run-id-for-test";
    try {
      const cfg = loadConfig();
      expect(cfg.runId).toBe("fixed-run-id-for-test");
    } finally {
      delete process.env.OCTO_BROWSER_RUN_ID;
    }
  });

  test("iterations defaults to 1", () => {
    delete process.env.OCTO_BROWSER_ITERATIONS;
    const cfg = loadConfig();
    expect(cfg.iterations).toBe(1);
  });

  test("iterations can be overridden", () => {
    process.env.OCTO_BROWSER_ITERATIONS = "5";
    try {
      const cfg = loadConfig();
      expect(cfg.iterations).toBe(5);
    } finally {
      delete process.env.OCTO_BROWSER_ITERATIONS;
    }
  });

  test("headless defaults to true (K8s job path)", () => {
    delete process.env.OCTO_BROWSER_HEADLESS;
    const cfg = loadConfig();
    expect(cfg.headless).toBe(true);
  });
});
