# E2E tests — `octo-apm-demo`

Playwright specs that run against a **deployed** environment (not a
local dev stack). They are opt-in via env vars so CI runs stay fast and
deterministic when the target isn't reachable.

## Specs

| File | Opt-in | What it asserts |
|---|---|---|
| `sso-oidc-pkce.spec.ts` | `SSO_E2E_ENABLED=1` | Full Authorization Code + PKCE round-trip against IDCS; session cookie; logout cleanup; negative cases (bad state, missing code) |
| `cross-service-smoke.spec.ts` | `CROSS_SERVICE_E2E_ENABLED=1` | `/api/integrations/schema` parity; CRM `/api/orders` auth enforcement; `idempotency_token` dedup; `/ready` DB health; W3C traceparent propagation |

## Run locally

```bash
# Install Playwright once
npx playwright install --with-deps chromium

# Cross-service smoke against the deployed env
SHOP_BASE_URL=https://shop.cyber-sec.ro \
CRM_BASE_URL=https://crm.cyber-sec.ro \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts

# SSO spec (requires an IDCS test user + confidential app configured)
SSO_E2E_ENABLED=1 \
SHOP_BASE_URL=https://shop.cyber-sec.ro \
OCTO_E2E_TEST_USER_EMAIL=e2e-test@cyber-sec.ro \
OCTO_E2E_TEST_USER_PASSWORD='***' \
npx playwright test tests/e2e/sso-oidc-pkce.spec.ts
```

For CAP or any other tenancy, override `SHOP_BASE_URL` / `CRM_BASE_URL` explicitly. The baked-in defaults now target `DEFAULT` / `oci4cca`.

## CI integration

Suggested GitHub Actions matrix job:

```yaml
jobs:
  e2e:
    if: github.event_name == 'schedule' || github.event.inputs.run_e2e == 'true'
    runs-on: ubuntu-latest
    env:
      CROSS_SERVICE_E2E_ENABLED: "1"
      SHOP_BASE_URL: ${{ secrets.SHOP_BASE_URL }}
      CRM_BASE_URL: ${{ secrets.CRM_BASE_URL }}
      INTERNAL_SERVICE_KEY: ${{ secrets.INTERNAL_SERVICE_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test tests/e2e/cross-service-smoke.spec.ts
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
```

Add a nightly cron trigger + a manual `workflow_dispatch` with
`run_e2e` input so you can kick off ad-hoc runs after any tenancy
change.
