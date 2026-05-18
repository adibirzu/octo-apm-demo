# Phase 1: Signal Contract Hardening - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning
**Source:** GSD brownfield onboarding and local code/docs review

<domain>
## Phase Boundary

Phase 1 hardens the observability signal contract for the existing OCTO APM
Demo services. The deliverable is not a live deployment or OCI resource apply;
it is source-level hardening and validation so every relevant service can emit
consistent trace, log, metric, service, workflow, request, order, payment, and
database pivots that APM, Log Analytics, Monitoring, and ATP can join.

This phase covers:

- Shop and CRM/Admin FastAPI tracing, structured logging, request IDs,
  workflow context, user/order/payment pivots, and OCI Monitoring metrics.
- Java payment app-server sidecar trace/log fields and token-safe payment
  event evidence.
- Python support-service telemetry helpers used by async-worker, load-control,
  object-pipeline, remediator, and edge-fuzz.
- Versioned APM saved-query and Log Analytics field/search/dashboard assets.
- Automated checks that prevent future contract drift.

This phase does not deploy to VM/OKE, run Terraform apply, alter public load
balancer routing, or create OCI resources. Live OCI validation belongs to later
phases after the code and assets are hardened.
</domain>

<decisions>
## Implementation Decisions

### D-01 Signal Contract Scope
- Phase 1 must cover OBS-01, OBS-02, OBS-03, and OBS-05 from
  `.planning/REQUIREMENTS.md`.
- Treat `site/architecture/correlation-contract.md` as the authoritative field
  specification.

### D-02 Reuse-First Log Analytics Mapping
- Parser/source and log-alias work must prefer existing Log Analytics display
  fields from `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json`
  before adding any new field names.

### D-03 Request and Workflow Context
- Structured application logs must carry `request_id`, `workflow_id`,
  `workflow_step`, `trace_id`, `span_id`, `oracleApmTraceId`, and
  `oracleApmSpanId` when the context exists.
- `X-Request-Id` and request middleware context are the request-id source of
  truth; `X-Correlation-Id` can remain a compatibility correlation ID.

### D-04 Runtime Resource Identity
- All application and support-service telemetry must include `service.name`,
  `service.namespace=octo`, `service.instance.id`,
  `deployment.environment`, `cloud.provider=oci`, and
  `oci.demo.stack=octo-apm-demo`.

### D-05 Monitoring Namespace
- OCI Monitoring custom metrics must use `octo_apm_demo` unless explicitly
  overridden through `OCI_MONITORING_NAMESPACE`.
- Deployment templates for VM and OKE must continue to expose
  `OCI_REGION`, `OCI_COMPARTMENT_ID`, and `OCI_MONITORING_NAMESPACE`.

### D-06 Token-Safe Payment Evidence
- Payment gateway, wallet, card, processor, and Java sidecar fields must remain
  token-safe. Never emit raw PAN, CVV, wallet token, cryptogram, credential, or
  secret values.

### D-07 No Destructive Cloud Actions
- This phase must not run Terraform apply, destroy resources, rotate LB routes,
  or touch non-OCTO resources in emdemo.

### D-08 the agent's Discretion
- The executor may add small helper functions or tests where they reduce
  duplication or make the signal contract enforceable.
- The executor may update docs to reflect exact source behavior discovered
  during implementation, as long as public docs remain sanitized.
</decisions>

<canonical_refs>
## Canonical References

Downstream agents must read these before planning or implementing:

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/INTEGRATIONS.md`
- `.planning/codebase/CONVENTIONS.md`
- `.planning/codebase/TESTING.md`
- `.planning/codebase/CONCERNS.md`
- `site/architecture/correlation-contract.md`
- `site/architecture/service-inventory.md`
- `site/operations/current-status.md`
- `shop/server/observability/logging_sdk.py`
- `crm/server/observability/logging_sdk.py`
- `shop/server/middleware/tracing.py`
- `crm/server/middleware/tracing.py`
- `shop/server/observability/otel_setup.py`
- `crm/server/observability/otel_setup.py`
- `shop/server/observability/oci_monitoring.py`
- `crm/server/observability/oci_monitoring.py`
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java`
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/OtelSupport.java`
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/PaymentRailSimulator.java`
- `deploy/oci/apm/saved-queries/`
- `deploy/oci/log_analytics/fields/`
- `deploy/oci/log_analytics/parsers/`
- `deploy/oci/log_analytics/searches/`
- `deploy/oci/log_analytics/dashboards/`
</canonical_refs>

<validation_architecture>
## Validation Architecture

Local validation for this phase should include:

- Python contract tests for Shop and CRM structured log enrichment.
- Java Maven tests for payment sidecar structured logs and span/log fields.
- Root tests for APM saved query and Log Analytics asset coverage.
- Targeted support-service telemetry tests or source assertions for resource
  attributes, OTLP endpoint handling, and script span attributes.
- `python -m mkdocs build --strict` when public docs are changed.
- `git diff --check` for whitespace and patch hygiene.

Live OCI checks are useful evidence but not required to mark this planning
phase complete. They should be deferred to Phase 4 or a deployment validation
run after code changes are merged and released.
</validation_architecture>
