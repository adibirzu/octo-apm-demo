# Service Inventory

Every service the platform ships, what it does, where its source lives,
and which correlation-contract fields it emits.

## Application services

| Service | Source | Public URL | OTel `service.name` |
|---|---|---|---|
| Drone Shop | `shop/` | `https://shop.${DNS_DOMAIN}` | `octo-drone-shop` |
| Enterprise CRM Portal | `crm/` | `https://crm.${DNS_DOMAIN}` | `enterprise-crm-portal` |
| Workflow Gateway (Go) | `shop/services/workflow-gateway/` | internal | `octo-workflow-gateway` |

## Platform services (OCI 360)

| # | Service | Source | Purpose |
|---|---|---|---|
| 1 | `octo-otel-gateway` | `services/otel-gateway/` | Central OTel Collector. Every app exports OTLP here; single egress to OCI APM. |
| 2 | `octo-load-control` | `services/load-control/` | Named workload-profile orchestrator. 12 profiles, run ledger, REST API, OCI Events. |
| 3 | `octo-edge-gateway` | `deploy/terraform/modules/api_gateway/` | OCI API Gateway Terraform module with route policies for `/api/public/*`, `/api/partner/*`, `/api/admin/*`. |
| 3a | `octo-edge-fuzz` | `services/edge-fuzz/` | 6-category forged-request burst executor for the `edge-auth-failure-burst` profile. |
| 4 | `octo-browser-runner` | `services/browser-runner/` | Playwright journey runner — real Chromium for genuine RUM signal. |
| 5 | `octo-async-worker` | `services/async-worker/` | Redis-Streams consumer with retry+DLQ. `EventPublisher` is the producer library shop+CRM will import. |
| 6 | `octo-cache` | `services/cache/` | Redis 7 + instrumented Python client. `cache.hit`/`cache.miss`/`cache.namespace` span attributes. |
| 7 | `octo-object-pipeline` | `services/object-pipeline/` | OCI Object Storage event → handler → outcome event. Ships invoice + image handlers. |
| 8a | `octo-container-lab` | `services/container-lab/` | K8s Jobs: CPU, memory, disk stress. Trips HPA + alarms. |
| 8b | `octo-vm-lab` | `services/vm-lab/` | cloud-init + systemd-wrapped stress-ng on a dedicated VM. |
| 9 | `octo-remediator` | `services/remediator/` | Alarm-driven recovery. Tier-gated playbooks (LOW auto, MEDIUM conditional, HIGH approval). |

## Placement By Deployment Type

| Component | OKE | Two-instance Compute | Unified VM |
|---|---|---|---|
| Drone Shop | `octo-drone-shop` Deployment + public LB Service | `octo-compute.service` on the private Shop VM | local app process/container |
| Enterprise CRM Portal | `enterprise-crm-portal` Deployment + public LB Service | `octo-compute.service` on the private CRM VM | local app process/container |
| Java APM sidecar | sidecar/Deployment option for App Server and JVM metrics | `octo-java-apm` Podman container on the Shop VM | optional local sidecar |
| Workflow Gateway | `octo-workflow-gateway` Deployment/Service | `octo-workflow-gateway` Podman container on the Shop VM | optional local service |
| Browser Runner | Kubernetes Job launched by load-control | local Playwright E2E against public hosts | local Playwright E2E |
| Load Control | service Deployment when enabled | not currently deployed on private Compute | optional local service |
| Remediator | service Deployment when enabled | not currently deployed on private Compute | optional local service |
| OTel Gateway | collector Deployment when enabled | not required; apps export directly to OCI APM | optional collector |
| Langfuse | low-resource `octo-langfuse` namespace on OKE | external `lf.octodemo.cloud` used by live Shop | optional external |

The May 11, 2026 `emdemo` live Compute deployment currently runs Shop, CRM,
the Java APM sidecar, and the Workflow Gateway. The OKE manifests cover the
same app/service contracts, but the target OCTO project VCN still needs a new
or selected OKE cluster before those manifests can be applied there.

## Tooling

| Tool | Path | Purpose |
|---|---|---|
| Traffic generator | `tools/traffic-generator/` | Synthetic user population — realistic distributions, OTLP-instrumented. |
| LA saved searches | `tools/la-saved-searches/` | APM ↔ LA round-trip dashboards + smoke test. |
| Workshop verifiers | `tools/workshop/` | Per-lab pass/fail scripts + `certify.sh`. |
| Provisioning wizard | `deploy/wizard/` | Interactive TUI — discovery + plan + dispatch. |
| Deploy verifier | `deploy/verify.sh` | Provisioning surface smoke: shell, plain YAML, Helm render/lint, JSON, terraform fmt + validate, compose, pre-flight, mkdocs, pytest, template smoke. |

## Correlation contract coverage

Every service emits the **same** identity fields, per
[correlation-contract](correlation-contract.md):

- `trace_id` + `span_id` on every span (OTel)
- `oracleApmTraceId` on every log record
- `request_id` on every inbound + outbound HTTP call
- `workflow_id` on business-flow spans + logs
- `run_id` **when** originated by `octo-load-control` or `octo-remediator`

## Event namespace

OCI Events emitted by the platform follow
`com.octodemo.<service>.<noun>.<verb>`:

| Prefix | Emitter |
|---|---|
| `com.octodemo.drone-shop.order.*` | Shop order state machine (payments) |
| `com.octodemo.load-control.run.*` | Load-control run lifecycle |
| `com.octodemo.remediator.run.*` | Remediator run lifecycle |
| `com.octodemo.object-pipeline.*.processed` | Object-pipeline per-bucket handler |
| `com.octodemo.async-worker.*` | Future: async-worker DLQ escalations |

## Validation surfaces

| Surface | Scope |
|---|---|
| `python3 -m pytest -q tests/test_unified_deploy_surface.py` | Deploy/docs invariants for the unified repo |
| `python3 -m pytest -q deploy/wizard/tests/test_plan.py` | Provisioning wizard plan composition |
| `bash deploy/verify.sh` | Shell, plain YAML/JSON, Helm render + lint, terraform fmt, compose, pre-flight, mkdocs, pytest, template smoke |
| `tests/e2e/*.spec.ts` | Deployed-tenancy smoke for cross-service, SSO, and optional full-platform coverage |
