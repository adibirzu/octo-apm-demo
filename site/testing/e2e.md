# E2E Tests

237 Playwright tests across 8 spec files covering the full application surface.

## Test Dimensions

| Spec File | Tests | What It Covers |
|---|---|---|
| `health.spec.ts` | Health checks, readiness probes, DB connectivity |
| `shopping-flow.spec.ts` | Full buyer journey: storefront → cart → checkout → orders |
| `cross-service.spec.ts` | Shop↔CRM bidirectional sync, distributed trace propagation |
| `melts.spec.ts` | MELTS stack: Prometheus metrics, 360 dashboard, traceparent, security |
| `auth-sso.spec.ts` | SSO status, IDCS flow, token validation, protected endpoints |
| `simulation.spec.ts` | Chaos controls gated behind SSO, input validation |
| `availability.spec.ts` | Concurrency (10 parallel health, 5 parallel ready), malformed payloads |
| `k6-integration.spec.ts` | k6 test file validation (structure, BASE_URL) |

## Running Tests

=== "Local"

    ```bash
    npm install
    npm run test:e2e
    ```

=== "Against Live OKE"

    ```bash
    SHOP_URL=https://shop.octodemo.cloud \
    CRM_URL=https://crm.octodemo.cloud \
    npm run test:e2e
    ```

=== "Single Spec"

    ```bash
    npx playwright test tests/e2e/melts.spec.ts
    ```

## Configuration

```typescript
// playwright.config.ts
{
  projects: [
    { name: 'chromium' },  // Browser tests
    { name: 'api' }        // Lightweight API tests
  ],
  timeout: isLive ? 45000 : 20000,  // OKE vs local timeouts
  reporter: [['html'], ['junit']]
}
```
