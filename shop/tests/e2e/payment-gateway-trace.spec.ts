/**
 * Payment gateway trace coverage.
 *
 * Verifies the critical buying path emits trace-bearing browser calls, runs
 * the dedicated payment gateway emulator, records antifraud verification, and
 * links the resulting order to the signed-in buyer.
 */

import { test, expect, APIRequestContext, Page } from '@playwright/test';
import {
  SHOP_URL,
  INTEGRATION_TIMEOUT_MS,
  apiGet,
  apiPost,
  assertObject,
} from './helpers';

const SHOPPER_USERNAME = process.env.SHOP_E2E_USERNAME ?? 'shopper';
const SHOPPER_PASSWORD = process.env.SHOP_E2E_PASSWORD ?? '';

interface LoginResult {
  token: string;
  user: Record<string, unknown>;
}

async function loginViaApi(request: APIRequestContext): Promise<LoginResult> {
  const { status, body } = await apiPost(
    request,
    `${SHOP_URL}/api/auth/login`,
    { username: SHOPPER_USERNAME, password: SHOPPER_PASSWORD },
  );
  expect(status).toBe(200);
  const payload = assertObject(body);
  expect(payload.status).toBe('success');
  expect(typeof payload.token).toBe('string');
  return {
    token: payload.token as string,
    user: assertObject(payload.user),
  };
}

async function loginViaUi(page: Page): Promise<void> {
  await page.goto(`${SHOP_URL}/login`);
  await page.locator('[data-testid="login-username"]').fill(SHOPPER_USERNAME);
  await page.locator('[data-testid="login-password"]').fill(SHOPPER_PASSWORD);
  await page.locator('[data-testid="login-submit"]').click();
  await expect(page.locator('#result')).toContainText('Signed in as', { timeout: INTEGRATION_TIMEOUT_MS });
}

async function cheapestProductId(request: APIRequestContext): Promise<number> {
  const { status, body } = await apiGet(request, `${SHOP_URL}/api/shop/storefront`);
  expect(status).toBe(200);
  const storefront = assertObject(body);
  const products = (storefront.products as Array<Record<string, unknown>> | undefined) ?? [];
  const stocked = products
    .filter((product) => Number(product.stock ?? 0) > 0)
    .sort((a, b) => Number(a.price ?? 0) - Number(b.price ?? 0));
  expect(stocked.length).toBeGreaterThan(0);
  return Number(stocked[0].id);
}

function assertGatewayWorkflow(payment: Record<string, unknown>): Record<string, unknown> {
  const gateway = assertObject(payment.gateway);
  expect(gateway.gateway).toBe('octo-payment-gateway-emulator');
  expect(typeof gateway.request_id).toBe('string');
  expect((gateway.request_id as string).length).toBeGreaterThan(0);

  const steps = (gateway.steps as Array<Record<string, unknown>> | undefined) ?? [];
  const names = steps.map((step) => String(step.name));
  expect(names).toContain('gateway_payment_received');
  expect(names).toContain('verification_antifraud_request');
  expect(names).toContain('verification_antifraud_response');
  expect(names).toContain('processor_authorization_request');
  expect(names).toContain('processor_authorization_response');
  expect(names).toContain('network_authorization_routing');

  const verification = assertObject(gateway.verification);
  expect(verification.provider).toBe('octo-antifraud-verification-app');
  expect(typeof verification.decision).toBe('string');
  return gateway;
}

test.describe('Payment Gateway Trace', () => {
  test.beforeEach(() => {
    test.skip(!SHOPPER_PASSWORD, 'Set SHOP_E2E_PASSWORD to run authenticated payment gateway E2E tests.');
  });

  test('signed-in buyer completes Google Pay checkout with gateway and antifraud spans', async ({ page, request }) => {
    test.setTimeout(INTEGRATION_TIMEOUT_MS * 4);

    const productId = await cheapestProductId(request);
    await loginViaUi(page);
    await page.goto(`${SHOP_URL}/shop`);

    await expect(page.locator('[data-testid="buyer-auth-chip"]')).toContainText('Signed in');
    await page.locator(`[data-testid="add-to-cart-button"][data-id="${productId}"]`).click();
    await expect(page.locator('#cartChip')).toContainText(/1 item|[2-9] items/, { timeout: INTEGRATION_TIMEOUT_MS });

    await page.locator('[data-testid="checkout-name"]').fill('Trace Shopper');
    await page.locator('[data-testid="checkout-email"]').fill('trace.shopper@octo.local');
    await page.locator('[data-testid="checkout-company"]').fill('OCTO Trace Labs');
    await page.locator('[data-testid="checkout-address"]').fill('1 Observability Way, Trace City');
    await page.locator('[data-testid="payment-method"]').selectOption('google_pay');
    await page.locator('[data-testid="google-pay-button"]').click();

    const checkoutResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/api/shop/checkout') && response.request().method() === 'POST',
      { timeout: INTEGRATION_TIMEOUT_MS },
    );
    await page.locator('[data-testid="place-order-button"]').click();
    const checkoutResponse = await checkoutResponsePromise;
    expect(checkoutResponse.status()).toBe(200);
    const checkoutRequestHeaders = checkoutResponse.request().headers();
    expect(checkoutRequestHeaders.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
    expect(checkoutRequestHeaders['x-correlation-id']).toMatch(/^[0-9a-f]{32}$/);
    expect(checkoutRequestHeaders.authorization).toContain('Bearer ');
    const checkout = assertObject(await checkoutResponse.json());

    expect(checkout.status).toBe('order_placed');
    expect(checkout.payment_required).toBe(false);
    expect(checkout.payment_status).toBe('paid');
    expect(typeof checkout.trace_id).toBe('string');
    expect((checkout.trace_id as string).length).toBe(32);

    const payment = assertObject(checkout.payment);
    expect(payment.status).toBe('authorized');
    expect(payment.method).toBe('google_pay');
    expect(payment.wallet_type).toBe('google_pay');
    assertGatewayWorkflow(payment);

    await expect(page.locator('[data-testid="checkout-status"]')).toContainText('Order paid', {
      timeout: INTEGRATION_TIMEOUT_MS,
    });

    const token = await page.evaluate(() => localStorage.getItem('octo-auth-token') || '');
    expect(token.length).toBeGreaterThan(0);
    const { status, body } = await apiGet(
      request,
      `${SHOP_URL}/api/orders?limit=25`,
      { Authorization: `Bearer ${token}` },
    );
    expect(status).toBe(200);
    const ordersBody = assertObject(body);
    const orders = (ordersBody.orders as Array<Record<string, unknown>> | undefined) ?? [];
    const created = orders.find((order) => Number(order.id) === Number(checkout.order_id));
    expect(created).toBeTruthy();
    expect(created?.payment_status).toBe('paid');
    expect(Boolean(created?.payment_required)).toBe(false);
    expect(Number(created?.user_id)).toBe(Number(assertObject(checkout.authenticated_user).id));
  });

  test('declined Visa card keeps the order payment-required and records antifraud verification', async ({ request }) => {
    test.setTimeout(INTEGRATION_TIMEOUT_MS * 3);

    const { token } = await loginViaApi(request);
    const productId = await cheapestProductId(request);
    const idempotencyKey = `e2e-decline-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const { status, body } = await apiPost(
      request,
      `${SHOP_URL}/api/shop/checkout`,
      {
        session_id: `e2e-${Date.now()}`,
        checkout_idempotency_key: idempotencyKey,
        customer_name: 'Decline Shopper',
        customer_email: 'decline.shopper@octo.local',
        company: 'OCTO Trace Labs',
        shipping_address: '2 Payment Required Ave, Trace City',
        payment_method: 'credit_card',
        items: [{ product_id: productId, quantity: 1 }],
        payment_details: {
          card: {
            number: '4000000000000002',
            expiry: '12/30',
            cvv: '123',
            cardholder_name: 'Decline Shopper',
            billing_postal_code: '10001',
          },
        },
      },
      { Authorization: `Bearer ${token}` },
    );
    expect(status).toBe(200);
    const checkout = assertObject(body);
    expect(checkout.status).toBe('order_placed');
    expect(checkout.payment_required).toBe(true);
    expect(checkout.payment_status).toBe('failed');
    expect(checkout.order_status).toBe('payment_pending');

    const payment = assertObject(checkout.payment);
    expect(payment.status).toBe('declined');
    expect(payment.risk_reasons).toContain('issuer_decline_test_card');
    const gateway = assertGatewayWorkflow(payment);
    const verification = assertObject(gateway.verification);
    if (verification.status === 'ok') {
      expect(verification.decision).toBe('declined');
      expect(payment.decision_source).toBe('java-antifraud-verification-app');
    } else {
      expect(['internal-antifraud', 'java-antifraud-verification-app']).toContain(payment.decision_source);
    }
    expect(assertObject(gateway.final_step).status).toBe('declined');
  });
});
