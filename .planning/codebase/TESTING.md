# Codebase Testing

Generated: 2026-05-14

## Test Surfaces

- Root pytest tests validate unified deploy/docs invariants and OCI/Log
  Analytics assets.
- `shop/tests/` covers Shop routes, checkout, payment gateway simulation,
  Java sidecar client behavior, observability, monitoring, readiness, and UI
  fragments.
- `crm/tests/` covers Admin/CRM routes, orders, auth/idempotency, observability,
  data retention, and monitoring.
- `services/*/tests` or package-local tests cover supporting services.
- `services/apm-java-demo` uses Maven/JUnit tests.
- `tests/e2e/` and `shop/tests/e2e/` use Playwright for cross-service browser
  flows.
- `deploy/verify.sh` validates scripts, manifests, Helm, Terraform formatting,
  docs, pytest suites, and template smoke checks.
- `mkdocs build --strict` validates public documentation.

## Common Commands

```bash
python3 -m pytest -q tests/test_unified_deploy_surface.py
python -m pytest shop/tests -q
python -m pytest crm/tests -q
cd services/apm-java-demo && mvn test
npx playwright test tests/e2e/cross-service-smoke.spec.ts
python -m mkdocs build --strict
bash deploy/verify.sh
```

## Focused Validation for Current Roadmap

- Payment flow: targeted Shop payment tests, Java sidecar Maven tests, and
  Playwright payment gateway traces.
- APM/Log Analytics: saved-search deployment checks, parser/source tests,
  trace-log coverage searches, and live query verification where OCI access is
  available.
- OKE parity: OKE manifest/render checks, Kubernetes monitoring health searches,
  and public LB smoke tests that can hit VM or OKE.
- Admin AI: coordinator scope tests, GenAI readiness, LLMetry/Langfuse
  telemetry checks, and sanitized log assertions.
- Docs: `mkdocs build --strict` plus secret/placeholder scans for public pages.

## Last Known Validation Context

Before GSD onboarding, project notes indicated successful focused validation of
Shop, Admin/CRM, Java payment flows, public E2E payment journeys, Log
Analytics/OKE checkout correlation, docs build, and whitespace checks. Treat
that as historical context, not a substitute for re-running tests after new
code changes.
