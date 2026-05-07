/**
 * Journey: catalog-to-checkout.
 *
 * Simulates a real shopper:
 *   1. Land on home page.
 *   2. Browse to the drones category.
 *   3. View a product.
 *   4. Add to cart.
 *   5. Open cart.
 *   6. Proceed to checkout.
 *   7. Submit order (may succeed or fail based on test data).
 *
 * Every step is tagged with X-Run-Id so downstream APM traces group
 * under the same run.
 */

import type { BrowserContext, Page } from "playwright";
import { syntheticIdentityHeaders, type BrowserRunnerConfig } from "../src/config.js";

export async function runJourney(
  context: BrowserContext,
  config: BrowserRunnerConfig,
): Promise<void> {
  const page = await context.newPage();

  // Tag every request from this page with the run_id so backend traces
  // carry `request_headers['x-run-id']` as a filterable span attribute.
  await page.setExtraHTTPHeaders({
    "X-Run-Id": config.runId,
    "X-Operator": config.operator,
    "X-Workflow-Id": `browser.${config.journey}`,
    ...syntheticIdentityHeaders(config.selectedSyntheticUser),
  });

  await page.goto(config.shopBaseUrl, { timeout: config.timeoutPerActionMs });
  await page.waitForLoadState("domcontentloaded");

  // Click into drones category if a nav link exists; otherwise hit the
  // API directly so at least a product list is in the DOM.
  const dronesLink = page.locator('a:has-text("Drones"), a[href*="category=drones"]').first();
  if (await dronesLink.count()) {
    await dronesLink.click();
    await page.waitForLoadState("networkidle", { timeout: config.timeoutPerActionMs });
  }

  // First visible product card
  const firstProduct = page.locator('[data-testid="product-card"], .product-card').first();
  if (await firstProduct.count()) {
    await firstProduct.click();
    await page.waitForLoadState("domcontentloaded", { timeout: config.timeoutPerActionMs });
  }

  // Add to cart
  const addToCartBtn = page.locator(
    '[data-testid="add-to-cart"], button:has-text("Add to Cart"), button:has-text("Add to cart")',
  ).first();
  if (await addToCartBtn.count()) {
    await addToCartBtn.click();
  } else {
    // Fallback — direct API add so the journey still produces signal
    await page.request.post(`${config.shopBaseUrl}/api/cart`, {
      data: { product_id: 1, quantity: 1 },
      headers: { "X-Run-Id": config.runId, ...syntheticIdentityHeaders(config.selectedSyntheticUser) },
    });
  }

  // Open cart drawer
  const cartIcon = page.locator('[data-testid="cart-icon"], a[href*="/cart"]').first();
  if (await cartIcon.count()) {
    await cartIcon.click();
    await page.waitForLoadState("domcontentloaded", { timeout: config.timeoutPerActionMs });
  }

  // Checkout through the real form when the current storefront exposes it.
  const user = config.selectedSyntheticUser ?? {
    displayName: "Synthetic Buyer",
    email: "synthetic.buyer@apex.example.test",
    username: "synthetic.buyer",
    domain: "apex.example.test",
  };
  const checkoutForm = page.locator("#checkoutForm").first();
  if (await checkoutForm.count()) {
    await page.locator('#checkoutForm [name="customer_name"]').fill(user.displayName);
    await page.locator('#checkoutForm [name="customer_email"]').fill(user.email);
    await page.locator('#checkoutForm [name="company"]').fill("Apex Synthetic Operations");
    await page.locator('#checkoutForm [name="customer_phone"]').fill("+1-555-0100");
    await page.locator('#checkoutForm [name="shipping_address"]').fill("Synthetic operations address");
    await page.locator('#checkoutForm [name="payment_method"]').selectOption("credit_card");
    await page.locator('#checkoutForm [name="card_number"]').fill("4111 1111 1111 1111");
    await page.locator('#checkoutForm [name="card_expiry"]').fill("12/30");
    await page.locator('#checkoutForm [name="card_cvv"]').fill("123");
    await page.locator('#checkoutForm [name="cardholder_name"]').fill(user.displayName);
    await page.locator('#checkoutForm [name="billing_postal_code"]').fill("10001");
    await Promise.all([
      page.waitForResponse(
        (response) => response.url().includes("/api/shop/checkout"),
        { timeout: config.timeoutPerActionMs },
      ).catch(() => undefined),
      page.locator("#checkoutSubmitButton").click(),
    ]);
  } else {
    // Synthetic checkout via API — the primary purpose is APM signal
    await page.request.post(`${config.shopBaseUrl}/api/shop/checkout`, {
      data: {
        customer_name: user.displayName,
        customer_email: user.email,
        company: "Apex Synthetic Operations",
        customer_phone: "+1-555-0100",
        shipping_address: "Synthetic operations address",
        payment_method: "credit_card",
        payment_details: {
          card: {
            number: "4111 1111 1111 1111",
            expiry: "12/30",
            cvv: "123",
            cardholder_name: user.displayName,
            billing_postal_code: "10001",
            brand: "visa",
          },
        },
        items: [{ product_id: 1, quantity: 1 }],
      },
      headers: { "X-Run-Id": config.runId, ...syntheticIdentityHeaders(config.selectedSyntheticUser) },
    });
  }

  // Screenshot if configured
  if (config.captureScreenshots) {
    await page.screenshot({
      path: `${config.artifactsDir}/catalog-to-checkout-${config.runId}.png`,
      fullPage: true,
    });
  }

  await page.close();
}
