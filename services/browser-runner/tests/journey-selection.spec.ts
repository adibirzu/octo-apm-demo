/**
 * Unit tests — verify the journey registry is well-formed and the
 * config loader honours env vars. These tests do NOT launch a real
 * browser (that's what running the journey is for); they assert the
 * scaffolding is sound.
 */

import { expect, test } from "@playwright/test";

import {
  buildSyntheticUsers,
  loadConfig,
  selectSyntheticUser,
  syntheticIdentityHeaders,
} from "../src/config.js";

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

  test("synthetic users default to the reserved Apex demo domain", () => {
    delete process.env.OCTO_BROWSER_SYNTHETIC_USER_DOMAIN;
    delete process.env.OCTO_BROWSER_SYNTHETIC_USERS;
    const cfg = loadConfig();

    expect(cfg.syntheticUserDomain).toBe("apex.example.test");
    expect(cfg.syntheticUsers.length).toBeGreaterThanOrEqual(8);
    expect(cfg.syntheticUsers.every((user) => user.email.endsWith("@apex.example.test"))).toBe(true);
    expect(JSON.stringify(cfg.syntheticUsers)).not.toContain("oracle.com");
  });

  test("synthetic user pool can be overridden by env list", () => {
    process.env.OCTO_BROWSER_SYNTHETIC_USERS = "alex.chen@corp.example.test, maya.ionescu@corp.example.test";
    try {
      const cfg = loadConfig();
      expect(cfg.syntheticUsers.map((user) => user.email)).toEqual([
        "alex.chen@corp.example.test",
        "maya.ionescu@corp.example.test",
      ]);
      expect(selectSyntheticUser(cfg, 2).email).toBe("maya.ionescu@corp.example.test");
    } finally {
      delete process.env.OCTO_BROWSER_SYNTHETIC_USERS;
    }
  });

  test("buildSyntheticUsers rejects unsafe domains", () => {
    expect(() => buildSyntheticUsers("bad domain.test", "")).toThrow(/domain/i);
  });

  test("synthetic identity headers omit raw e-mail values", () => {
    const [user] = buildSyntheticUsers("corp.example.test", "alex.chen@corp.example.test");
    const headers = syntheticIdentityHeaders(user);

    expect(headers["X-Synthetic-User"]).toBe("alex.chen");
    expect(headers["X-Synthetic-User-Domain"]).toBe("corp.example.test");
    expect(headers["X-Synthetic-User-Hash"]).toMatch(/^[0-9a-f]{16}$/);
    expect(headers).not.toHaveProperty("X-Synthetic-User-Email");
    expect(JSON.stringify(headers)).not.toContain("alex.chen@corp.example.test");
  });
});
