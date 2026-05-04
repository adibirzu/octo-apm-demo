# Testing

## Validation Surfaces

| Type | Tool | Scope |
|---|---|---|
| Deploy-targeted E2E | Playwright | Cross-service smoke, SSO PKCE smoke, optional full-platform smoke |
| Load (shop) | k6 | Browse, checkout, DB stress, cross-service stress |
| Deploy validation | `deploy/verify.sh` | Scripts, manifests, Helm render, docs, pytest, template smoke |
| Health probes | OCI + Kubernetes | `/ready`, rollout status, ingress/controller health |

## Sections

- [E2E Tests](e2e.md) — root Playwright smoke specs for deployed tenancies
- [Load Tests](load-tests.md) — k6 stress test suites with light/moderate/heavy profiles
