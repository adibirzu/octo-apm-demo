---
title: Development
---

# Development

Practical guide for contributors and engineers extending `octo-apm-demo` locally. The platform is a
multi-service demo (FastAPI shop + CRM, Spring Boot APM sidecar, Go workflow gateway, Playwright
synthetics, OCI deploy tooling). This page covers how to set everything up, run it, debug it, and
add new code that fits the existing observability and release-gate conventions.

---

## A. Local Development Setup

The repo expects a workstation with the following toolchain. Versions are pinned by the source files
(`requirements.txt`, `pom.xml`, `application.yml`, `go.mod`, `package.json`).

| Toolchain | Version | Used by |
| --- | --- | --- |
| Python | 3.11 | `shop/`, `crm/`, top-level `tests/`, `tools/` |
| Java JDK | 21 (LTS) | `services/apm-java-demo/` (Spring Boot 3.3.5) |
| Maven | 3.9+ | Java sidecar build |
| Go | 1.25+ | `shop/services/workflow-gateway/` |
| Node.js | 20+ | Playwright e2e (`shop/`, `crm/`) |
| Docker / Podman | recent | local-stack regression, image builds |
| k6 | latest | load tests in `shop/k6/`, `crm/k6/` |

### Python environments

Each Python service has its own pinned `requirements.txt` plus a `requirements-dev.txt`. Use one
virtualenv per service so dependency drift stays visible:

```bash
# Shop
cd shop
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# CRM (separate venv — different bcrypt pin, different OTel transitive surface)
cd ../crm
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

The repo-root docs tooling is installed from `requirements-docs.txt`:

```bash
pip install -r requirements-docs.txt
```

Top-level integration tests under `tests/` pull from the shop / CRM venvs depending on which surface
they exercise.

### Java toolchain

```bash
cd services/apm-java-demo
mvn -B clean package         # builds target/apm-java-demo.jar
mvn -B test                  # JUnit gate
```

`pom.xml` pins `<java.version>21</java.version>` and Spring Boot 3.3.5. The build still works under
JDK 17 if 21 is unavailable, but the release gate runs against 21.

### Go workflow gateway

```bash
cd shop/services/workflow-gateway
go build ./...
go test ./...
```

`go.mod` requires `go 1.25`.

### Node.js (Playwright synthetics)

```bash
cd shop
npm install
npx playwright install --with-deps        # browser binaries

cd ../crm
npm install
npx playwright install --with-deps
```

### Editor

VS Code is the most ergonomic option for this codebase:

- **Python** + **Pylance** (Microsoft) — type checking against the FastAPI surfaces
- **Extension Pack for Java** (Microsoft) — Maven + JUnit + Spring Boot
- **Go** (Google) — gopls, vet, test runner
- **YAML** (Red Hat) — for Helm + k8s manifests
- **Mermaid Preview** — for `site/architecture/diagrams/*.mmd`

The repo also includes `.editorconfig`-style conventions (4-space Python, 2-space YAML/JSON/JS).

---

## B. Running Services Locally

You have three options: run each service standalone, run the regression stack via Docker Compose, or
mix (compose for infra + python locally for hot-reload).

### Option 1: Standalone per-service

Each FastAPI app exposes its ASGI app at `server.main:app` and listens on port 8080 in containers.
For local development run uvicorn directly and pick a free port:

```bash
# Shop (from inside shop/ with .venv activated)
cd shop
uvicorn server.main:app --host 127.0.0.1 --port 8080 --reload

# CRM (separate terminal, separate venv)
cd crm
uvicorn server.main:app --host 127.0.0.1 --port 8081 --reload
```

Java sidecar:

```bash
cd services/apm-java-demo
mvn spring-boot:run          # listens on :8080 by default (application.yml)
# To collide-free local run, override:
SERVER_PORT=18091 mvn spring-boot:run
```

Workflow gateway:

```bash
cd shop/services/workflow-gateway
go run ./cmd/workflow-gateway
```

### Option 2: Compose regression stack

The canonical local stack is `deploy/local-stack/docker-compose.test.yml`. It bundles Postgres (as
an ATP stand-in), Redis, the shop, the CRM, and the Java sidecar with port mappings deliberately
shifted so they don't clash with a host-side standalone run:

```bash
cd deploy/local-stack
docker compose -f docker-compose.test.yml up --build
```

| Service | URL |
| --- | --- |
| Shop | `http://localhost:18080` |
| CRM | `http://localhost:18090` |
| Java sidecar | `http://localhost:18091` |
| Postgres | `localhost:15432` (user `octo`, db `octo`) |
| Redis | `localhost:16379` |

Build context for the shop and CRM is the repo root because both Dockerfiles install sibling
packages. Run the compose command from `deploy/local-stack/` so the relative `../..` resolves.

### Option 3: Standalone Python + compose infra

For fast iteration on Python code, start only the data plane via compose and run uvicorn on the
host:

```bash
cd deploy/local-stack
docker compose -f docker-compose.test.yml up -d postgres redis

# Then in shop/ and crm/ venvs:
export DATABASE_URL='postgresql+asyncpg://octo:octo-local-test@localhost:15432/octo'
export OCTO_CACHE_URL='redis://localhost:16379/0'
uvicorn server.main:app --reload --port 8080
```

---

## C. Codebase Tour

A flat map of where things live. Use this as the starting point before you start grepping.

### `shop/` — OCTO Drone Shop (FastAPI)

```
shop/
├── server/
│   ├── main.py                  # FastAPI app factory, router registration, lifespan hooks
│   ├── config.py                # pydantic settings, OCI/IDCS toggles
│   ├── database.py              # async + sync SQLAlchemy engines, seed_data
│   ├── modules/                 # Route packages: auth, sso, catalogue, orders, shipping,
│   │                            # analytics, campaigns, admin, shop, simulation,
│   │                            # dashboard, integrations, services, payments/, public_api,
│   │                            # observability_dashboard, synthetic_users, workflow_gateway
│   ├── middleware/              # tracing.py, metrics_mw.py, chaos.py, geo_latency.py
│   ├── observability/           # otel_setup.py, logging_sdk.py, metrics.py,
│   │                            # correlation.py, workflow_context.py, log_enricher.py,
│   │                            # oci_monitoring.py
│   ├── security/                # headers.py, request_id.py, auth_security.py
│   ├── templates/               # Jinja2 page templates
│   └── static/                  # Static assets served at /static
├── services/workflow-gateway/   # Go service (Oracle workflow proxy, OTel, Prometheus)
├── tests/                       # Pytest suite mirroring server/ layout + e2e/
├── k6/                          # k6 load scripts
├── docs/                        # Per-service mkdocs (also published to site/)
└── Dockerfile                   # uvicorn server.main:app on :8080
```

### `crm/` — Enterprise CRM Portal (FastAPI)

```
crm/
├── server/
│   ├── main.py                  # FastAPI app factory (similar shape to shop)
│   ├── bootstrap.py             # DB bootstrap, seed data
│   ├── config.py
│   ├── database.py + db_compat.py
│   ├── modules/                 # auth, customers, orders, products, shops, invoices,
│   │                            # tickets, reports, admin, files, dashboard, api_keys,
│   │                            # simulation, campaigns, observability_dashboard, …
│   ├── middleware/              # tracing.py, metrics_mw.py, chaos.py,
│   │                            # geo_latency.py, session_gate.py
│   ├── observability/           # otel_setup.py, logging_sdk.py, metrics.py, …
│   ├── security/                # headers, request id, auth helpers
│   ├── order_sync.py            # Cross-service order ingestion from the shop
│   └── shop_catalog_sync.py     # Catalogue ingestion back-channel
├── tests/                       # Pytest, mirrors server/
└── Dockerfile                   # uvicorn server.main:app on :8080
```

### `services/apm-java-demo/` — Java APM sidecar

```
services/apm-java-demo/
├── pom.xml                                      # Spring Boot 3.3.5, Java 21, OTel 1.43
├── src/main/resources/application.yml           # server.port: 8080
├── src/main/java/com/octo/apmdemo/
│   ├── App.java                                 # Spring Boot entrypoint + REST controllers
│   ├── OtelSupport.java                         # Manual span/attribute helpers
│   └── PaymentRailSimulator.java                # Synthetic payment-rail latency profile
├── src/test/java/com/octo/apmdemo/AppTest.java
├── agent-bundle/                                # Optional pre-downloaded OCI APM agent
├── entrypoint.sh                                # Decides whether to attach the agent at runtime
└── Dockerfile                                   # Multi-stage build, runs as uid 10001 on :8080
```

### `services/` — adjacent services

`otel-gateway/`, `async-worker/`, `auto-remediator/`, `browser-runner/`, `cache/`, `container-lab/`,
`edge-fuzz/`, `load-control/`, `object-pipeline/`, `remediator/`, `vm-lab/`. Each ships with its own
`README.md` and (where applicable) Dockerfile + config.

### `deploy/` — infrastructure surfaces

```
deploy/
├── compute/             # Single-VM install: app-compose.yml, install.sh, deploy-apps.sh,
│                        # systemd units, terraform/cloud-init for OCI Compute
├── helm/                # octo-apm-demo Helm chart (values.yaml, templates/)
├── k8s/oke/             # Raw OKE manifests: shop/, crm/, apm-java-demo/, workflow-gateway/, common/
├── local-stack/         # docker-compose.test.yml — regression target
├── oci/                 # OCI tenancy bootstrap, log analytics, monitoring, functions
├── oke/                 # OKE rollout scripts (deploy-oke.sh, build-push-images.sh)
├── resource-manager/    # OCI Resource Manager stack packaging
├── terraform/           # Root TF modules
├── vm/                  # VM-only deploy path
├── wizard/              # Interactive deploy wizard
└── verify.sh            # Offline dry-run gate for everything above
```

### `site/` — mkdocs source

```
site/
├── index.md
├── introduction.md
├── architecture/       # correlation-contract.md, data-model.md, system-design.md, …
├── crm/                # CRM service docs
├── drone-shop/         # Shop service docs
├── getting-started/    # Operator onboarding
├── integrations/
├── observability/      # Telemetry pipeline docs
├── observability-v2/   # Newer iteration of the observability narrative
├── operations/         # Runbooks
├── testing/            # Test strategy
└── workshop/           # Workshop content
```

The `docs/` directory you are reading is published alongside `site/` by mkdocs (see
`mkdocs.yml`).

### `tests/` — repo-level integration

```
tests/
├── e2e/                                                  # Cross-service end-to-end gates
├── test_compute_java_app_server_surface.py
├── test_compute_langfuse_surface.py
├── test_compute_synthetic_users_surface.py
├── test_deployment_parity_release_gates.py
├── test_documentation_architecture_closure.py
├── test_log_analytics_attack_assets.py
├── test_log_analytics_detection_reliability.py
├── test_observability_asset_contract.py
├── test_signal_contract_inventory.py
└── test_unified_deploy_surface.py
```

These tests treat the codebase as a whole — they enforce parity between deploy paths, doc-vs-code
agreement, and the observability contract.

---

## D. Adding a New Feature

The codebase enforces test-driven development plus an observability contract. Walk through this
checklist when you add anything non-trivial.

1. **Write or update tests first.** Decide which suite the feature belongs to:
   - `shop/tests/` or `crm/tests/` for service-scoped behavior
   - `tests/` (repo root) for cross-service contract or deploy parity
   - Mark unit vs integration vs e2e via `pytest.mark` (markers are declared in each `pytest.ini`)
2. **Add the source code.** Place new route packages under `server/modules/<feature>/` and register
   them from `server/main.py`. Keep modules focused; the existing modules average 200–400 LOC.
3. **Add structured logging.** Use `push_log()` from `server.observability.logging_sdk` with the
   standard fields: `request_id`, `workflow_id`, `trace_id`, plus dotted-attribute fields
   (`http.url.path`, `error.type`, etc.). Don't sprinkle `print()` calls — they bypass the OCI
   Logging SDK and break the correlation contract.
4. **Add APM span attributes.** Use `OtelSupport`-style helpers (Python equivalents live in
   `server.observability.otel_setup` and `correlation.py`). Attributes must follow the dotted
   convention (`payment.rail`, `workflow.id`) AND, where the OCI APM UI requires it, a snake_case
   alias (`payment_rail`, `workflow_id`). See `site/architecture/correlation-contract.md`.
5. **Run the local validation gate.** Before pushing:
   ```bash
   bash deploy/verify.sh
   ```
   This runs syntax + YAML + helm lint + terraform validate + mkdocs strict + compose config in one
   pass.
6. **Update the relevant docs page.** Most features touch one of `site/drone-shop/`, `site/crm/`,
   `site/architecture/`, or `site/observability/`. Pages render via `mkdocs build --strict`, so a
   broken cross-link blocks the gate.

---

## E. Code Knowledge Map

The platform maintains a queryable knowledge map of its own source. Every Python class and function,
every Java method, every FastAPI route, every Helm template, every mkdocs page, and every rationale
comment is indexed as a node, with edges that capture imports, route registration, deploy targets,
and doc-to-code references.

### When it earns its keep

- **Tracing a feature's footprint across services.** Find every payment-related route, the spans
  they emit, the tests that cover them, and the docs that describe them in a single query.
- **Finding test coverage gaps.** Identify modules with no inbound edge from any node under
  `tests/`.
- **Surfacing rationale.** Pull every comment tagged as a design rationale next to a given module.
  Useful when you're about to change a "why does this even exist" piece of code.
- **Doc-vs-code drift.** Compare the set of routes declared in `server/modules/**` against the set
  of routes referenced under `site/**`.

### How to regenerate

An AST-extraction step builds a JSON knowledge map of the codebase locally and writes it to a
local build directory (`graph.json`, `graph.html`, a human-readable summary report). The map is
regenerated on demand, not on every commit, because the JSON is tens of megabytes. The
maintainer toolchain includes the generator — see the project README and the per-service
contributor notes for the exact invocation. Generated artefacts are gitignored.

For day-to-day work you do not need to regenerate the map yourself; the indexed summary report
is the human-readable entry point for exploration.

---

## F. Local Validation Gate

These commands are the release gate. CI runs the same set; running them locally first is the
fastest way to avoid a red PR.

### Python test suites

```bash
# Top-level integration / contract tests
python3 -m pytest -q tests/

# Shop service
cd shop && python3 -m pytest -q && cd ..

# CRM service
cd crm && python3 -m pytest -q && cd ..
```

Each suite reads `pytest.ini` (testpaths, async mode, marker definitions). Use `-m unit`,
`-m integration`, `-m e2e`, `-m portability`, or `-m security` to narrow scope.

### Java sidecar

```bash
cd services/apm-java-demo
mvn -B test
```

### Go workflow gateway

```bash
cd shop/services/workflow-gateway
go test ./...
```

### mkdocs strict build

```bash
python3 -m mkdocs build --strict
```

A strict build fails on broken links, missing nav entries, or unresolved Mermaid diagrams. Required
before any docs-touching PR.

### DrawIO XML validation

Architecture diagrams under `site/architecture/diagrams/` are validated for well-formed XML and
schema compliance as part of the YAML category in `deploy/verify.sh`.

### Unified offline gate

```bash
bash deploy/verify.sh
```

Runs every category — syntax, help, pre-flight, YAML, helm, compute, terraform, compose, docs —
without touching a real tenancy. Network-dependency errors are downgraded to warnings so the gate
remains green offline. Exit code `0` = clean, `1` = at least one category failed.

---

## G. Coding Conventions

### Python

- **Formatting:** black (line length 100), isort for import order
- **Linting:** ruff
- **Type hints:** required on all public function signatures, encouraged everywhere
- **Logging:** `push_log()` from `server.observability.logging_sdk` — never `print()`
- **Errors:** explicit exceptions, no bare `except`. Use the global exception handler in
  `server/main.py` as the funnel for unhandled errors.
- **Immutability:** prefer `@dataclass(frozen=True)` and `NamedTuple` for DTOs

### Java

- **Style:** Google Java Style
- **Build:** Maven, single command (`mvn -B clean package`)
- **Spans:** all manual spans go through `OtelSupport`, which enforces the dual dotted +
  snake_case attribute convention

### Go

- `gofmt` + `go vet` (run before commit)
- Use the in-package `internal/telemetry` for span and metric setup; do not import OTel SDK
  directly from `cmd/`

### Tests live next to source

`shop/tests/` mirrors `shop/server/`. `crm/tests/` mirrors `crm/server/`. Each Java module has a
sibling `src/test/java/`. The repo-level `tests/` directory is reserved for cross-service contract
and deploy-parity tests.

### Observability field convention

Span attributes, log fields, and metric labels follow the convention documented in
`site/architecture/correlation-contract.md`. The short version:

- Dotted form for OpenTelemetry semantic alignment (`http.method`, `workflow.id`,
  `payment.rail`)
- snake_case alias where the OCI APM UI needs a column-friendly name
  (`http_method`, `workflow_id`, `payment_rail`)
- Always emit `request_id`, `workflow_id`, and `trace_id` for any request-scoped event

---

## H. Debugging Tips

### Tracing locally without OCI APM

`otel_setup.py` falls back to a `ConsoleSpanExporter` when no APM endpoint is configured. Run the
service without setting `OCI_APM_ENDPOINT` / `OCI_APM_PRIVATE_KEY` and spans will print to stdout.
Filter the noise with `jq` if you also have JSON logging on:

```bash
uvicorn server.main:app --reload 2>&1 | jq -R 'fromjson? // .'
```

### Inspecting structured logs

The Python services emit JSON via `push_log()`. Pipe them through `jq` to slice by correlation:

```bash
docker compose -f deploy/local-stack/docker-compose.test.yml logs -f shop \
  | jq -c 'select(.request_id == "<your-request-id>")'
```

### Finding spans in OCI APM

When debugging against a real tenancy, filter by:

- `service.namespace = octo`
- your username embedded in `request_id` (the request-id middleware tags every request with a
  prefix derived from the authenticated principal where one is present)

This is far faster than scrolling by timestamp.

### Reproducing detection rules

`tests/test_log_analytics_detection_reliability.py` exercises every Log Analytics detection rule
against deterministic fixtures. If a real-world alert is misfiring, run this test with `-k
<rule-name>` to isolate it locally before touching the rule YAML under `deploy/oci/log_analytics/`.

### When the Java sidecar misbehaves

The entrypoint script (`services/apm-java-demo/entrypoint.sh`) decides whether to attach the APM
Java agent based on the contents of `/opt/apm-agent`. To run without the agent, build with an empty
`agent-bundle/` directory; the service boots cleanly and Spring Boot Actuator (`/actuator/health`,
`/actuator/metrics`) remains available on port 8080 for inspection.

### When `verify.sh` fails offline

Network-dependent failures (Terraform provider downloads, container pulls) are downgraded to
warnings — the gate prints them but does not fail. If you see a `FAIL` line, it's a real issue
(syntax, lint, schema). Read the named category section in the output; each category is independent.
