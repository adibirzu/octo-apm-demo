import { test, expect } from '@playwright/test';

/*
 * OCI APM Availability Monitoring Scripted Browser script for the OCTO demo.
 *
 * Upload this file as a Playwright script in Availability Monitoring. It is
 * intentionally frontend-only: it drives the shop and optional admin demo
 * paths, but it does not navigate the OCI Console.
 *
 * Keep real live URLs and credentials out of Git. Configure them as script
 * parameters, Vault-backed values, or environment variables in the monitor.
 */

const env = (globalThis as any).process?.env || {};

const SHOP_URL_PARAM = "https://shop.example.test";
const ADMIN_URL_PARAM = "https://admin.example.test";
// <ORAP><ON>OCTO_LIVE_SHOP_URL</ON><OV>https://shop.example.test</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_LIVE_ADMIN_URL</ON><OV>https://admin.example.test</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_APM_DEMO_MODE</ON><OV>monitor</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_ADMIN_USERNAME</ON><OV>admin</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_ADMIN_PASSWORD</ON><OS>true</OS></ORAP>

const SHOP_URL = env.OCTO_LIVE_SHOP_URL || env.SHOP_URL || SHOP_URL_PARAM;
const ADMIN_URL = env.OCTO_LIVE_ADMIN_URL || env.ADMIN_URL || ADMIN_URL_PARAM;
const RUN_ADMIN_STORYBOARD = String(env.RUN_ADMIN_STORYBOARD || "false").toLowerCase() === "true";
const DEMO_MODE = env.OCTO_APM_DEMO_MODE === "full" ? "full" : "monitor";

type BuyerScenario = {
  label: string;
  name: string;
  email: string;
  persona: string;
  company: string;
  quantity: 2 | 3;
} & (
  | {
      kind: "card";
      cardNumber: string;
      expiry: string;
      cvv: string;
      expectedPaymentStatus: "paid" | "failed";
    }
  | {
      kind: "wallet";
      method: "apple_pay" | "google_pay";
      expectedPaymentStatus: "paid";
    }
  | {
      kind: "manual";
      method: "bank_transfer";
    }
);

const BUYER_SCENARIOS: BuyerScenario[] = [
  {
    kind: "card",
    label: "alex-fleet-mastercard-approved",
    name: "Alex Chen",
    email: "alex.chen@apex.example.test",
    persona: "Fleet operations buyer",
    company: "Apex Fleet Operations",
    quantity: 2,
    cardNumber: "5555555555554444",
    expiry: "12/30",
    cvv: "321",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "card",
    label: "maya-field-visa-approved",
    name: "Maya Ionescu",
    email: "maya.ionescu@apex.example.test",
    persona: "Field services buyer",
    company: "Apex Field Services",
    quantity: 3,
    cardNumber: "4111111111111111",
    expiry: "12/30",
    cvv: "123",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "card",
    label: "nora-energy-issuer-decline",
    name: "Nora Patel",
    email: "nora.patel@apex.example.test",
    persona: "Energy survey buyer",
    company: "Apex Energy Survey",
    quantity: 2,
    cardNumber: "4000000000000002",
    expiry: "12/30",
    cvv: "123",
    expectedPaymentStatus: "failed",
  },
  {
    kind: "manual",
    label: "daniel-infrastructure-bank-transfer",
    name: "Daniel Rossi",
    email: "daniel.rossi@apex.example.test",
    persona: "Infrastructure buyer",
    company: "Apex Infrastructure",
    quantity: 3,
    method: "bank_transfer",
  },
  {
    kind: "wallet",
    label: "irina-public-safety-apple-pay",
    name: "Irina Marin",
    email: "irina.marin@apex.example.test",
    persona: "Public safety buyer",
    company: "Apex Public Safety",
    quantity: 2,
    method: "apple_pay",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "wallet",
    label: "samuel-logistics-google-pay",
    name: "Samuel Wright",
    email: "samuel.wright@apex.example.test",
    persona: "Logistics buyer",
    company: "Apex Logistics",
    quantity: 3,
    method: "google_pay",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "card",
    label: "elena-agriculture-visa-approved",
    name: "Elena Garcia",
    email: "elena.garcia@apex.example.test",
    persona: "Agriculture buyer",
    company: "Apex Agriculture",
    quantity: 2,
    cardNumber: "4111111111111111",
    expiry: "12/30",
    cvv: "123",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "card",
    label: "noah-inspection-mastercard-approved",
    name: "Noah Kim",
    email: "noah.kim@apex.example.test",
    persona: "Inspection buyer",
    company: "Apex Inspection Services",
    quantity: 3,
    cardNumber: "5555555555554444",
    expiry: "12/30",
    cvv: "321",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "wallet",
    label: "sofia-rail-apple-pay",
    name: "Sofia Andersen",
    email: "sofia.andersen@apex.example.test",
    persona: "Rail systems buyer",
    company: "Apex Rail Systems",
    quantity: 2,
    method: "apple_pay",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "wallet",
    label: "matei-utilities-google-pay",
    name: "Matei Popa",
    email: "matei.popa@apex.example.test",
    persona: "Utilities buyer",
    company: "Apex Utilities",
    quantity: 3,
    method: "google_pay",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "card",
    label: "lina-emergency-visa-approved",
    name: "Lina Hoffman",
    email: "lina.hoffman@apex.example.test",
    persona: "Emergency response buyer",
    company: "Apex Emergency Response",
    quantity: 2,
    cardNumber: "4111111111111111",
    expiry: "12/30",
    cvv: "123",
    expectedPaymentStatus: "paid",
  },
  {
    kind: "manual",
    label: "omar-maritime-bank-transfer",
    name: "Omar Saleh",
    email: "omar.saleh@apex.example.test",
    persona: "Maritime buyer",
    company: "Apex Maritime",
    quantity: 3,
    method: "bank_transfer",
  },
];

function url(base: string, path: string, syntheticUser?: string): string {
  const value = new URL(path, base.replace(/\/$/, "") + "/");
  if (syntheticUser) value.searchParams.set("synthetic_user", syntheticUser);
  return value.toString();
}

function adminCredentials(): { username: string; password: string } {
  if (env.BOOTSTRAP_ADMIN_USERNAME && env.BOOTSTRAP_ADMIN_PASSWORD) {
    return { username: env.BOOTSTRAP_ADMIN_USERNAME, password: env.BOOTSTRAP_ADMIN_PASSWORD };
  }

  const username = env.OCTO_ADMIN_USERNAME || env.ADMIN_USERNAME || "admin";
  const password = env.OCTO_ADMIN_PASSWORD || env.ADMIN_PASSWORD || "";
  if (!password) {
    throw new Error("Admin password is missing. Configure OCTO_ADMIN_PASSWORD as a secret monitor parameter.");
  }
  return { username, password };
}

function objectField(value: unknown, label: string): Record<string, unknown> {
  expect(value, `${label} should be present`).toBeTruthy();
  expect(typeof value, `${label} should be an object`).toBe("object");
  expect(Array.isArray(value), `${label} should not be an array`).toBe(false);
  return value as Record<string, unknown>;
}

function stringField(value: unknown, label: string): string {
  expect(typeof value, `${label} should be a string`).toBe("string");
  expect((value as string).length, `${label} should be non-empty`).toBeGreaterThan(0);
  return value as string;
}

function paymentMethod(scenario: BuyerScenario): string {
  if (scenario.kind === "card") return "credit_card";
  return scenario.method;
}

function assertTraceableCheckout(body: Record<string, unknown>, scenario: BuyerScenario): void {
  stringField(body.trace_id, "checkout.trace_id");
  const method = paymentMethod(scenario);
  if (method === "bank_transfer") {
    expect(body.payment_status).toBe("pending");
    return;
  }

  const payment = objectField(body.payment, "checkout.payment");
  stringField(payment.provider, "payment.provider");
  expect(payment.method).toBe(method);
  expect(body.payment_status).toBe(scenario.kind === "card" || scenario.kind === "wallet" ? scenario.expectedPaymentStatus : "pending");
  const gateway = objectField(payment.gateway, "payment.gateway");
  expect(gateway.gateway).toBe("octo-payment-gateway-emulator");
  expect(gateway.provider).toBe("cybersource-compatible-simulator");
  stringField(gateway.request_id, "payment.gateway.request_id");

  const steps = Array.isArray(gateway.steps) ? gateway.steps : [];
  const names = steps.map((step) => String((step as Record<string, unknown>).name || ""));
  expect(names).toContain("gateway_payment_received");
  expect(names).toContain("verification_antifraud_request");
  expect(names).toContain("verification_antifraud_response");
  expect(names).toContain("processor_authorization_request");
  expect(names).toContain("network_authorization_routing");

  const verification = objectField(gateway.verification, "payment.gateway.verification");
  expect(verification.provider).toBe("octo-antifraud-verification-app");
  stringField(verification.decision, "payment.gateway.verification.decision");
}

test("OCTO APM availability monitor", async ({ page }) => {
  test.setTimeout(360000);

  async function screenshot(name: string): Promise<void> {
    console.log(`oraSynCustomScreenshot:${name}`);
    await page.waitForTimeout(250);
  }

  async function openShop(scenario: BuyerScenario): Promise<void> {
    await page.goto(url(SHOP_URL, "/shop", scenario.email), { waitUntil: "domcontentloaded" });
    await expect(page.locator(".product-card").first()).toBeVisible({ timeout: 45000 });
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => undefined);
    await screenshot("01-shop-catalog");
  }

  async function stockedProductIds(quantity: number): Promise<number[]> {
    const ids = await page.evaluate(async (requestedQuantity: number) => {
      const response = await fetch("/api/shop/storefront", { headers: { Accept: "application/json" } });
      const body = (await response.json()) as { products?: any[] };
      const products = Array.isArray(body.products) ? body.products : [];
      const stocked = products
        .filter((product: any) => Number(product.stock || 0) > 0)
        .sort((left: any, right: any) => {
          const stockDelta = Number(right.stock || 0) - Number(left.stock || 0);
          return stockDelta || Number(left.price || 0) - Number(right.price || 0);
        });
      const selected: number[] = [];
      for (const product of stocked) {
        const copies = Math.min(Number(product.stock || 0), requestedQuantity - selected.length);
        for (let index = 0; index < copies; index += 1) selected.push(Number(product.id));
        if (selected.length >= requestedQuantity) break;
      }
      return selected;
    }, quantity);
    expect(ids.length, `storefront should expose ${quantity} in-stock drone units`).toBe(quantity);
    return ids;
  }

  async function addProducts(quantity: number): Promise<void> {
    const productIds = await stockedProductIds(quantity);
    for (const productId of productIds) {
      const addButton = page.locator(`.add-btn[data-id="${productId}"]`).first();
      await addButton.click();
      await expect(page.locator(".cart-item").first()).toBeVisible({ timeout: 20000 });
    }
    await expect(page.locator("#cartChip")).toHaveText(new RegExp(`${quantity} items?`), { timeout: 20000 });
  }

  async function fillBuyer(scenario: BuyerScenario): Promise<void> {
    const method = paymentMethod(scenario);
    await page.fill('#checkoutForm [name="customer_name"]', scenario.name);
    await page.fill('#checkoutForm [name="customer_email"]', scenario.email);
    await page.fill('#checkoutForm [name="company"]', scenario.company);
    await page.fill('#checkoutForm [name="customer_phone"]', "+1 555 0184");
    await page.fill('#checkoutForm [name="shipping_address"]', `100 Demo Operations Way - ${scenario.persona}`);
    await page.selectOption('#checkoutForm [name="payment_method"]', method);
    await page.fill('#checkoutForm [name="coupon_code"]', "DEMO-LAB").catch(() => undefined);

    if (scenario.kind === "card") {
      await page.fill('#checkoutForm [name="card_number"]', scenario.cardNumber);
      await page.fill('#checkoutForm [name="card_expiry"]', scenario.expiry);
      await page.fill('#checkoutForm [name="card_cvv"]', scenario.cvv);
      await page.fill('#checkoutForm [name="cardholder_name"]', scenario.name);
      await page.fill('#checkoutForm [name="billing_postal_code"]', "10001");
    }

    if (method === "apple_pay") {
      await page.getByTestId("apple-pay-button").click();
    }

    if (method === "google_pay") {
      await page.getByTestId("google-pay-button").click();
    }
  }

  async function placeOrder(scenario: BuyerScenario): Promise<void> {
    const method = paymentMethod(scenario);
    await openShop(scenario);
    await addProducts(scenario.quantity);
    await fillBuyer(scenario);
    await screenshot(`02-checkout-ready-${scenario.label}`);
    const checkoutResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/shop/checkout") && response.request().method() === "POST",
      { timeout: 90000 },
    );
    await page.click("#checkoutSubmitButton");
    const checkoutResponse = await checkoutResponsePromise;
    expect(checkoutResponse.status()).toBe(200);
    const checkout = objectField(await checkoutResponse.json(), "checkout response");
    assertTraceableCheckout(checkout, scenario);
    console.log(
      `octoSynthetic:buyer=${scenario.email};persona=${scenario.persona};quantity=${scenario.quantity};payment=${method}`,
    );
    await page.waitForFunction(
      () => {
        const text = document.querySelector("#checkoutStatus")?.textContent || "";
        return /Order #|Order placed|Order created|Checkout failed|Request failed|Payment failed|success|complete|declined/i.test(text);
      },
      null,
      { timeout: 90000 },
    );
    await screenshot(`03-checkout-result-${scenario.label}`);
  }

  async function submitSupportTicket(syntheticUser: string): Promise<void> {
    await page.goto(url(SHOP_URL, "/services", syntheticUser), { waitUntil: "domcontentloaded" });
    await expect(page.locator("#ticketForm")).toBeVisible({ timeout: 30000 });
    const bookButton = page.locator("button", { hasText: "Book" }).first();
    if (await bookButton.count()) await bookButton.click();
    await page.fill("#ticketTitle", "Request: drone telemetry support").catch(() => undefined);
    await page.fill(
      "#ticketContent",
      "Synthetic monitor validating checkout, support, RUM, app logs, Java spans, and SQL spans.",
    ).catch(() => undefined);
    await page.selectOption("#ticketPriority", "low").catch(() => undefined);
    await screenshot("04-support-ticket-ready");
    await page.locator("#ticketForm button[type='submit']").click();
    await page.waitForFunction(
      () => /Ticket successfully created|Error:/i.test(document.querySelector("#ticketFormStatus")?.textContent || ""),
      null,
      { timeout: 30000 },
    );
    await screenshot("05-support-ticket-result");
  }

  async function runAdminStoryboard(): Promise<void> {
    const { username, password } = adminCredentials();

    await page.goto(url(ADMIN_URL, "/login"), { waitUntil: "domcontentloaded" });
    await expect(page.locator("#login-username")).toBeVisible({ timeout: 30000 });
    await page.fill("#login-username", username);
    await page.fill("#login-password", password);
    await page.click('#login-form button[type="submit"]');
    await page.waitForURL((current: URL) => !current.pathname.startsWith("/login"), { timeout: 45000 });
    await page.goto(url(ADMIN_URL, "/settings"), { waitUntil: "domcontentloaded" });
    await expect(page.locator("#card-storyboard")).toBeVisible({ timeout: 45000 });
    await screenshot("06-admin-simulation");

    const javaCard = page.locator("#card-drone-shop");
    if (await javaCard.count()) {
      await javaCard.locator("button", { hasText: "Java Health" }).click();
      await page.waitForTimeout(3000);
      await screenshot("07-admin-java-health");
    }

    const storyCard = page.locator("#card-storyboard");
    if (await storyCard.count()) {
      await storyCard.locator("button", { hasText: "Run Story" }).click();
      await page.waitForFunction(
        () => {
          const text = document.querySelector("#story-output")?.textContent || "";
          return text && !/running|proxying/i.test(text);
        },
        null,
        { timeout: 120000 },
      ).catch(() => undefined);
      await screenshot("08-admin-storyboard");
    }
  }

  for (const scenario of BUYER_SCENARIOS) {
    await placeOrder(scenario);
  }

  await submitSupportTicket(BUYER_SCENARIOS[0].email);

  if (RUN_ADMIN_STORYBOARD || DEMO_MODE === "full") {
    await runAdminStoryboard();
  }
});
