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

declare const page: any;

const env = (globalThis as any).process?.env || {};

const SHOP_URL = env.OCTO_LIVE_SHOP_URL || env.SHOP_URL || "https://shop.example.test";
const ADMIN_URL = env.OCTO_LIVE_ADMIN_URL || env.ADMIN_URL || "https://admin.example.test";
const ADMIN_USERNAME = env.BOOTSTRAP_ADMIN_USERNAME || env.ADMIN_USERNAME || "admin";
const ADMIN_PASSWORD = env.BOOTSTRAP_ADMIN_PASSWORD || env.ADMIN_PASSWORD || "";
const PAYMENT_METHOD = env.PAYMENT_METHOD || "credit_card";
const RUN_PAYMENT_MATRIX = String(env.RUN_PAYMENT_MATRIX || "false").toLowerCase() === "true";
const RUN_ADMIN_STORYBOARD = String(env.RUN_ADMIN_STORYBOARD || "false").toLowerCase() === "true";

const users = [
  "maya.ionescu@apex.example.test",
  "alex.chen@apex.example.test",
  "irina.marin@apex.example.test",
  "samuel.wright@apex.example.test",
  "daniel.rossi@apex.example.test",
];

const paymentMethods = RUN_PAYMENT_MATRIX
  ? ["credit_card", "apple_pay", "google_pay", "bank_transfer"]
  : [PAYMENT_METHOD];

function url(base: string, path: string, syntheticUser?: string): string {
  const value = new URL(path, base.replace(/\/$/, "") + "/");
  if (syntheticUser) value.searchParams.set("synthetic_user", syntheticUser);
  return value.toString();
}

async function screenshot(name: string): Promise<void> {
  await page.screenshot({ path: `${name}.png`, fullPage: true }).catch(() => undefined);
}

async function openShop(syntheticUser: string): Promise<void> {
  await page.goto(url(SHOP_URL, "/shop", syntheticUser), { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".product-card", { timeout: 45000 });
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => undefined);
  await screenshot("01-shop-catalog");
}

async function addTwoProducts(): Promise<void> {
  const addButtons = page.locator(".add-btn");
  await addButtons.first().click();
  await page.waitForSelector(".cart-item", { timeout: 20000 });
  if ((await addButtons.count()) > 1) {
    await addButtons.nth(1).click();
  }
}

async function fillBuyer(syntheticUser: string, method: string): Promise<void> {
  await page.fill('#checkoutForm [name="customer_name"]', syntheticUser.split("@")[0].replace(".", " "));
  await page.fill('#checkoutForm [name="customer_email"]', syntheticUser);
  await page.fill('#checkoutForm [name="company"]', "Apex Field Services");
  await page.fill('#checkoutForm [name="customer_phone"]', "+1 555 0184");
  await page.fill('#checkoutForm [name="shipping_address"]', "100 Demo Operations Way");
  await page.selectOption('#checkoutForm [name="payment_method"]', method);
  await page.fill('#checkoutForm [name="coupon_code"]', "DEMO-LAB").catch(() => undefined);

  if (method === "credit_card") {
    await page.fill('#checkoutForm [name="card_number"]', "4111111111111111");
    await page.fill('#checkoutForm [name="card_expiry"]', "12/30");
    await page.fill('#checkoutForm [name="card_cvv"]', "123");
    await page.fill('#checkoutForm [name="cardholder_name"]', "Maya Ionescu");
    await page.fill('#checkoutForm [name="billing_postal_code"]', "10001");
  }

  if (method === "apple_pay") {
    await page.getByTestId("apple-pay-button").click();
  }

  if (method === "google_pay") {
    await page.getByTestId("google-pay-button").click();
  }
}

async function placeOrder(syntheticUser: string, method: string): Promise<void> {
  await openShop(syntheticUser);
  await addTwoProducts();
  await fillBuyer(syntheticUser, method);
  await screenshot(`02-checkout-ready-${method}`);
  await page.click("#checkoutSubmitButton");
  await page.waitForFunction(
    () => {
      const text = document.querySelector("#checkoutStatus")?.textContent || "";
      return /Order #|Order placed|Order created|Checkout failed|Request failed|Payment failed|success|complete|declined/i.test(text);
    },
    null,
    { timeout: 90000 },
  );
  await screenshot(`03-checkout-result-${method}`);
}

async function submitSupportTicket(syntheticUser: string): Promise<void> {
  await page.goto(url(SHOP_URL, "/services", syntheticUser), { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#ticketForm", { timeout: 30000 });
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
  if (!ADMIN_PASSWORD || ADMIN_PASSWORD === "CHANGE_ME") return;

  await page.goto(url(ADMIN_URL, "/login"), { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#login-username", { timeout: 30000 });
  await page.fill("#login-username", ADMIN_USERNAME);
  await page.fill("#login-password", ADMIN_PASSWORD);
  await page.click('#login-form button[type="submit"]');
  await page.waitForURL((current: URL) => !current.pathname.startsWith("/login"), { timeout: 45000 });
  await page.goto(url(ADMIN_URL, "/settings"), { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#card-storyboard", { timeout: 45000 });
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

for (let index = 0; index < paymentMethods.length; index += 1) {
  await placeOrder(users[index % users.length], paymentMethods[index]);
}

await submitSupportTicket(users[0]);

if (RUN_ADMIN_STORYBOARD) {
  await runAdminStoryboard();
}

export {};
