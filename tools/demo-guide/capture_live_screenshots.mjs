import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const root = path.resolve(new URL("../..", import.meta.url).pathname);
const outDir = path.join(root, "site/assets/demo/private-live");
const require = createRequire(import.meta.url);

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  ({ chromium } = require(path.join(root, "services/browser-runner/node_modules/playwright")));
}

const shopBase = process.env.OCTO_LIVE_SHOP_URL || "https://shop.example.test";
const adminBase = process.env.OCTO_LIVE_ADMIN_URL || "https://admin.example.test";
const adminUsername = process.env.BOOTSTRAP_ADMIN_USERNAME || process.env.OCTO_ADMIN_USERNAME;
const adminPassword = process.env.BOOTSTRAP_ADMIN_PASSWORD || process.env.OCTO_ADMIN_PASSWORD;

const syntheticUser = process.env.OCTO_LIVE_SYNTHETIC_USER || "maya.ionescu@apex.example.test";
const checkoutPerson = {
  name: "Maya Ionescu",
  email: syntheticUser,
  company: "Apex Field Services",
  phone: "+1 555 0184",
  address: "100 Drone Ops Way, Phoenix, AZ",
};

async function ensureOutDir() {
  await fs.mkdir(outDir, { recursive: true });
}

async function screenshot(page, name, options = {}) {
  await page.screenshot({
    path: path.join(outDir, name),
    fullPage: options.fullPage ?? false,
    animations: "disabled",
  });
}

async function elementScreenshot(page, selector, name) {
  const locator = page.locator(selector);
  await locator.scrollIntoViewIfNeeded();
  await locator.screenshot({
    path: path.join(outDir, name),
    animations: "disabled",
  });
}

async function openShop(page) {
  const url = new URL("/shop", shopBase);
  url.searchParams.set("synthetic_user", syntheticUser);
  await page.goto(url.toString(), { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".product-card", { timeout: 45000 });
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
}

async function runShopCheckout(page) {
  await openShop(page);
  await screenshot(page, "shop-catalog-live.png");

  const addButtons = page.locator(".add-btn");
  await addButtons.nth(0).click();
  await page.waitForSelector(".cart-item", { timeout: 20000 });
  await addButtons.nth(1).click().catch(() => {});
  await page.waitForTimeout(1500);

  await page.fill('#checkoutForm [name="customer_name"]', checkoutPerson.name);
  await page.fill('#checkoutForm [name="customer_email"]', checkoutPerson.email);
  await page.fill('#checkoutForm [name="company"]', checkoutPerson.company);
  await page.fill('#checkoutForm [name="customer_phone"]', checkoutPerson.phone);
  await page.fill('#checkoutForm [name="shipping_address"]', checkoutPerson.address);
  await page.selectOption('#checkoutForm [name="payment_method"]', "credit_card");
  await page.fill('#checkoutForm [name="coupon_code"]', "DEMO-LAB");

  await elementScreenshot(page, "#cartPanel", "shop-checkout-ready-live.png");
  await page.click("#checkoutSubmitButton");
  await page.waitForFunction(
    () => {
      const text = document.querySelector("#checkoutStatus")?.textContent || "";
      return /Order #|Checkout failed|Request failed/i.test(text);
    },
    null,
    { timeout: 45000 },
  );
  await page.waitForFunction(
    () => !document.querySelector("#checkoutSubmitButton")?.disabled,
    null,
    { timeout: 45000 },
  ).catch(() => {});
  await elementScreenshot(page, "#cartPanel", "shop-order-complete-live.png");
}

async function runSupportTicket(page) {
  const url = new URL("/services", shopBase);
  url.searchParams.set("synthetic_user", syntheticUser);
  await page.goto(url.toString(), { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#ticketForm", { timeout: 30000 });
  await page.waitForSelector(".product-card", { timeout: 30000 }).catch(() => {});

  const bookButton = page.locator("button", { hasText: "Book" }).first();
  if (await bookButton.count()) {
    await bookButton.click();
  }
  const ticketTitle = await page.locator("#ticketTitle").inputValue().catch(() => "");
  if (!ticketTitle) {
    await page.fill("#ticketTitle", "Request: Drone support lab");
    await page.fill("#ticketContent", "Need help validating post-purchase telemetry and Java app-server traces.");
    await page.selectOption("#ticketPriority", "low");
  }
  await elementScreenshot(page, "#ticketForm", "shop-support-ticket-ready-live.png");
  await page.locator("#ticketForm button[type='submit']").click();
  await page.waitForFunction(
    () => /Ticket successfully created|Error:/i.test(document.querySelector("#ticketFormStatus")?.textContent || ""),
    null,
    { timeout: 30000 },
  );
  const firstTicket = page.locator("#ticketList .crm-customer").first();
  if (await firstTicket.count()) {
    await firstTicket.scrollIntoViewIfNeeded();
    await firstTicket.screenshot({
      path: path.join(outDir, "shop-support-ticket-submitted-live.png"),
      animations: "disabled",
    });
  } else {
    await elementScreenshot(page, "#ticketList", "shop-support-ticket-submitted-live.png");
  }
}

async function loginAdmin(page) {
  if (!adminUsername || !adminPassword) {
    throw new Error("Missing admin credentials in environment.");
  }
  await page.goto(new URL("/login", adminBase).toString(), { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#login-username", { timeout: 30000 });
  await screenshot(page, "admin-login-live.png");
  await page.fill("#login-username", adminUsername);
  await page.fill("#login-password", adminPassword);
  await page.click('#login-form button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 45000 });
}

async function waitOutputChanged(page, selector, initialText, timeout = 90000) {
  await page.waitForFunction(
    ({ selector: target, initial }) => {
      const text = document.querySelector(target)?.textContent || "";
      return text && text !== initial && !/running|proxying|firing/i.test(text);
    },
    { selector, initial: initialText },
    { timeout },
  ).catch(() => {});
}

async function clickCardAction(page, cardSelector, buttonText, outputSelector, screenshotName, timeout) {
  if ((await page.locator(cardSelector).count()) === 0) {
    return false;
  }
  const initialText = await page.locator(outputSelector).textContent().catch(() => "");
  await page.locator(cardSelector).scrollIntoViewIfNeeded();
  await page.locator(`${cardSelector} button`, { hasText: buttonText }).click();
  await waitOutputChanged(page, outputSelector, initialText || "", timeout);
  await elementScreenshot(page, cardSelector, screenshotName);
  return true;
}

async function runAdminLab(page) {
  await loginAdmin(page);
  await page.goto(new URL("/settings", adminBase).toString(), { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#card-storyboard", { timeout: 45000 });
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await screenshot(page, "admin-simulation-live.png", { fullPage: true });

  await clickCardAction(page, "#card-drone-shop", "Java Health", "#drone-output", "admin-java-apm-health-live.png", 45000);
  await clickCardAction(page, "#card-storyboard", "Run Story", "#story-output", "admin-storyboard-output-live.png", 90000);
  await clickCardAction(page, "#card-synthetic-users", "Generate Users", "#synthetic-output", "admin-synthetic-users-output-live.png", 90000);
  await clickCardAction(page, "#card-attack-lab", "Generate Attack", "#attack-output", "admin-attack-lab-output-live.png", 120000);
  await clickCardAction(page, "#card-availability", "Show Global Monitor Plan", "#availability-output", "admin-availability-plan-live.png", 30000);

  await page.goto(new URL("/observability", adminBase).toString(), { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".card", { timeout: 45000 });
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.evaluate(() => {
    for (const element of Array.from(document.querySelectorAll("body *"))) {
      if (element.children.length === 0 && /ocid1\./i.test(element.textContent || "")) {
        element.textContent = "redacted in guide asset";
      }
    }
  });
  await screenshot(page, "admin-360-monitoring-live.png", { fullPage: true });
}

async function main() {
  await ensureOutDir();
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1,
      locale: "en-US",
    });
    const page = await context.newPage();
    page.setDefaultTimeout(45000);

    await runShopCheckout(page);
    await runSupportTicket(page);
    await runAdminLab(page);
  } finally {
    await browser.close();
  }
  console.log(`wrote live screenshots to ${path.relative(root, outDir)}`);
}

main().catch(async (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
