# Testing

This subtree documents the **shop-local** test surface. The unified repo
also ships deploy-targeted Playwright smoke specs under root
`tests/e2e/`; use those when validating a freshly provisioned tenancy.

## Coverage

| Type | Tool | Scope |
|---|---|---|
| Shop-local browser and API checks | Playwright | `shop/tests/e2e/` against the storefront and CRM integration surface |
| Load (shop) | k6 | Browse, API load, geo-latency, security probes |
| Load (cross-service) | k6 | Shop+CRM browse, API, distributed traces, checkout, observability |
| Load (DB stress) | k6 | Bulk writes, N+1, slow queries, checkout storms, CRM sync |
| Deploy-targeted smoke | Playwright | Root `tests/e2e/` against a live tenancy |

## Sections

- [E2E Tests](e2e.md) — shop-local Playwright suite plus the hand-off to root tenancy smoke
- [Load Tests](load-tests.md) — k6 stress test suites with light/moderate/heavy profiles
