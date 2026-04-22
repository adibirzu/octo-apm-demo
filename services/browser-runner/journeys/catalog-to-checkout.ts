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
import type { BrowserRunnerConfig } from "../src/config.js";

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
    '[data-testid="add-to-cart"], button:has-text("Add to cart")',
  ).first();
  if (await addToCartBtn.count()) {
    await addToCartBtn.click();
  } else {
    // Fallback — direct API add so the journey still produces signal
    await page.request.post(`${config.shopBaseUrl}/api/cart`, {
      data: { product_id: 1, quantity: 1 },
      headers: { "X-Run-Id": config.runId },
    });
  }

  // Open cart drawer
  const cartIcon = page.locator('[data-testid="cart-icon"], a[href*="/cart"]').first();
  if (await cartIcon.count()) {
    await cartIcon.click();
    await page.waitForLoadState("domcontentloaded", { timeout: config.timeoutPerActionMs });
  }

  // Checkout
  const checkoutBtn = page.locator(
    '[data-testid="checkout"], button:has-text("Checkout")',
  ).first();
  if (await checkoutBtn.count()) {
    await checkoutBtn.click();
    await page.waitForLoadState("domcontentloaded", { timeout: config.timeoutPerActionMs });
  } else {
    // Synthetic checkout via API — the primary purpose is APM signal
    await page.request.post(`${config.shopBaseUrl}/api/orders`, {
      data: {
        customer_id: 1,
        items: [{ product_id: 1, quantity: 1, unit_price: 49.99 }],
      },
      headers: { "X-Run-Id": config.runId },
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
