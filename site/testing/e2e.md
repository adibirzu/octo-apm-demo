# E2E Tests

The root repo ships **deployment-targeted** Playwright specs under
`tests/e2e/`. They run against a live tenancy, not the local dev stack.

## Specs

| File | Opt-in flag | What it proves |
|---|---|---|
| `tests/e2e/cross-service-smoke.spec.ts` | `CROSS_SERVICE_E2E_ENABLED=1` | `/api/integrations/schema` parity, CRM auth enforcement, idempotency-token dedup, `/ready` DB health, trace propagation |
| `tests/e2e/sso-oidc-pkce.spec.ts` | `SSO_E2E_ENABLED=1` | OCI IAM Identity Domain Authorization Code + PKCE round-trip, session establishment, logout cleanup, callback rejection cases |
| `tests/e2e/full-platform-smoke.spec.ts` | `FULL_PLATFORM_E2E_ENABLED=1` | Shop/CRM readiness plus optional `load-control`, `remediator`, and `object-pipeline` endpoints when you expose them in the tenancy |

## Before you run them in a new tenancy

- Shop and CRM must both be reachable over HTTP or HTTPS.
- ATP must already be `AVAILABLE`.
- `INTERNAL_SERVICE_KEY` is required for cross-service and full-platform smoke.
- `octo-sso` plus a real test user are required for the SSO spec.
- For the shared `DEFAULT` environment, the baked-in URLs are `https://shop.example.test` and `https://crm.example.test`, but do not rely on those defaults unless [Current Status](../operations/current-status.md) says the tenancy is healthy.

## Install Playwright once

```bash
npx playwright install --with-deps chromium
```

## Cross-service smoke

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
CRM_BASE_URL=https://crm.<your-domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts
```

If public DNS is not propagated yet but ingress is healthy, point both base URLs at the ingress IP and pass the expected virtual host names:

```bash
SHOP_BASE_URL=http://<ingress-ip> \
CRM_BASE_URL=http://<ingress-ip> \
SHOP_HOST_HEADER=shop.<your-domain> \
CRM_HOST_HEADER=crm.<your-domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts
```

## SSO smoke

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
OCTO_E2E_TEST_USER_EMAIL=e2e@example.com \
OCTO_E2E_TEST_USER_PASSWORD='***' \
SSO_E2E_ENABLED=1 \
npx playwright test tests/e2e/sso-oidc-pkce.spec.ts
```

The Identity Domain application must allow Authorization Code + PKCE and
use `https://shop.<your-domain>/api/auth/sso/callback` as the redirect
URI.

## Full-platform smoke

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
CRM_BASE_URL=https://crm.<your-domain> \
LOAD_CONTROL_URL=https://load-control.<your-domain> \
REMEDIATOR_URL=https://remediator.<your-domain> \
OBJECT_PIPELINE_URL=https://object-pipeline.<your-domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
FULL_PLATFORM_E2E_ENABLED=1 \
npx playwright test tests/e2e/full-platform-smoke.spec.ts
```

Only set the optional service URLs when those components are actually
exposed in the tenancy under test.
