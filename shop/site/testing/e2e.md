# E2E Tests

This page covers two different Playwright layers:

- `shop/tests/e2e/` for the shop-local regression suite.
- Root `tests/e2e/` for deployed-tenancy smoke after bootstrap.

## Shop-local suite

Use the shop-local suite while iterating on the storefront and its
cross-service contract:

```bash
cd shop
npm install
npm run test:e2e
```

To point the suite at a live environment instead of localhost:

```bash
cd shop
SHOP_URL=https://shop.<your-domain> \
CRM_URL=https://crm.<your-domain> \
npm run test:e2e
```

## Hand-off to unified tenancy smoke

After the root `deploy/bootstrap.sh` flow finishes, switch to the root
repo smoke specs:

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
CRM_BASE_URL=https://crm.<your-domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts
```

If SSO is configured for the tenancy:

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
OCTO_E2E_TEST_USER_EMAIL=e2e@example.com \
OCTO_E2E_TEST_USER_PASSWORD='***' \
SSO_E2E_ENABLED=1 \
npx playwright test tests/e2e/sso-oidc-pkce.spec.ts
```
