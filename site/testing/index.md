# Testing

## Test Coverage

| Type | Tool | Count | Coverage |
|---|---|---|---|
| E2E | Playwright | 237 tests | Health, shopping, cross-service, MELTS, auth, simulation, availability, k6 |
| Load (shop) | k6 | 4 scenarios | Browse, API load, geo-latency, security probes |
| Load (cross-service) | k6 | 5 scenarios | Shop+CRM browse, API, distributed traces, checkout, observability |
| Load (DB stress) | k6 | 6 scenarios | Bulk writes, N+1, slow queries, checkout storms, CRM sync |
| Health probes | OCI | Continuous | HTTP `/ready` every 30s |

## Sections

- [E2E Tests](e2e.md) — 237 Playwright tests across 8 dimensions
- [Load Tests](load-tests.md) — k6 stress test suites with light/moderate/heavy profiles
