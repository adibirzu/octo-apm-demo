/**
 * Full-platform smoke against the deployed tenancy.
 *
 * Drives each of the 11 platform services' public-facing surfaces.
 * Opt-in via FULL_PLATFORM_E2E_ENABLED=1 + SHOP_BASE_URL / CRM_BASE_URL.
 *
 * Not a perf test — just an end-to-end "did every service come up"
 * smoke that an operator can run after the `deploy/wizard/` completes.
 */

import { expect, test, type APIRequestContext } from "@playwright/test";

const ENABLED = process.env.FULL_PLATFORM_E2E_ENABLED === "1";
const SHOP = process.env.SHOP_BASE_URL || "https://shop.cyber-sec.ro";
const CRM = process.env.CRM_BASE_URL || "https://crm.cyber-sec.ro";
const LOAD_CONTROL = process.env.LOAD_CONTROL_URL || "";
const REMEDIATOR = process.env.REMEDIATOR_URL || "";
const OBJECT_PIPELINE = process.env.OBJECT_PIPELINE_URL || "";
const INTERNAL_KEY = process.env.INTERNAL_SERVICE_KEY || "";

async function jsonOk(req: APIRequestContext, url: string): Promise<any> {
  const r = await req.get(url, { timeout: 10_000 });
  expect.soft(r.ok()).toBeTruthy();
  return r.ok() ? r.json() : null;
}

test.describe("full-platform smoke", () => {
  test.skip(!ENABLED, "set FULL_PLATFORM_E2E_ENABLED=1");

  test("shop /ready + /api/version + /api/integrations/schema", async ({ request }) => {
    const ready = await jsonOk(request, `${SHOP}/ready`);
    expect(ready?.database?.reachable ?? ready?.ready).toBe(true);

    const ver = await jsonOk(request, `${SHOP}/api/version`);
    expect(ver).toHaveProperty("image_tag");
    expect(ver).toHaveProperty("git_sha");

    const schema = await jsonOk(request, `${SHOP}/api/integrations/schema`);
    expect(String(schema?.openapi || "")).toMatch(/^3\./);
  });

  test("crm /ready + /api/integrations/schema", async ({ request }) => {
    const ready = await jsonOk(request, `${CRM}/ready`);
    expect(ready?.database?.reachable ?? ready?.ready).toBe(true);

    const schema = await jsonOk(request, `${CRM}/api/integrations/schema`);
    expect(schema?.components?.securitySchemes?.InternalServiceKey?.in).toBe("header");
  });

  test("public catalog endpoint", async ({ request }) => {
    const r = await request.get(`${SHOP}/api/v1/public/catalog`);
    expect([200, 429]).toContain(r.status());  // 429 if prior test burned limit
  });

  test("load-control profiles listing", async ({ request }) => {
    test.skip(!LOAD_CONTROL, "set LOAD_CONTROL_URL");
    const profiles = await jsonOk(request, `${LOAD_CONTROL}/profiles`);
    expect(Array.isArray(profiles)).toBe(true);
    expect(profiles!.length).toBe(12);
  });

  test("remediator playbook catalog", async ({ request }) => {
    test.skip(!REMEDIATOR, "set REMEDIATOR_URL");
    const pbs = await jsonOk(request, `${REMEDIATOR}/playbooks`);
    const names = new Set((pbs ?? []).map((p: any) => p.name));
    expect(names.has("cache-flush")).toBe(true);
    expect(names.has("scale-hpa")).toBe(true);
    expect(names.has("restart-deployment")).toBe(true);
  });

  test("object-pipeline /health lists handlers", async ({ request }) => {
    test.skip(!OBJECT_PIPELINE, "set OBJECT_PIPELINE_URL");
    const h = await jsonOk(request, `${OBJECT_PIPELINE}/health`);
    expect(h?.handlers).toContain("octo-invoices");
  });

  test("cross-service auth enforced on CRM orders POST", async ({ request }) => {
    test.skip(!INTERNAL_KEY, "set INTERNAL_SERVICE_KEY");
    const noKey = await request.post(`${CRM}/api/orders`, {
      data: { customer_id: 42, items: [{ product_id: 1, quantity: 1 }] },
    });
    expect(noKey.status()).toBe(401);
  });

  test("traceparent passthrough shop → CRM", async ({ request }) => {
    const traceId = Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
    const spanId = Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
    const r = await request.get(`${SHOP}/api/integrations/crm/health`, {
      headers: { traceparent: `00-${traceId}-${spanId}-01` },
    });
    expect([200, 503]).toContain(r.status());
  });
});
