# OCTO APM Demo

**An end-to-end OCI Observability reference platform — a multi-service drone retail stack instrumented so every browser click, FastAPI request, Spring Boot span, and Oracle ATP query share one trace context.**

[![Docs](https://img.shields.io/badge/docs-mkdocs--material-blue)](https://<github-username>.github.io/octo-apm-demo)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🚀 Deploy in 5–10 minutes

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/adibirzu/octo-apm-demo/releases/download/compute-resource-manager-stack-20260517/octo-compute-stack.zip)

| Path | When to use | How |
|---|---|---|
| **One-click Resource Manager** | First evaluation, no local tooling | Click the **Deploy to Oracle Cloud** button above + fill 3 stack variables |
| **`make` quickstart** | Engineers extending the platform | `cp env.template .env && make doctor && make deploy && make smoke` |
| **Local stack (no OCI)** | First exploration / code reading | `make local-up` then browse `http://localhost:18080` |

Full step-by-step: see **[docs/QUICKSTART.md](docs/QUICKSTART.md)**.

```bash
# Once you have an OCI tenancy + `oci setup config`:
cp env.template .env             # then edit OCI_COMPARTMENT_ID, OCIR_REGION, OCIR_TENANCY, DNS_DOMAIN
make doctor                      # verify local tooling + OCI auth
make tenancy-init                # create OCIR repos + namespaces + bootstrap secrets
make deploy                      # build + push + apply
make smoke                       # validate every observability subsystem
```

`make help` lists every target.

---

OCTO APM Demo is a production-grade demonstration platform for OCI customers, observability practitioners, and developers evaluating Oracle Cloud Infrastructure's MELT-S (Metrics, Events, Logs, Traces, Security) stack. It packages a customer storefront, an enterprise operations CRM, a Java payment sidecar, async/edge/remediation support services, and a shared Oracle Autonomous Transaction Processing (ATP) database into a single deployable estate.

The platform exists to answer one question: *what does "everything correlates" actually look like across OCI Observability?* Every request begins in the browser with a W3C `traceparent`, propagates through Python FastAPI services and a Spring Boot sidecar, lands in OCI APM as a distributed trace, emits structured logs into OCI Logging with `oracleApmTraceId`/`oracleApmSpanId` correlation fields, fans out to OCI Logging Analytics through Service Connector Hub, raises custom metrics in OCI Monitoring, and surfaces in OCI Stack Monitoring for ATP and JVM health. From any view — a RUM session, an APM trace, a Logging Analytics saved search, a Monitoring alarm — an operator pivots to the same correlated evidence using shared IDs.

## Why this project exists

Observability marketing claims are easy. Wiring a real, multi-service application so every signal correlates end-to-end is not. OCTO APM Demo is the working reference:

- A realistic retail user journey (browse, login, cart, checkout, payment authorization) that exercises every OCI Observability surface
- Token-safe payment telemetry demonstrating cross-language trace propagation (Python → Java) without ever capturing PAN, CVV, or wallet payloads
- Source-controlled APM saved queries, Log Analytics parsers, dashboards, detection rules, and Monitoring alarms — all under `deploy/oci/`
- A workshop track (ten hands-on labs) walking practitioners from first trace through chaos drill
- Multiple deployment paths (single-VM Compute, OKE, Helm, Terraform / Resource Manager) so the demo runs anywhere OCI runs

## At a glance — service topology

| Service | Stack | Role |
|---|---|---|
| **OCTO Drone Shop** (`shop/`) | Python FastAPI + Jinja, OCI APM RUM | Customer storefront: catalog, cart, checkout, AI assistant, real-user telemetry |
| **Enterprise CRM Portal** (`crm/`) | Python FastAPI | Operations console: catalog, orders, customers, simulations, observability dashboard, security training |
| **APM Java Demo** (`services/apm-java-demo/`) | Spring Boot 3 + OCI APM Java agent | Payment sidecar populating OCI APM **App Servers** (Apdex, GC, CPU, JVM telemetry); verification + authorization spans on checkout |
| **OTEL Gateway** (`services/otel-gateway/`) | OpenTelemetry Collector | Optional telemetry fan-out and edge collection |
| **Async Worker** (`services/async-worker/`) | Python | Background jobs for catalog hydration and simulation runners |
| **Auto-Remediator** (`services/auto-remediator/`) | OCI Functions | Event-driven auto-remediation triggered by Monitoring alarms and Cloud Guard problems |
| **Edge Fuzz / Container Lab / VM Lab** (`services/`) | Mixed | Attack-lab simulators for security-pivot demonstrations |
| **Shared Oracle ATP** | Autonomous Transaction Processing | Shop, CRM, workflow, assistant events — one database, drill-down across services |

## OCI Observability surface map

The platform exercises every layer of OCI's observability stack. Each signal is instrumented intentionally and every cross-signal pivot is wired:

| Surface | What the demo demonstrates | Where it lives |
|---|---|---|
| **OCI APM** | Distributed traces across Python FastAPI services and the Spring Boot sidecar via W3C `traceparent` + B3 headers; trace explorer; span search; saved queries for checkout, payment sidecar, slow DB, login, assistant LLMetry, service errors | `deploy/oci/apm/`, `shop/server/`, `crm/server/`, `services/apm-java-demo/` |
| **OCI APM RUM** | Browser real-user monitoring with page-load through `fetch`/`XHR` trace propagation; sanitized custom actions; navigation timing tied to backend spans | `shop/server/templates/`, `crm/server/templates/` |
| **OCI Logging** | Durable structured log ingestion via the OCI Logging SDK with `oracleApmTraceId` / `oracleApmSpanId` correlation fields stamped on every log record | `crm/server/observability/logging_sdk.py` and the shop equivalent |
| **OCI Logging Analytics** | Source-controlled custom parsers, fields, saved searches, dashboards, scheduled detection rules, the attack-lab command center, and trace-to-log pivots | `deploy/oci/log_analytics/` |
| **OCI Monitoring** | Custom metrics + alarms (payment success rate, login failures, checkout idempotency violations, RUM error rate) | `deploy/oci/ensure_monitoring.sh`, `shop/server/observability/`, `crm/server/observability/` |
| **OCI Stack Monitoring** | Shared ATP database health and JVM telemetry from the Java sidecar | `deploy/oci/ensure_stack_monitoring.sh` |
| **OCI Service Connector Hub** | Routes OCI Logging log groups into Log Analytics for unified search and dashboarding | `deploy/oci/ensure_log_analytics_connectors.sh` |
| **OCI WAF + Cloud Guard** | Edge-layer events correlated with application traces; auto-remediator consumes Cloud Guard problems and runs scoped fixes | `deploy/oci/ensure_waf.sh`, `deploy/oci/ensure_cloud_guard*.sh`, `services/auto-remediator/` |
| **OCI Vault + Security Zones** | Secret material kept out of source; environment-driven configuration | `deploy/oci/ensure_vault.sh`, `deploy/oci/ensure_security_zones.sh` |

**The correlation promise.** A customer fails checkout. From the RUM session, the operator pivots to the APM trace; from the trace, into the Java App Servers dashboard for the sidecar; from any span, into the matching ATP SQL evidence; from the same trace, into OCI Logging Analytics where every log row carries `oracleApmTraceId`. The Monitoring alarm that fired is linked to the same trace ID. Nothing is fabricated — the IDs match because the SDK and Java agent emitted them together.

Architecture diagrams: [`site/architecture/diagrams/platform-overview.svg`](site/architecture/diagrams/platform-overview.svg) (rendered) and [`site/architecture/diagrams/observability-flow.drawio`](site/architecture/diagrams/observability-flow.drawio) (editable source).

## Get started

The documentation site is the canonical entry point. Direct links by audience:

- **New to the platform?** Start at [Introduction](site/introduction.md) and the [Getting Started overview](site/getting-started/index.md).
- **Want a working stack fast?** Follow [Quickstart](site/getting-started/quickstart.md) and the [Prerequisites](site/getting-started/prerequisites.md) checklist.
- **Deploying to a fresh OCI tenancy?** Use the [New Tenancy bootstrap](site/getting-started/new-tenancy.md).
- **Single-VM private Compute deployment?** See [Compute Deployment](site/getting-started/compute-deployment.md) and `deploy/compute/`.
- **OKE / Kubernetes deployment?** See [OKE Deployment](site/getting-started/oke-deployment.md), `deploy/oke/`, and `deploy/helm/`.
- **Want to understand the architecture first?** Read [Platform Overview](site/architecture/platform-overview.md), [Service Inventory](site/architecture/service-inventory.md), and [Correlation Contract](site/architecture/correlation-contract.md).
- **Want hands-on labs?** Work through the [Workshop](site/workshop/index.md) — ten labs from first trace through chaos drill.

A minimal local stack lives under `deploy/local-stack/` for laptop-scale exploration without an OCI tenancy.

```bash
# Clone and preview the documentation locally
git clone https://github.com/<github-username>/octo-apm-demo.git
cd octo-apm-demo

pip install -r requirements-docs.txt
mkdocs serve
# → open http://127.0.0.1:8000
```

For an OCI deployment, the high-level path is:

```bash
# Configure your tenancy placeholders
export OCIR_REGION=<OCIR_REGION>
export OCIR_TENANCY=<OCIR_TENANCY>
export COMPARTMENT_OCID=<COMPARTMENT_OCID>

# Bootstrap observability primitives (APM, Logging, Log Analytics, Monitoring, Stack Monitoring)
./deploy/bootstrap.sh

# Deploy the application stack (choose Compute, OKE, or Resource Manager)
./deploy/deploy.sh
```

Detailed runbooks: [`deploy/BOOTSTRAP-README.md`](deploy/BOOTSTRAP-README.md), [`deploy/OBSERVABILITY-BOOTSTRAP.md`](deploy/OBSERVABILITY-BOOTSTRAP.md).

## Repository layout

```
octo-apm-demo/
├── shop/                 OCTO Drone Shop — customer storefront (FastAPI + Jinja + RUM)
├── crm/                  Enterprise CRM Portal — operations console (FastAPI)
├── services/             Supporting microservices
│   ├── apm-java-demo/    Spring Boot payment sidecar with OCI APM Java agent
│   ├── otel-gateway/     OpenTelemetry collector
│   ├── async-worker/     Background job runner
│   ├── auto-remediator/  OCI Functions auto-remediation
│   ├── edge-fuzz/        Attack-lab edge simulator
│   ├── container-lab/    Attack-lab container simulator
│   ├── vm-lab/           Attack-lab VM simulator
│   └── ...               browser-runner, cache, load-control, object-pipeline, remediator
├── deploy/               All deployment assets
│   ├── compute/          Single-VM private Compute stack
│   ├── oke/              Raw Kubernetes manifests for OKE
│   ├── k8s/              Additional k8s overlays
│   ├── helm/             Helm chart (octo-apm-demo)
│   ├── terraform/        Infrastructure as code
│   ├── resource-manager/ OCI Resource Manager stack
│   ├── local-stack/      docker-compose for laptop-scale runs
│   ├── oci/              OCI service bootstrap scripts (APM, Logging, LA, Monitoring, etc.)
│   ├── vm/, wizard/      VM and wizard-driven flows
│   └── bootstrap.sh, deploy.sh, destroy.sh, verify.sh
├── site/                 mkdocs-material documentation source
│   ├── architecture/     Platform overview, service inventory, correlation contract, diagrams
│   ├── getting-started/  Quickstart, prerequisites, deployment options
│   ├── observability/    APM, RUM, Logging, Log Analytics, Monitoring, Stack Monitoring guides
│   ├── observability-v2/ Current single-journey observability overview
│   ├── operations/       Runbooks
│   ├── workshop/         Ten hands-on labs
│   ├── crm/, drone-shop/ Per-service docs
│   └── integrations/, testing/
├── tests/                Cross-service integration and end-to-end tests
├── tools/                Operator utilities
├── hooks/                mkdocs build hooks (repo-variable substitution)
├── mkdocs.yml            Documentation site configuration
└── LICENSE               MIT
```

## Documentation site

Full documentation is published at **https://&lt;github-username&gt;.github.io/octo-apm-demo** and is built from `site/` via GitHub Actions (`.github/workflows/mkdocs-deploy.yml`). The mkdocs-material configuration lives in `mkdocs.yml`. To preview locally, run `mkdocs serve` after installing `requirements-docs.txt`.

## Status & license

- **Continuous integration:** `.github/workflows/mkdocs-deploy.yml` builds and publishes the documentation site on push to `main`. `.github/workflows/security-gates.yml` runs security scanning gates.
- **License:** [MIT](LICENSE) — Copyright (c) 2026 OCTO APM Demo Contributors.
- **Contributing:** Issues and pull requests welcome. Operational and architectural conventions are documented under `site/architecture/` and `site/operations/`.

<!-- VERIFY: Final published documentation URL on GitHub Pages -->
