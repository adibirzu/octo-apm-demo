import { test, expect } from '@playwright/test';

type Page = any;

const env = typeof process !== 'undefined' ? process.env : {};

const SHOP_URL_PARAM = 'https://shop.example.test';
const ADMIN_URL_PARAM = 'https://admin.example.test';
// <ORAP><ON>OCTO_LIVE_SHOP_URL</ON><OV>https://shop.example.test</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_LIVE_ADMIN_URL</ON><OV>https://admin.example.test</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_APM_DEMO_MODE</ON><OV>monitor</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_ADMIN_USERNAME</ON><OV>admin</OV><OS>false</OS></ORAP>
// <ORAP><ON>OCTO_ADMIN_PASSWORD</ON><OS>true</OS></ORAP>
// <ORAP><ON>OCTO_INTERNAL_SERVICE_KEY</ON><OS>true</OS></ORAP>

const SHOP_URL = env.OCTO_LIVE_SHOP_URL || env.SHOP_URL || SHOP_URL_PARAM;
const ADMIN_URL = env.OCTO_LIVE_ADMIN_URL || env.ADMIN_URL || ADMIN_URL_PARAM;
const DEMO_MODE = env.OCTO_APM_DEMO_MODE === 'full' ? 'full' : 'monitor';
const INTERNAL_SERVICE_KEY = env.OCTO_INTERNAL_SERVICE_KEY || env.INTERNAL_SERVICE_KEY || '';
const STEP_TIMEOUT_MS = 45_000;

function adminCredentials(): { username: string; password: string } {
  const username = env.OCTO_ADMIN_USERNAME || 'admin';
  const password = env.OCTO_ADMIN_PASSWORD || env.ADMIN_PASSWORD || '';
  if (!password) {
    throw new Error('Admin password is missing. Configure OCTO_ADMIN_PASSWORD as a secret monitor parameter.');
  }

  return {
    username,
    password,
  };
}

type CardPaymentScenario = {
  kind: 'card';
  label: string;
  email: string;
  name: string;
  persona: string;
  company: string;
  quantity: 2 | 3;
  cardNumber: string;
  expiry: string;
  cvv: string;
  expectedPaymentStatus: 'paid' | 'failed';
};

type WalletPaymentScenario = {
  kind: 'wallet';
  label: string;
  email: string;
  name: string;
  persona: string;
  company: string;
  quantity: 2 | 3;
  method: 'apple_pay' | 'google_pay';
  expectedPaymentStatus: 'paid';
};

type ManualPaymentScenario = {
  kind: 'manual';
  label: string;
  email: string;
  name: string;
  persona: string;
  company: string;
  quantity: 2 | 3;
  method: 'bank_transfer';
};

type PaymentScenario = CardPaymentScenario | WalletPaymentScenario | ManualPaymentScenario;
type SyntheticSessionSeed = { nextSessionId: string; syntheticUserEmail: string };
type AdminActionArgs = {
  nextAction: string;
  nextPayload: Record<string, unknown>;
  nextMethod: 'GET' | 'POST';
};

const PAYMENT_SCENARIOS: PaymentScenario[] = [
  {
    kind: 'card',
    label: 'alex-fleet-mastercard-approved',
    email: 'alex.chen@apex.example.test',
    name: 'Alex Chen',
    persona: 'Fleet operations buyer',
    company: 'Apex Fleet Operations',
    quantity: 2,
    cardNumber: '5555555555554444',
    expiry: '12/30',
    cvv: '321',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'maya-field-visa-approved',
    email: 'maya.ionescu@apex.example.test',
    name: 'Maya Ionescu',
    persona: 'Field services buyer',
    company: 'Apex Field Services',
    quantity: 3,
    cardNumber: '4111111111111111',
    expiry: '12/30',
    cvv: '123',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'nora-energy-issuer-decline',
    email: 'nora.patel@apex.example.test',
    name: 'Nora Patel',
    persona: 'Energy survey buyer',
    company: 'Apex Energy Survey',
    quantity: 2,
    cardNumber: '4000000000000002',
    expiry: '12/30',
    cvv: '123',
    expectedPaymentStatus: 'failed',
  },
  {
    kind: 'manual',
    label: 'daniel-infrastructure-bank-transfer',
    email: 'daniel.rossi@apex.example.test',
    name: 'Daniel Rossi',
    persona: 'Infrastructure buyer',
    company: 'Apex Infrastructure',
    quantity: 3,
    method: 'bank_transfer',
  },
  {
    kind: 'wallet',
    label: 'irina-public-safety-apple-pay',
    email: 'irina.marin@apex.example.test',
    name: 'Irina Marin',
    persona: 'Public safety buyer',
    company: 'Apex Public Safety',
    quantity: 2,
    method: 'apple_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'wallet',
    label: 'samuel-logistics-google-pay',
    email: 'samuel.wright@apex.example.test',
    name: 'Samuel Wright',
    persona: 'Logistics buyer',
    company: 'Apex Logistics',
    quantity: 3,
    method: 'google_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'elena-agriculture-visa-approved',
    email: 'elena.garcia@apex.example.test',
    name: 'Elena Garcia',
    persona: 'Agriculture buyer',
    company: 'Apex Agriculture',
    quantity: 2,
    cardNumber: '4111111111111111',
    expiry: '12/30',
    cvv: '123',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'noah-inspection-mastercard-approved',
    email: 'noah.kim@apex.example.test',
    name: 'Noah Kim',
    persona: 'Inspection buyer',
    company: 'Apex Inspection Services',
    quantity: 3,
    cardNumber: '5555555555554444',
    expiry: '12/30',
    cvv: '321',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'wallet',
    label: 'sofia-rail-apple-pay',
    email: 'sofia.andersen@apex.example.test',
    name: 'Sofia Andersen',
    persona: 'Rail systems buyer',
    company: 'Apex Rail Systems',
    quantity: 2,
    method: 'apple_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'wallet',
    label: 'matei-utilities-google-pay',
    email: 'matei.popa@apex.example.test',
    name: 'Matei Popa',
    persona: 'Utilities buyer',
    company: 'Apex Utilities',
    quantity: 3,
    method: 'google_pay',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'card',
    label: 'lina-emergency-visa-approved',
    email: 'lina.hoffman@apex.example.test',
    name: 'Lina Hoffman',
    persona: 'Emergency response buyer',
    company: 'Apex Emergency Response',
    quantity: 2,
    cardNumber: '4111111111111111',
    expiry: '12/30',
    cvv: '123',
    expectedPaymentStatus: 'paid',
  },
  {
    kind: 'manual',
    label: 'omar-maritime-bank-transfer',
    email: 'omar.saleh@apex.example.test',
    name: 'Omar Saleh',
    persona: 'Maritime buyer',
    company: 'Apex Maritime',
    quantity: 3,
    method: 'bank_transfer',
  },
];

const MONITOR_PAYMENT_SCENARIOS = PAYMENT_SCENARIOS;

function uniqueSession(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function objectField(value: unknown, label: string): Record<string, unknown> {
  expect(value, `${label} should be present`).toBeTruthy();
  expect(typeof value, `${label} should be an object`).toBe('object');
  expect(Array.isArray(value), `${label} should not be an array`).toBe(false);
  return value as Record<string, unknown>;
}

function stringField(value: unknown, label: string): string {
  expect(typeof value, `${label} should be a string`).toBe('string');
  expect((value as string).length, `${label} should be non-empty`).toBeGreaterThan(0);
  return value as string;
}

function stepNames(gateway: Record<string, unknown>): string[] {
  const steps = Array.isArray(gateway.steps) ? gateway.steps : [];
  expect(steps.length, 'payment gateway should expose detailed steps').toBeGreaterThan(5);
  return steps.map((step) => String((step as Record<string, unknown>).name || ''));
}

function assertSafePaymentTelemetry(
  checkoutBody: Record<string, unknown>,
  scenario: PaymentScenario,
): { gatewayRequestId: string; traceId: string } | null {
  const traceId = stringField(checkoutBody.trace_id, 'checkout.trace_id');
  expect(traceId).toMatch(/^[0-9a-f]{32}$/);

  if (scenario.kind === 'manual') {
    expect(checkoutBody.payment_status).toBe('pending');
    return null;
  }

  const payment = objectField(checkoutBody.payment, 'checkout.payment');
  expect(payment.status).toBe(scenario.expectedPaymentStatus === 'paid' ? 'authorized' : 'declined');
  expect(payment.method).toBe(scenario.kind === 'card' ? 'credit_card' : scenario.method);
  stringField(payment.provider, 'payment.provider');
  stringField(payment.decision_source, 'payment.decision_source');
  expect(Number(payment.risk_score), 'payment.risk_score should be numeric').not.toBeNaN();

  if (scenario.kind === 'card') {
    stringField(payment.card_brand, 'payment.card_brand');
    expect(payment.card_last4).toBe(scenario.cardNumber.slice(-4));
    const serialized = JSON.stringify(payment);
    expect(serialized).not.toContain(scenario.cardNumber);
    expect(serialized).not.toContain(scenario.cvv);
  } else {
    expect(payment.wallet_type).toBe(scenario.method);
  }

  const gateway = objectField(payment.gateway, 'payment.gateway');
  expect(gateway.gateway).toBe('octo-payment-gateway-emulator');
  expect(gateway.provider).toBe('cybersource-compatible-simulator');
  const gatewayRequestId = stringField(gateway.request_id, 'payment.gateway.request_id');
  const names = stepNames(gateway);
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

  const verification = objectField(gateway.verification, 'payment.gateway.verification');
  expect(verification.provider).toBe('octo-antifraud-verification-app');
  stringField(verification.decision, 'payment.gateway.verification.decision');
  const finalStep = objectField(gateway.final_step, 'payment.gateway.final_step');
  expect(finalStep.name).toBe('merchant_authorization_result');
  expect(['authorized', 'declined', 'completed']).toContain(String(finalStep.status));

  return { gatewayRequestId, traceId };
}

async function assertPaymentGatewayDrilldown(page: Page, gatewayRequestId: string): Promise<void> {
  if (!INTERNAL_SERVICE_KEY) {
    console.log('octoSynthetic:payment_gateway_drilldown=skipped_internal_key_missing');
    return;
  }

  const result = await page.evaluate(
    async ({ requestId, internalKey }: { requestId: string; internalKey: string }) => {
      const response = await fetch(
        `/api/observability/payment-gateway/events?gateway_request_id=${encodeURIComponent(requestId)}&limit=50`,
        {
          headers: {
            Accept: 'application/json',
            'X-Internal-Service-Key': internalKey,
          },
        },
      );
      return {
        status: response.status,
        body: await response.json(),
      };
    },
    { requestId: gatewayRequestId, internalKey: INTERNAL_SERVICE_KEY },
  );

  expect(result.status).toBe(200);
  const body = objectField(result.body, 'payment gateway drilldown response');
  const summary = objectField(body.summary, 'payment gateway drilldown summary');
  expect(Number(summary.event_count), 'payment gateway drilldown should return persisted events').toBeGreaterThan(0);
  expect(summary.gateway_request_ids).toContain(gatewayRequestId);
}

async function capture(page: Page, name: string): Promise<void> {
  console.log(`oraSynCustomScreenshot:${name}`);
  await page.waitForTimeout(250);
}

async function prepareShop(page: Page, scenario: PaymentScenario): Promise<void> {
  const sessionId = uniqueSession(`oci-apm-${scenario.label}`);
  await page.goto(SHOP_URL, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ({ nextSessionId, syntheticUserEmail }: SyntheticSessionSeed) => {
      localStorage.setItem('octo-session-id', nextSessionId);
      localStorage.setItem('octoSyntheticUserEmail', syntheticUserEmail);
    },
    { nextSessionId: sessionId, syntheticUserEmail: scenario.email },
  );

  await page.goto(`${SHOP_URL}/shop?synthetic_user=${encodeURIComponent(scenario.email)}`);
  await expect(page.locator('[data-testid="checkout-form"]')).toBeVisible({ timeout: STEP_TIMEOUT_MS });
  await expect(page.locator('[data-testid="add-to-cart-button"]').first()).toBeVisible({ timeout: STEP_TIMEOUT_MS });
}

async function stockedProductIds(page: Page, quantity: number): Promise<number[]> {
  const result = await page.evaluate(async (requestedQuantity: number) => {
    const response = await fetch('/api/shop/storefront', { headers: { Accept: 'application/json' } });
    const body = (await response.json()) as { products?: any[] };
    const products = Array.isArray(body.products) ? body.products : [];
    const stocked = products
      .filter((product: any) => Number(product.stock || 0) > 0)
      .sort((left: any, right: any) => {
        const stockDelta = Number(right.stock || 0) - Number(left.stock || 0);
        return stockDelta || Number(left.price || 0) - Number(right.price || 0);
      });
    const totalStock = stocked.reduce((sum: number, product: any) => sum + Number(product.stock || 0), 0);
    if (totalStock < requestedQuantity) return [];

    const ids: number[] = [];
    for (const product of stocked) {
      const available = Number(product.stock || 0);
      const copies = Math.min(available, requestedQuantity - ids.length);
      for (let index = 0; index < copies; index += 1) {
        ids.push(Number(product.id));
      }
      if (ids.length >= requestedQuantity) break;
    }
    return ids;
  }, quantity);
  const ids = Array.isArray(result)
    ? result.filter((id): id is number => typeof id === 'number' && Number.isFinite(id))
    : [];
  expect(ids.length, `storefront should expose ${quantity} in-stock drone units`).toBe(quantity);
  return ids;
}

async function addProductsToCart(page: Page, quantity: number): Promise<void> {
  const productIds = await stockedProductIds(page, quantity);
  for (const productId of productIds) {
    const productButton = page.locator(`[data-testid="add-to-cart-button"][data-id="${productId}"]`);
    const addButton = (await productButton.count()) > 0
      ? productButton.first()
      : page.locator('[data-testid="add-to-cart-button"]').first();
    await addButton.click();
    await expect(page.locator('#cartChip')).toContainText(/item/, { timeout: STEP_TIMEOUT_MS });
  }
  await expect(page.locator('#cartChip')).toHaveText(new RegExp(`${quantity} items?`), { timeout: STEP_TIMEOUT_MS });
}

async function fillBuyer(page: Page, scenario: PaymentScenario): Promise<void> {
  await page.locator('[data-testid="checkout-name"]').fill(scenario.name);
  await page.locator('[data-testid="checkout-email"]').fill(scenario.email);
  await page.locator('[data-testid="checkout-company"]').fill(scenario.company);
  await page.locator('[data-testid="checkout-phone"]').fill('+1 555 0184');
  await page.locator('[data-testid="checkout-address"]').fill(`100 Demo Operations Way - ${scenario.persona}`);
}

async function selectPayment(page: Page, scenario: PaymentScenario): Promise<void> {
  if (scenario.kind === 'card') {
    await page.locator('[data-testid="payment-method"]').selectOption('credit_card');
    await page.locator('[data-testid="card-number"]').fill(scenario.cardNumber);
    await page.locator('[data-testid="card-expiry"]').fill(scenario.expiry);
    await page.locator('[data-testid="card-cvv"]').fill(scenario.cvv);
    await page.locator('[data-testid="cardholder-name"]').fill(scenario.name);
    await page.locator('[data-testid="billing-postal-code"]').fill('10001');
    return;
  }

  if (scenario.kind === 'wallet') {
    await page.locator('[data-testid="payment-method"]').selectOption(scenario.method);
    const testId = scenario.method === 'apple_pay' ? 'apple-pay-button' : 'google-pay-button';
    await page.locator(`[data-testid="${testId}"]`).click();
    return;
  }

  await page.locator('[data-testid="payment-method"]').selectOption(scenario.method);
}

async function checkout(page: Page, scenario: PaymentScenario): Promise<Record<string, unknown>> {
  await fillBuyer(page, scenario);
  await selectPayment(page, scenario);

  const responsePromise = page.waitForResponse(
    (response: any) => response.url().includes('/api/shop/checkout') && response.request().method() === 'POST',
    { timeout: STEP_TIMEOUT_MS },
  );

  await page.locator('[data-testid="place-order-button"]').click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);

  const body = (await response.json()) as Record<string, unknown>;
  expect(body.status).toBe('order_placed');
  expect(typeof body.order_id).toBe('number');
  expect(typeof body.trace_id).toBe('string');
  await expect(page.locator('[data-testid="checkout-status"]')).toContainText('Order #', { timeout: STEP_TIMEOUT_MS });

  if (scenario.kind === 'card' || scenario.kind === 'wallet') {
    expect(body.payment_status).toBe(scenario.expectedPaymentStatus);
  }

  const paymentCorrelation = assertSafePaymentTelemetry(body, scenario);
  if (paymentCorrelation) {
    const expectedPaymentStatus = scenario.kind === 'manual' ? 'pending' : scenario.expectedPaymentStatus;
    console.log(
      `octoSynthetic:checkout_trace=${paymentCorrelation.traceId};gateway_request=${paymentCorrelation.gatewayRequestId};method=${scenario.kind === 'card' ? 'credit_card' : scenario.method};expected=${expectedPaymentStatus}`,
    );
    await assertPaymentGatewayDrilldown(page, paymentCorrelation.gatewayRequestId);
  }

  return body;
}

async function createSupportTicket(page: Page): Promise<void> {
  await page.goto(`${SHOP_URL}/services?synthetic_user=maya.ionescu@apex.example.test`);
  await expect(page.locator('#ticketForm')).toBeVisible({ timeout: STEP_TIMEOUT_MS });
  await page.getByRole('button', { name: 'Book' }).first().click();
  await page.locator('#ticketTitle').fill('Telemetry validation for synthetic demo order');
  await page.locator('#ticketPriority').selectOption('high');
  await page.locator('#ticketContent').fill(
    'Correlate browser session, checkout trace, payment gateway, Java APM sidecar, app logs, and support ticket evidence.',
  );

  const responsePromise = page.waitForResponse(
    (response: any) => response.url().includes('/api/services/tickets') && response.request().method() === 'POST',
    { timeout: STEP_TIMEOUT_MS },
  );
  await page.getByRole('button', { name: 'Submit Ticket' }).click();
  const response = await responsePromise;
  expect([200, 201]).toContain(response.status());
}

async function loginToAdmin(page: Page): Promise<void> {
  const credentials = adminCredentials();
  await page.goto(`${ADMIN_URL}/login`);
  await page.locator('#login-username').fill(credentials.username);
  await page.locator('#login-password').fill(credentials.password);
  await Promise.all([
    page.waitForURL((url: URL) => url.pathname !== '/login', { timeout: STEP_TIMEOUT_MS }),
    page.getByRole('button', { name: 'Login' }).click(),
  ]);
  await page.goto(`${ADMIN_URL}/settings`);
  await expect(page.getByText('Java App Server + Payment Gateway')).toBeVisible({ timeout: STEP_TIMEOUT_MS });
}

async function runAdminAction(
  page: Page,
  action: string,
  payload: Record<string, unknown>,
  method: 'GET' | 'POST' = 'POST',
): Promise<Record<string, unknown>> {
  const result = await page.evaluate(
    async ({ nextAction, nextPayload, nextMethod }: AdminActionArgs) => {
      const response = await fetch(`/api/simulate/drone-shop/${nextAction}`, {
        method: nextMethod,
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: nextMethod === 'POST' ? JSON.stringify(nextPayload) : undefined,
      });
      return {
        status: response.status,
        body: await response.json(),
      };
    },
    { nextAction: action, nextPayload: payload, nextMethod: method },
  );

  expect(result.status).toBe(200);
  const body = result.body as Record<string, unknown>;
  expect(body.status).toBe('proxied');
  expect(body.upstream_status).toBe(200);
  return body.data as Record<string, unknown>;
}

test('OCI APM OCTO live observability demo', async ({ page }) => {
  test.setTimeout(360_000);

  const paymentScenarios = DEMO_MODE === 'full' ? PAYMENT_SCENARIOS : MONITOR_PAYMENT_SCENARIOS;

  for (const [index, scenario] of paymentScenarios.entries()) {
    await prepareShop(page, scenario);
    if (index === 0) await capture(page, '01-shop-catalog');
    await addProductsToCart(page, scenario.quantity);
    console.log(
      `octoSynthetic:buyer=${scenario.email};persona=${scenario.persona};quantity=${scenario.quantity};payment=${scenario.kind === 'card' ? 'credit_card' : scenario.method}`,
    );
    const order = await checkout(page, scenario);

    if (index === 0) await capture(page, '02-first-buyer-checkout');
    if ((scenario.kind === 'card' || scenario.kind === 'wallet') && scenario.expectedPaymentStatus === 'failed') {
      await capture(page, '03-decline-checkout');
    }
    if (scenario.kind === 'wallet' && scenario.method === 'google_pay') await capture(page, '04-google-pay-checkout');
    if (scenario.kind === 'manual') await capture(page, '05-bank-transfer-checkout');
    if (index === paymentScenarios.length - 1) await capture(page, '06-final-buyer-checkout');

    expect(order.order_id).toBeTruthy();
  }

  await createSupportTicket(page);
  await capture(page, '07-support-ticket');

  await loginToAdmin(page);
  await capture(page, '08-admin-settings');

  const javaHealth = await runAdminAction(page, 'java-health', {}, 'GET');
  expect(javaHealth.java_app_server).toBeDefined();
  await capture(page, '09-java-health');

  if (DEMO_MODE === 'full') {
    const storyboard = await runAdminAction(page, 'demo-storyboard', {
      persona: 'Field services buyer',
      quantity: 3,
      source_ip: '198.51.100.42',
      card: { brand: 'visa', number: '4242424242424242' },
    });
    expect(storyboard.status).toBe('completed');
    await capture(page, '10-demo-storyboard');

    const syntheticUsers = await runAdminAction(page, 'synthetic-users', {
      domain: 'apex.example.test',
      count: 12,
      order_count: 12,
      delete_after_days: 7,
    });
    expect(syntheticUsers.status).toBe('completed');
  }

  const attack = await runAdminAction(page, 'attack-lab', {
    source_ip: '203.0.113.77',
    external_status_code: 503,
    user_agent: 'curl/8.4.0 octo-attack-lab',
    payment_redirect_url: 'https://pay-update.example.test/checkout/session',
    card: { brand: 'visa', number: '4242424242424242' },
  });
  expect(attack.status).toBe('completed');
  expect(typeof attack.attack_id).toBe('string');
  expect(typeof attack.trace_id).toBe('string');
  await capture(page, DEMO_MODE === 'full' ? '11-attack-lab' : '10-attack-lab');
});
