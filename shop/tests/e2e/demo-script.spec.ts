/**
 * OCTO live demo script.
 *
 * Drives the shopper journey, support-ticket flow, and CRM/admin simulation
 * controls used by the OCI Observability workshop.
 *
 * Env vars:
 *   OCTO_LIVE_SHOP_URL    defaults to http://localhost:8080
 *   OCTO_LIVE_ADMIN_URL   defaults to http://localhost:8081
 *   OCTO_ADMIN_USERNAME   defaults to admin
 *   OCTO_ADMIN_PASSWORD   required for admin-console controls
 *   OCTO_INTERNAL_SERVICE_KEY optional; enables payment-gateway DB drilldown checks
 */

import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { apiGet, assertObject } from './helpers';

const SHOP_BASE_URL =
  process.env.OCTO_LIVE_SHOP_URL ?? process.env.SHOP_URL ?? 'http://localhost:8080';
const ADMIN_BASE_URL =
  process.env.OCTO_LIVE_ADMIN_URL ?? process.env.CRM_URL ?? 'http://localhost:8081';
const ADMIN_USERNAME = process.env.OCTO_ADMIN_USERNAME ?? 'admin';
const ADMIN_PASSWORD = process.env.OCTO_ADMIN_PASSWORD ?? '';
const INTERNAL_SERVICE_KEY = process.env.OCTO_INTERNAL_SERVICE_KEY ?? process.env.INTERNAL_SERVICE_KEY ?? '';

const DEMO_TIMEOUT_MS = SHOP_BASE_URL.startsWith('https://') ? 45_000 : 15_000;

type CardPaymentScenario = {
  kind: 'card';
  label: string;
  userEmail: string;
  customerName: string;
  persona: string;
  company: string;
  quantity: 2 | 3;
  cardNumber: string;
  expiry: string;
  cvv: string;
  postalCode: string;
  expectedPaymentStatus: 'paid' | 'failed';
};

type WalletPaymentScenario = {
  kind: 'wallet';
  label: string;
  userEmail: string;
  customerName: string;
  persona: string;
  company: string;
  quantity: 2 | 3;
  method: 'apple_pay' | 'google_pay';
  expectedPaymentStatus: 'paid';
};

type ManualPaymentScenario = {
  kind: 'manual';
  label: string;
  userEmail: string;
  customerName: string;
  persona: string;
  company: string;
  quantity: 2 | 3;
  method: 'bank_transfer';
};

type PaymentScenario = CardPaymentScenario | WalletPaymentScenario | ManualPaymentScenario;

type AdminSimulationResult = {
  status: number;
  body: unknown;
};

const PAYMENT_SCENARIOS: PaymentScenario[] = [
  {
    kind: 'card',
    label: 'alex-fleet-mastercard-approved',
    userEmail: 'alex.chen@apex.example.test',
    customerName: 'Alex Chen',
    persona: 'Fleet operations buyer',
    company: 'Apex Fleet Operations',
    quantity: 2,
    cardNumber: '5555555555554444',
    expiry: '12/30',
    cvv: '321',
    postalCode: '10001',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'maya-field-visa-approved',
    userEmail: 'maya.ionescu@apex.example.test',
    customerName: 'Maya Ionescu',
    persona: 'Field services buyer',
    company: 'Apex Field Services',
    quantity: 3,
    cardNumber: '4111111111111111',
    expiry: '12/30',
    cvv: '123',
    postalCode: '10001',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'nora-energy-issuer-decline',
    userEmail: 'nora.patel@apex.example.test',
    customerName: 'Nora Patel',
    persona: 'Energy survey buyer',
    company: 'Apex Energy Survey',
    quantity: 2,
    cardNumber: '4000000000000002',
    expiry: '12/30',
    cvv: '123',
    postalCode: '10001',
    expectedPaymentStatus: 'failed',
  },
  {
    kind: 'manual',
    label: 'daniel-infrastructure-bank-transfer',
    userEmail: 'daniel.rossi@apex.example.test',
    customerName: 'Daniel Rossi',
    persona: 'Infrastructure buyer',
    company: 'Apex Infrastructure',
    quantity: 3,
    method: 'bank_transfer',
  },
  {
    kind: 'wallet',
    label: 'irina-public-safety-apple-pay',
    userEmail: 'irina.marin@apex.example.test',
    customerName: 'Irina Marin',
    persona: 'Public safety buyer',
    company: 'Apex Public Safety',
    quantity: 2,
    method: 'apple_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'wallet',
    label: 'samuel-logistics-google-pay',
    userEmail: 'samuel.wright@apex.example.test',
    customerName: 'Samuel Wright',
    persona: 'Logistics buyer',
    company: 'Apex Logistics',
    quantity: 3,
    method: 'google_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'elena-agriculture-visa-approved',
    userEmail: 'elena.garcia@apex.example.test',
    customerName: 'Elena Garcia',
    persona: 'Agriculture buyer',
    company: 'Apex Agriculture',
    quantity: 2,
    cardNumber: '4111111111111111',
    expiry: '12/30',
    cvv: '123',
    postalCode: '10001',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'noah-inspection-mastercard-approved',
    userEmail: 'noah.kim@apex.example.test',
    customerName: 'Noah Kim',
    persona: 'Inspection buyer',
    company: 'Apex Inspection Services',
    quantity: 3,
    cardNumber: '5555555555554444',
    expiry: '12/30',
    cvv: '321',
    postalCode: '10001',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'wallet',
    label: 'sofia-rail-apple-pay',
    userEmail: 'sofia.andersen@apex.example.test',
    customerName: 'Sofia Andersen',
    persona: 'Rail systems buyer',
    company: 'Apex Rail Systems',
    quantity: 2,
    method: 'apple_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'wallet',
    label: 'matei-utilities-google-pay',
    userEmail: 'matei.popa@apex.example.test',
    customerName: 'Matei Popa',
    persona: 'Utilities buyer',
    company: 'Apex Utilities',
    quantity: 3,
    method: 'google_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'lina-emergency-visa-approved',
    userEmail: 'lina.hoffman@apex.example.test',
    customerName: 'Lina Hoffman',
    persona: 'Emergency response buyer',
    company: 'Apex Emergency Response',
    quantity: 2,
    cardNumber: '4111111111111111',
    expiry: '12/30',
    cvv: '123',
    postalCode: '10001',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'manual',
    label: 'omar-maritime-bank-transfer',
    userEmail: 'omar.saleh@apex.example.test',
    customerName: 'Omar Saleh',
    persona: 'Maritime buyer',
    company: 'Apex Maritime',
    quantity: 3,
    method: 'bank_transfer',
  },
];

function uniqueId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

async function apiJson(request: APIRequestContext, url: string): Promise<Record<string, unknown>> {
  const response = await request.get(url, { headers: { Accept: 'application/json' } });
  expect(response.status(), `${url} should return 200`).toBe(200);
  return assertObject(await response.json());
}

async function stockedProductIds(request: APIRequestContext, quantity: number): Promise<number[]> {
  const storefront = await apiJson(request, `${SHOP_BASE_URL}/api/shop/storefront`);
  const products = (storefront.products as Array<Record<string, unknown>> | undefined) ?? [];
  const stockedProducts = products
    .filter((product) => Number(product.stock ?? 0) > 0)
    .sort((a, b) => {
      const stockDelta = Number(b.stock ?? 0) - Number(a.stock ?? 0);
      return stockDelta || Number(a.price ?? 0) - Number(b.price ?? 0);
    });

  const totalStock = stockedProducts.reduce((sum, product) => sum + Number(product.stock ?? 0), 0);
  expect(totalStock, `storefront should expose ${quantity} in-stock drone units`).toBeGreaterThanOrEqual(quantity);

  const ids = stockedProducts.reduce<number[]>((selectedIds, product) => {
    if (selectedIds.length >= quantity) return selectedIds;
    const copies = Math.min(Number(product.stock ?? 0), quantity - selectedIds.length);
    return [
      ...selectedIds,
      ...Array.from({ length: copies }, () => Number(product.id)),
    ];
  }, []);
  expect(ids.length).toBe(quantity);
  return ids;
}

async function prepareFreshShopSession(page: Page, scenario: PaymentScenario): Promise<string> {
  const sessionId = uniqueId(`demo-${scenario.label}`);

  await page.goto(SHOP_BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ({ nextSessionId, syntheticUserEmail }) => {
      localStorage.setItem('octo-session-id', nextSessionId);
      localStorage.setItem('octoSyntheticUserEmail', syntheticUserEmail);
    },
    { nextSessionId: sessionId, syntheticUserEmail: scenario.userEmail },
  );

  await page.goto(`${SHOP_BASE_URL}/shop?synthetic_user=${encodeURIComponent(scenario.userEmail)}`);
  await expect(page.locator('[data-testid="checkout-form"]')).toBeVisible({ timeout: DEMO_TIMEOUT_MS });
  await expect(page.locator('[data-testid="add-to-cart-button"]').first()).toBeVisible({
    timeout: DEMO_TIMEOUT_MS,
  });

  return sessionId;
}

async function addProductsToCart(page: Page, productIds: number[]): Promise<void> {
  for (const productId of productIds) {
    const productButton = page.locator(`[data-testid="add-to-cart-button"][data-id="${productId}"]`);
    const addButton = (await productButton.count()) > 0
      ? productButton.first()
      : page.locator('[data-testid="add-to-cart-button"]').first();
    await addButton.click();
    await expect(page.locator('#cartChip')).toContainText(/item/, { timeout: DEMO_TIMEOUT_MS });
  }
  await expect(page.locator('#cartChip')).toHaveText(
    new RegExp(`${productIds.length} items?`),
    { timeout: DEMO_TIMEOUT_MS },
  );
}

async function fillBuyerDetails(page: Page, scenario: PaymentScenario): Promise<void> {
  await page.locator('[data-testid="checkout-name"]').fill(scenario.customerName);
  await page.locator('[data-testid="checkout-email"]').fill(scenario.userEmail);
  await page.locator('[data-testid="checkout-company"]').fill(scenario.company);
  await page.locator('[data-testid="checkout-phone"]').fill('+1 555 0184');
  await page.locator('[data-testid="checkout-address"]').fill(`100 Demo Operations Way - ${scenario.persona}`);
}

async function choosePaymentMethod(page: Page, scenario: PaymentScenario): Promise<void> {
  if (scenario.kind === 'card') {
    await page.locator('[data-testid="payment-method"]').selectOption('credit_card');
    await page.locator('[data-testid="card-number"]').fill(scenario.cardNumber);
    await page.locator('[data-testid="card-expiry"]').fill(scenario.expiry);
    await page.locator('[data-testid="card-cvv"]').fill(scenario.cvv);
    await page.locator('[data-testid="cardholder-name"]').fill(scenario.customerName);
    await page.locator('[data-testid="billing-postal-code"]').fill(scenario.postalCode);
    return;
  }

  if (scenario.kind === 'wallet') {
    await page.locator('[data-testid="payment-method"]').selectOption(scenario.method);
    const buttonTestId = scenario.method === 'apple_pay' ? 'apple-pay-button' : 'google-pay-button';
    await page.locator(`[data-testid="${buttonTestId}"]`).click();
    return;
  }

  await page.locator('[data-testid="payment-method"]').selectOption(scenario.method);
}

function gatewayStepNames(gateway: Record<string, unknown>): string[] {
  const steps = (gateway.steps as Array<Record<string, unknown>> | undefined) ?? [];
  expect(steps.length, 'payment gateway should return detailed steps').toBeGreaterThan(5);
  return steps.map((step) => String(step.name ?? ''));
}

function assertSafePaymentTelemetry(
  checkout: Record<string, unknown>,
  scenario: PaymentScenario,
): { gatewayRequestId: string; traceId: string } | null {
  expect(typeof checkout.trace_id).toBe('string');
  const traceId = checkout.trace_id as string;
  expect(traceId).toMatch(/^[0-9a-f]{32}$/);

  if (scenario.kind === 'manual') {
    expect(checkout.payment_status).toBe('pending');
    return null;
  }

  const payment = assertObject(checkout.payment);
  expect(payment.status).toBe(scenario.expectedPaymentStatus === 'paid' ? 'authorized' : 'declined');
  expect(payment.method).toBe(scenario.kind === 'card' ? 'credit_card' : scenario.method);
  expect(typeof payment.provider).toBe('string');
  expect((payment.provider as string).length).toBeGreaterThan(0);
  expect(typeof payment.decision_source).toBe('string');
  expect((payment.decision_source as string).length).toBeGreaterThan(0);
  expect(Number(payment.risk_score)).not.toBeNaN();

  if (scenario.kind === 'card') {
    expect(typeof payment.card_brand).toBe('string');
    expect(payment.card_last4).toBe(scenario.cardNumber.slice(-4));
    const serialized = JSON.stringify(payment);
    expect(serialized).not.toContain(scenario.cardNumber);
    expect(serialized).not.toContain(scenario.cvv);
  } else {
    expect(payment.wallet_type).toBe(scenario.method);
  }

  const gateway = assertObject(payment.gateway);
  expect(gateway.gateway).toBe('octo-payment-gateway-emulator');
  expect(gateway.provider).toBe('cybersource-compatible-simulator');
  expect(typeof gateway.request_id).toBe('string');
  const gatewayRequestId = gateway.request_id as string;
  expect(gatewayRequestId.length).toBeGreaterThan(0);

  const names = gatewayStepNames(gateway);
  expect(names).toContain('gateway_payment_received');
  expect(names).toContain('internal_antifraud_screening');
  expect(names).toContain('verification_antifraud_request');
  expect(names).toContain('verification_antifraud_response');
  expect(names).toContain('processor_authorization_request');
  expect(names).toContain('network_authorization_routing');

  if (scenario.kind === 'card') {
    expect(names).toContain('gateway_card_tokenization');
    expect(names).toContain('card_network_routing');
  } else {
    expect(names).toContain('wallet_token_received');
    expect(names).toContain('gateway_token_decryption');
    expect(names).toContain('network_token_cryptogram_validation');
  }

  const verification = assertObject(gateway.verification);
  expect(verification.provider).toBe('octo-antifraud-verification-app');
  expect(typeof verification.decision).toBe('string');
  const finalStep = assertObject(gateway.final_step);
  expect(finalStep.name).toBe('merchant_authorization_result');
  expect(['authorized', 'declined', 'completed']).toContain(String(finalStep.status));

  return { gatewayRequestId, traceId };
}

async function verifyPaymentGatewayEvents(
  request: APIRequestContext,
  gatewayRequestId: string,
): Promise<void> {
  if (!INTERNAL_SERVICE_KEY) {
    return;
  }

  const { status, body } = await apiGet(
    request,
    `${SHOP_BASE_URL}/api/observability/payment-gateway/events?gateway_request_id=${encodeURIComponent(gatewayRequestId)}&limit=50`,
    { 'X-Internal-Service-Key': INTERNAL_SERVICE_KEY },
  );
  expect(status).toBe(200);
  const response = assertObject(body);
  const summary = assertObject(response.summary);
  expect(Number(summary.event_count)).toBeGreaterThan(0);
  expect(summary.gateway_request_ids).toEqual(expect.arrayContaining([gatewayRequestId]));
}

async function runCheckout(
  page: Page,
  request: APIRequestContext,
  scenario: PaymentScenario,
): Promise<Record<string, unknown>> {
  await fillBuyerDetails(page, scenario);
  await choosePaymentMethod(page, scenario);

  const checkoutResponsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/shop/checkout') && response.request().method() === 'POST',
    { timeout: DEMO_TIMEOUT_MS },
  );

  await page.locator('[data-testid="place-order-button"]').click();
  const checkoutResponse = await checkoutResponsePromise;
  expect(checkoutResponse.status()).toBe(200);

  const checkout = assertObject(await checkoutResponse.json());
  expect(checkout.status).toBe('order_placed');
  expect(typeof checkout.order_id).toBe('number');
  expect(typeof checkout.trace_id).toBe('string');

  await expect(page.locator('[data-testid="checkout-status"]')).toContainText('Order #', {
    timeout: DEMO_TIMEOUT_MS,
  });

  if (scenario.kind === 'card' || scenario.kind === 'wallet') {
    expect(checkout.payment_status).toBe(scenario.expectedPaymentStatus);
  }

  const paymentCorrelation = assertSafePaymentTelemetry(checkout, scenario);
  if (paymentCorrelation) {
    await verifyPaymentGatewayEvents(request, paymentCorrelation.gatewayRequestId);
  }

  return checkout;
}

async function createSupportTicket(page: Page): Promise<Record<string, unknown>> {
  await page.goto(`${SHOP_BASE_URL}/services?synthetic_user=maya.ionescu@apex.example.test`);
  await expect(page.locator('#ticketForm')).toBeVisible({ timeout: DEMO_TIMEOUT_MS });
  await expect(page.getByRole('button', { name: 'Book' }).first()).toBeVisible({ timeout: DEMO_TIMEOUT_MS });

  await page.getByRole('button', { name: 'Book' }).first().click();
  await page.locator('#ticketTitle').fill('Telemetry validation for demo order');
  await page.locator('#ticketPriority').selectOption('high');
  await page.locator('#ticketContent').fill(
    'Need telemetry validation for a demo order. Please correlate browser session, checkout span, payment gateway, and support ticket activity.',
  );

  const ticketResponsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/services/tickets') && response.request().method() === 'POST',
    { timeout: DEMO_TIMEOUT_MS },
  );
  await page.getByRole('button', { name: 'Submit Ticket' }).click();

  const ticketResponse = await ticketResponsePromise;
  expect([200, 201]).toContain(ticketResponse.status());
  return assertObject(await ticketResponse.json());
}

async function loginToAdmin(page: Page): Promise<void> {
  await page.goto(`${ADMIN_BASE_URL}/login`);
  await page.locator('#login-username').fill(ADMIN_USERNAME);
  await page.locator('#login-password').fill(ADMIN_PASSWORD);

  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login', { timeout: DEMO_TIMEOUT_MS }),
    page.getByRole('button', { name: 'Login' }).click(),
  ]);

  const session = await page.evaluate(async () => {
    const response = await fetch('/api/auth/session', { headers: { Accept: 'application/json' } });
    return {
      status: response.status,
      body: await response.json(),
    };
  });

  expect(session.status).toBe(200);
  expect(assertObject(session.body).authenticated).toBe(true);
}

async function postAdminSimulation(
  page: Page,
  action: string,
  body: Record<string, unknown>,
  method: 'GET' | 'POST' = 'POST',
): Promise<AdminSimulationResult> {
  return page.evaluate(
    async ({ nextAction, nextBody, nextMethod }) => {
      const response = await fetch(`/api/simulate/drone-shop/${nextAction}`, {
        method: nextMethod,
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: nextMethod === 'POST' ? JSON.stringify(nextBody) : undefined,
      });

      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        payload = { raw: await response.text() };
      }

      return {
        status: response.status,
        body: payload,
      };
    },
    { nextAction: action, nextBody: body, nextMethod: method },
  );
}

function expectProxiedAdminResult(result: AdminSimulationResult, action: string): Record<string, unknown> {
  expect(result.status, `${action} CRM proxy HTTP status`).toBe(200);

  const proxy = assertObject(result.body);
  expect(proxy.status, `${action} should be proxied`).toBe('proxied');
  expect(proxy.upstream_status, `${action} upstream status`).toBe(200);

  return assertObject(proxy.data);
}

test.describe.serial('OCTO live observability demo script', () => {
  test.beforeEach(() => {
    test.skip(!ADMIN_PASSWORD, 'Set OCTO_ADMIN_PASSWORD to run the admin-console part of the demo script.');
  });

  test('runs shopper, support, and admin threat-hunting simulations end to end', async ({ page, request }) => {
    test.setTimeout(Math.max(DEMO_TIMEOUT_MS * 16, 240_000));

    const [shopCapabilities, adminCapabilities] = await Promise.all([
      apiJson(request, `${SHOP_BASE_URL}/api/observability/capabilities`),
      apiJson(request, `${ADMIN_BASE_URL}/api/observability/capabilities`),
    ]);

    expect(assertObject(shopCapabilities.runtime).apm_configured).toBe(true);
    expect(assertObject(shopCapabilities.runtime).logging_configured).toBe(true);
    expect(assertObject(adminCapabilities.runtime).apm_configured).toBe(true);
    expect(assertObject(adminCapabilities.runtime).logging_configured).toBe(true);

    const checkoutResults: Record<string, unknown>[] = [];

    for (const scenario of PAYMENT_SCENARIOS) {
      const productIds = await stockedProductIds(request, scenario.quantity);
      await prepareFreshShopSession(page, scenario);
      await addProductsToCart(page, productIds);
      checkoutResults.push(await runCheckout(page, request, scenario));
    }

    expect(checkoutResults.length).toBe(PAYMENT_SCENARIOS.length);
    expect(checkoutResults.some((checkout) => checkout.payment_status === 'failed')).toBe(true);
    expect(checkoutResults.some((checkout) => checkout.payment_status === 'paid')).toBe(true);

    const supportTicket = await createSupportTicket(page);
    expect(supportTicket.status ?? supportTicket.ticket_id ?? supportTicket.ticket).toBeTruthy();

    await loginToAdmin(page);
    await page.goto(`${ADMIN_BASE_URL}/settings`);
    await expect(page.getByText('Java App Server + Payment Gateway')).toBeVisible({ timeout: DEMO_TIMEOUT_MS });
    await expect(page.getByRole('heading', { name: /Attack Lab/ })).toBeVisible();

    const javaHealth = expectProxiedAdminResult(
      await postAdminSimulation(page, 'java-health', {}, 'GET'),
      'java-health',
    );
    expect(javaHealth.java_app_server).toBeDefined();

    const storyboard = expectProxiedAdminResult(
      await postAdminSimulation(page, 'demo-storyboard', {
        persona: 'Field services buyer',
        quantity: 3,
        source_ip: '198.51.100.42',
        card: { brand: 'visa', number: '4242424242424242' },
      }),
      'demo-storyboard',
    );
    expect(storyboard.status).toBe('completed');
    expect(typeof storyboard.trace_id).toBe('string');

    const syntheticUsers = expectProxiedAdminResult(
      await postAdminSimulation(page, 'synthetic-users', {
        domain: 'apex.example.test',
        count: 12,
        order_count: 12,
        delete_after_days: 7,
      }),
      'synthetic-users',
    );
    expect(syntheticUsers.status).toBe('completed');
    expect(Number(syntheticUsers.created_users ?? 0) + Number(syntheticUsers.updated_users ?? 0)).toBeGreaterThan(0);

    const attack = expectProxiedAdminResult(
      await postAdminSimulation(page, 'attack-lab', {
        source_ip: '203.0.113.77',
        external_status_code: 503,
        user_agent: 'curl/8.4.0 octo-attack-lab',
        payment_redirect_url: 'https://pay-update.example.test/checkout/session',
        card: { brand: 'visa', number: '4242424242424242' },
      }),
      'attack-lab',
    );

    expect(attack.status).toBe('completed');
    expect(typeof attack.attack_id).toBe('string');
    expect(typeof attack.trace_id).toBe('string');
    expect(Array.isArray(attack.compromised_hosts)).toBe(true);
    expect(assertObject(attack.payment).interception_detected).toBe(true);
    expect(assertObject(attack.payment).redirect_detected).toBe(true);
    expect(assertObject(attack.hunt_pivots).log_analytics_pivots).toBeDefined();
  });
});
