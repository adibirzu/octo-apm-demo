---
title: Testing
---

# Testing

Pragmatic, command-first reference for contributors writing or running tests in `octo-apm-demo`. Every command in this document is runnable as shown from the repository root unless otherwise noted.

## A. Test Surface Overview

The repository is a multi-service observability demo. Tests are organized as a pyramid:

| Layer | Where | Purpose |
|-------|-------|---------|
| Unit | `shop/tests/`, `crm/tests/`, `services/*/tests/` | Function/module isolation. No network, no DB, no OCI SDK. Marked `@pytest.mark.unit`. |
| Integration | Same dirs, marked `@pytest.mark.integration` | Hit local services, in-process DB, queue, or wired adapters. |
| Contract / repo-wide | `tests/` (top level) | Cross-cutting invariants: signal contracts, observability assets, deployment parity, public docs. |
| Java sidecar | `services/apm-java-demo/src/test/java/` | Spring Boot MockMvc + JUnit 5 / AssertJ. |
| Browser synthetic (Playwright, TS) | `shop/tools/apm/octo-apm-demo-synthetic.spec.ts`, `tools/demo-guide/octo-availability-monitor.playwright.ts`, `shop/tests/e2e/*.spec.ts`, `tests/e2e/*.spec.ts`, `services/browser-runner/tests/journey-selection.spec.ts` | End-user journeys, availability monitors, cross-service smoke. |

Per-service Python test directories:

```text
shop/tests/                        # Shop (FastAPI) — ~40 test files
crm/tests/                         # CRM (FastAPI) — ~25 test files
services/async-worker/tests/       # async-worker
services/cache/tests/              # octo-cache
services/edge-fuzz/tests/          # edge-fuzz fault injector
services/load-control/tests/       # load-control control plane
services/object-pipeline/tests/    # object storage pipeline
services/remediator/tests/         # auto-remediator OCI Function
services/otel-gateway/tests/       # OTel collector config validation (shell)
services/browser-runner/tests/     # browser-runner (Playwright)
```

Top-level (`tests/`) contract files:

```text
tests/test_compute_java_app_server_surface.py
tests/test_compute_langfuse_surface.py
tests/test_compute_synthetic_users_surface.py
tests/test_deployment_parity_release_gates.py
tests/test_documentation_architecture_closure.py
tests/test_log_analytics_attack_assets.py
tests/test_log_analytics_detection_reliability.py
tests/test_observability_asset_contract.py
tests/test_signal_contract_inventory.py
tests/test_unified_deploy_surface.py
tests/e2e/                         # Playwright cross-service smoke + SSO
```

## B. Running the Full Local Validation Gate

This is the same sequence used as the release gate. Run all four steps from the repository root before opening a PR or cutting a release:

```bash
# 1. Python tests across the entire repo (top-level + every service)
python3 -m pytest -q tests/ shop/tests/ crm/tests/ services/*/tests/

# 2. Java sidecar (apm-java-demo)
mvn -B -f services/apm-java-demo/pom.xml test

# 3. Public docs build cleanly (strict — fails on broken links, dead refs, plugin errors)
python3 -m mkdocs build --strict

# 4. Deploy surface dry-run — bash syntax, helm lint, terraform validate, compose config, mkdocs strict
bash deploy/verify.sh
```

What each step protects:

- **Step 1** — Functional correctness of every Python service plus the cross-cutting contract suite. If any new code breaks a signal contract or a deployment parity invariant, this fails fast.
- **Step 2** — The Java sidecar's payment-rail simulator stays compilable and behavior-locked via Spring Boot MockMvc tests.
- **Step 3** — The public site (`site/`) renders without warnings under MkDocs strict mode. Catches broken navigation, missing anchors, and orphan pages before they ship to the public docs surface.
- **Step 4** — Every deploy script (`deploy/**`) is `bash -n` clean, supports `--help`, surfaces missing env vars, has parseable YAML, Helm charts that lint and render, Terraform that validates, and docker-compose configs that resolve.

## C. Contract Tests

These tests live in the top-level `tests/` directory and encode observability and deployment invariants that hold across all services.

### `tests/test_signal_contract_inventory.py`

Walks every source asset and asserts the required MELT-S fields (Metrics, Events, Logs, Traces, Security signals) are present, named consistently, and tagged with the agreed dimensions. Fails when a new signal is added without the corresponding contract entry.

### `tests/test_observability_asset_contract.py`

Validates the APM saved queries, Log Analytics searches, dashboards, and Monitoring alert definitions as a single coherent set. Each referenced metric must exist; each saved query must parse; each dashboard widget must point at a real source.

### `tests/test_log_analytics_detection_reliability.py`

Detection rules in `deploy/oci/log_analytics/` declare a metric + dimension contract (e.g., `octo.auth.failure_count` with dimension `tenant_id`). This test enforces the contract so a renamed dimension never silently breaks an alert.

### `tests/test_deployment_parity_release_gates.py`

Helm chart (`deploy/helm/octo-apm-demo/`) and raw OKE manifests (`deploy/k8s/oke/`) must declare the same containers, env keys, ports, probes, and security contexts. This test diffs them and fails if they drift.

### `tests/test_documentation_architecture_closure.py`

Public-doc forbidden-token guard. Scans `site/**/*.md` for live tenancy strings, public IPs, OCIDs, internal slugs, and other tokens that must never appear in published documentation. Also asserts diagrams are layered/editable and that admin/AI surfaces stay off the customer-facing pages.

### `tests/test_unified_deploy_surface.py`

Terraform + Compute deploy surface validation: every variable declared in `deploy/terraform/variables.tf` is wired through `deploy/compute/render-runtime-env.sh` and surfaces in the runtime env template, so a misnamed variable never reaches a VM.

### `tests/test_log_analytics_attack_assets.py`

Attack-lab detection assets: every storyboard step in the attack lab has a corresponding detection rule, saved query, and dashboard widget so the lab demo is reproducible end to end.

### Compute surface tests

- `tests/test_compute_java_app_server_surface.py`
- `tests/test_compute_langfuse_surface.py`
- `tests/test_compute_synthetic_users_surface.py`

Each verifies the Compute (VM) deploy surface for one runtime role: required systemd units, runtime env keys, healthcheck wiring.

Run just the contract suite:

```bash
python3 -m pytest -q tests/
```

## D. Service-Level Tests

### Shop (`shop/tests/`)

Headline test files and what they protect:

| File | Protects |
|------|----------|
| `test_payment_gateway_observability.py` | Payment gateway spans + drilldown correlation IDs |
| `test_checkout_idempotency.py` | Checkout idempotency keys + replay protection |
| `test_checkout_payment_widget.py` | Checkout payment widget contract |
| `test_auth_login_observability.py` | Login emits success/failure spans + metrics |
| `test_workflow_gateway_proxy.py` | Workflow gateway proxy passthrough |
| `test_dashboard_demo_page.py` | Observability dashboard demo page renders + scopes |
| `test_rum_synthetic_identity.py` | RUM session identity is propagated through synthetics |
| `test_security_headers.py` | CSP, HSTS, frame-options, referrer-policy |
| `test_rate_limit.py` | Per-endpoint rate-limit enforcement |
| `test_public_api.py`, `test_service_url_aliases.py` | Public API surface stability |
| `shop/tests/payments/test_*.py` | Payment provider unit tests (Stripe, simulated provider, gateway emulator, order state machine, webhook integration) |

Run the shop suite:

```bash
python3 -m pytest -q shop/tests/
```

### CRM (`crm/tests/`)

| File | Protects |
|------|----------|
| `test_admin_coordinator.py` | Admin coordinator scoping (admin-only OCI surfaces) |
| `test_admin_data_retention.py` | Data-retention controls on admin-managed data |
| `test_observability_guidance_surfaces.py` | In-app observability guidance content |
| `test_observability_customer_demo.py` | Customer-facing observability demo data |
| `test_observability_frontend.py` | Frontend trace propagation + RUM hooks |
| `test_oci_monitoring.py` | OCI Monitoring metric publish path |
| `test_frontend_trace_propagation.py` | Browser → server trace context propagation |
| `test_chaos_end_to_end.py` | Chaos scenario end-to-end orchestration |
| `test_published_architecture_diagram.py` | Architecture diagram source-of-truth check |

Run the CRM suite:

```bash
python3 -m pytest -q crm/tests/
```

### Java sidecar (`services/apm-java-demo/`)

Spring Boot + MockMvc unit tests covering the payment-rail simulator endpoints (`/ready`, payment endpoints, output capture for log assertions).

```bash
mvn -B -f services/apm-java-demo/pom.xml test
```

### Other services

```bash
python3 -m pytest -q services/async-worker/tests/
python3 -m pytest -q services/cache/tests/
python3 -m pytest -q services/edge-fuzz/tests/
python3 -m pytest -q services/load-control/tests/
python3 -m pytest -q services/object-pipeline/tests/
python3 -m pytest -q services/remediator/tests/
bash services/otel-gateway/tests/test_config_validates.sh
```

## E. Browser Synthetics (Playwright)

### Local run

```bash
cd shop
npx playwright install --with-deps   # first run only
npx playwright test
```

Tests live in:

- `shop/tools/apm/octo-apm-demo-synthetic.spec.ts` — the headline synthetic monitor that exercises card, wallet, and manual payment journeys end to end.
- `shop/tests/e2e/*.spec.ts` — shopping flow, auth/SSO, admin data management, simulation, MELT-S, payment gateway trace, k6 integration, availability, demo script, auto-remediation demo, cross-service.
- `tests/e2e/*.spec.ts` — `cross-service-smoke.spec.ts`, `full-platform-smoke.spec.ts`, `sso-oidc-pkce.spec.ts`.
- `tools/demo-guide/octo-availability-monitor.playwright.ts` — the APM availability monitor uploaded to OCI APM.
- `services/browser-runner/tests/journey-selection.spec.ts` — browser-runner journey selection logic.

### Synthetic scenarios (`octo-apm-demo-synthetic.spec.ts`)

The synthetic spec drives three scenario shapes from a parameterized scenario list:

- **`CardPaymentScenario`** — checkout with card details, expected payment status `paid` or `failed`.
- **`WalletPaymentScenario`** — checkout via `apple_pay` or `google_pay`, expected `paid`.
- **`ManualPaymentScenario`** — checkout via `bank_transfer`, no immediate paid status.

### Token-safe assertion helpers

The spec exposes two helpers that scrub sensitive correlation tokens before asserting:

- `assertSafePaymentTelemetry(body, scenario)` — verifies payment telemetry on the response without leaking gateway request IDs, last-four digits, or other PII into test output.
- `assertPaymentGatewayDrilldown(page, gatewayRequestId)` — follows the gateway request ID into the drilldown view and asserts the correlation chain stays intact.

These helpers are mandatory when adding new payment-path synthetics — do not assert on raw payment payloads.

### APM availability monitors (live)

`tools/demo-guide/octo-availability-monitor.playwright.ts` is uploaded to OCI APM as an availability monitor and runs against the live tenancy on a schedule. It is **not** part of the local automated suite. See Section I.

## F. Coverage Targets

- **Minimum line coverage: 80%** per project rules (`~/.claude/rules/common/testing.md`).
- Each Python project (`shop/`, `crm/`, `services/*/`) is independent and tracks coverage separately.

Generate a coverage report locally for one service:

```bash
cd shop
python3 -m pytest --cov=server --cov-report=term-missing --cov-report=html
# HTML report in shop/htmlcov/index.html
```

```bash
cd crm
python3 -m pytest --cov=server --cov-report=term-missing
```

For a per-service module (example):

```bash
cd services/remediator
python3 -m pytest --cov=. --cov-report=term-missing
```

## G. CI

### GitHub Actions workflows (`.github/workflows/`)

| Workflow | Trigger | What it gates |
|----------|---------|---------------|
| `security-gates.yml` | PR on `shop/server/**`, `crm/server/**`, `deploy/**`, requirements/package manifests; push to `main` | Bandit SAST, pip-audit, Ruff `S` security rules, Gitleaks secret scan, Terraform `fmt` + tflint, Trivy config scan on shop+crm, Checkov IaC scan |
| `mkdocs-deploy.yml` | Push to `main` on `site/**`, `mkdocs.yml`, `requirements-docs.txt`; manual dispatch | `mkdocs build --strict`, upload pages artifact, deploy to GitHub Pages |

`security-gates.yml` runs Bandit, pip-audit, and Ruff in a matrix over `shop` and `crm`, plus a single-job secret scan, Terraform lint, container config scan, and IaC scan. A PR cannot merge with red security gates.

### Pre-commit / local guards

The repository relies on the in-CI Gitleaks scan plus the local `deploy/verify.sh` and the contract suite (`tests/test_documentation_architecture_closure.py`) for forbidden-token detection. Before committing:

- Run `bash deploy/verify.sh` if you touched `deploy/`.
- Run `python3 -m pytest -q tests/test_documentation_architecture_closure.py` if you touched `site/`.
- Confirm no `.env*`, `*.pem`, `*.key`, wallet files, or Playwright session artifacts are staged.

## H. Writing New Tests

### Structure

Use the **AAA** pattern (Arrange-Act-Assert):

```python
def test_login_emits_success_span_and_metric(client, span_capture):
    # Arrange
    payload = {"username": "demo", "password": "demo"}

    # Act
    response = client.post("/auth/login", json=payload)

    # Assert
    assert response.status_code == 200
    assert span_capture.has_span(name="auth.login", status="OK")
    assert span_capture.has_metric("octo.auth.success_count", value=1)
```

### Naming

Test names describe behavior, not implementation:

```text
test_login_emits_success_span_and_metric           # good
test_payment_gateway_returns_correlated_request_id # good
test_login_function                                # bad
test_it_works                                      # bad
```

### Markers

Use `pytest.ini` markers to classify each test:

```python
import pytest

@pytest.mark.unit
def test_calculates_loyalty_points():
    ...

@pytest.mark.integration
def test_order_publishes_to_queue(queue_fixture):
    ...

@pytest.mark.security
def test_login_rate_limit_returns_429():
    ...
```

Available markers (declared in `shop/pytest.ini` and `crm/pytest.ini`):

- `unit` — fast, isolated, no network/DB/OCI
- `integration` — real DB, queue, or local services
- `e2e` — full stack (Playwright/browser)
- `portability` — multi-tenancy + deploy-parameterization regressions
- `security` — auth, secrets, headers

### Assertion granularity

One assertion per behavior, but multiple invariants asserted on the same call site is fine when they describe the same behavior:

```python
# Fine — one behavior ("login success"), three invariants
assert response.status_code == 200
assert response.json()["user"]["role"] == "customer"
assert "Set-Cookie" in response.headers
```

### Mocking boundary

Mock at boundaries — **not** internal logic:

- Mock HTTP clients (`httpx`, `requests`), OCI SDK calls, queue producers, database drivers when running unit tests.
- Do **not** mock your own modules' internal functions just to make a test pass. If a unit is too entangled to test, refactor the unit.

### Synthetic / Playwright tests

- Use the `assertSafe*` helpers when asserting on payment or auth payloads.
- Wait on deterministic selectors (`page.getByRole`, `page.locator`), not arbitrary timeouts.
- Tag scenarios with the persona/journey they represent so failures surface the right runbook.

## I. Deferred Live Checks

Some validations are operator-gated and run only during approved rollout windows against the live tenancy. They are **not** part of the automated suite and do not block local development:

- Live APM Trace Explorer widget verification (visual confirmation that traces land in the expected dashboard widgets).
- Live Log Analytics fresh-row confirmation (a recent timestamp appears in each subscribed source on the production tenancy).
- Public VM / OKE browser E2E against the live deployed surface, executed by the operator with production credentials.
- The `tools/demo-guide/octo-availability-monitor.playwright.ts` monitor uploaded to OCI APM, run on a schedule from APM's monitoring engine.

If a deferred live check is required for a release, the operator runs it from a sanctioned workstation during the rollout window and records the outcome in the rollout log. Do not attempt to embed live tenancy credentials, hostnames, or OCIDs in any test under `tests/`, `shop/tests/`, `crm/tests/`, or `services/*/tests/`.
