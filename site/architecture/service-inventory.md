# Service Inventory

Every service the platform ships, what it does, where its source lives,
and which correlation-contract fields it emits.

## Application services

| Service | Source | Public URL | OTel `service.name` |
|---|---|---|---|
| Drone Shop | `shop/` | `https://shop.example.test` (`https://shop.${DNS_DOMAIN}` in portable stacks) | `octo-drone-shop` |
| Enterprise CRM Portal | `crm/` | `https://admin.example.test` (`https://crm.${DNS_DOMAIN}` in portable stacks) | `enterprise-crm-portal` |
| Admin Coordinator surface | `crm/server/modules/coordinator.py` | `https://admin.example.test/admin` | `enterprise-crm-portal` |
| Java payment/app-server sidecar | `services/apm-java-demo/` | private loopback endpoint on the Shop host in Compute | `octo-java-app-server` |
| Workflow Gateway (Go) | `shop/services/workflow-gateway/` | internal | `octo-workflow-gateway` (`octo-workflow-gateway-oke` on OKE) |

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

## APM to Log Analytics Mapping

Use this matrix when checking whether logs can be mapped back to traces. The
preferred join is always APM `TraceId` to Log Analytics `Trace ID`.

| service | APM service/query coverage | log mapping | high-value joins |
| --- | --- | --- | --- |
| `octo-drone-shop` | `checkout-end-to-end`, `login-auth-flow`, `assistant-genai-llmetry`, `service-errors` | `octo-shop-v2` parser maps `trace_id`, `oracleApmTraceId`, `span_id`, `request_id`, `workflow_id` | `Order ID`, `Payment Gateway Request ID`, `Session ID`, `Application Hash`, `User ID` |
| `enterprise-crm-portal` | `checkout-end-to-end`, `login-auth-flow`, `service-errors` | `octo-crm-v2` parser maps the same trace/log contract | `Source Order ID`, `Order ID`, `Request ID`, `DB Statement`, `User ID` |
| `octo-java-app-server` | `payment-java-sidecar`, `service-errors` | Java logs carry MDC `trace_id`/`span_id`; Shop logs also map `java_apm.*` sidecar call results | `Payment Gateway Request ID`, `Transaction ID`, `Response Code`, `Java APM Error Type` |
| `octo-workflow-gateway` / `octo-workflow-gateway-oke` | `db-slow-spans`, `platform-workflows` | Go telemetry emits JSON logs with `oracleApmTraceId`, `trace_id`, `service.name` | `Workflow ID`, `Run ID`, `DB Statement`, `Trace ID` |
| `octo-load-control` | `platform-workflows`, `service-errors` | run ledger and workload dispatch logs should stamp `run_id`, `workflow_id`, and service name | `Run ID`, profile name, target service |
| `octo-browser-runner` | `platform-workflows` plus RUM sessions | pino logs and RUM custom dimensions carry `run_id` and synthetic user metadata | `Run ID`, `synthetic_user_domain`, `Trace ID` from backend responses |
| `octo-async-worker` | `platform-workflows` | Redis stream events carry producer `trace_id`/`span_id`; worker spans preserve `workflow.id` and `run_id` | stream name, event id, DLQ reason, `Trace ID` |
| `octo-cache` | `platform-workflows` when client spans are active | cache client emits span attributes; app logs keep the upstream trace id | cache namespace, hit/miss, latency, `Trace ID` |
| `octo-object-pipeline` | `platform-workflows`, `service-errors` | OCI Events envelope must include `oracleApmTraceId` when an upstream trace exists | object name, bucket, handler result, `Run ID` |
| `octo-edge-fuzz` | `platform-workflows`, `service-errors` | fuzzer requests set `X-Run-Id`; API Gateway/app logs carry request and trace fields | `Run ID`, `API Gateway Request ID`, `Attack ID` |
| `octo-remediator` | `platform-workflows`, `service-errors` | remediation actions should log alarm/run ids and target resource | `Run ID`, alarm id, target service, playbook |
| WAF/API Gateway/OSQuery/Tetragon | Log Analytics-only plus APM trace ids from app pivots | dedicated parsers map edge, host, and eBPF fields | `Request ID`, `API Gateway Request ID`, `Attack ID`, `Instance OCID`, `OSQuery Query` |

Fast troubleshooting searches live in `deploy/oci/log_analytics/searches/`:
`service-trace-log-coverage`, `trace-drilldown`, `checkout-payment-correlation`,
`auth-login-correlation`, `genai-assistant-llmetry`, `service-error-triage`,
`db-slowness-hotspots`, and the attack-lab searches.

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
| `python3 -m pytest -q tests/test_signal_contract_inventory.py` | Source-level signal contract inventory for APM, Log Analytics, and Monitoring drift |
| `python3 -m pytest -q tests/test_unified_deploy_surface.py` | Deploy/docs invariants for the unified repo |
| `python3 -m pytest -q deploy/wizard/tests/test_plan.py` | Provisioning wizard plan composition |
| `bash deploy/verify.sh` | Shell, plain YAML/JSON, Helm render + lint, terraform fmt, compose, pre-flight, mkdocs, pytest, template smoke |
| `tests/e2e/*.spec.ts` | Deployed-tenancy smoke for cross-service, SSO, and optional full-platform coverage |
