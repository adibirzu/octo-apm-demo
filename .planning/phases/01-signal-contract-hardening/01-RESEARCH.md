# Phase 1: Signal Contract Hardening - Research

**Date:** 2026-05-14
**Status:** Complete

## Scope Reviewed

- Correlation contract and service inventory docs.
- Shop and CRM FastAPI middleware, OTel setup, structured logging, and OCI
  Monitoring publishers.
- Java payment app-server OTel support and structured payment logs.
- Python support-service telemetry helpers.
- APM saved-query assets and Log Analytics fields, parsers, searches, and
  dashboards.

## Findings

### FastAPI Application Signals

- Shop and CRM both have FastAPI OTel instrumentation with safe header capture,
  header sanitization, SQL/HTTP instrumentation, and request middleware.
- Shop request middleware already enriches spans/logs with workflow and
  purchase journey fields such as `shop.journey_id`, `shop.session_id`,
  `browser.trace_id`, `enduser.action`, `checkout.step`, and `payment.method`.
- CRM request middleware creates explicit spans for `middleware.entry`,
  `auth.check`, `request.validate`, and `response.finalize`, but its request
  logs are thinner than Shop and should add workflow/page/request-id context.
- `push_log` in both Shop and CRM stamps trace/span and service metadata, but
  request-id enrichment should use the current `RequestIdMiddleware` context so
  logs carry `request_id` even when callers omit it.

### Log Analytics Field Mapping

- Shop and CRM logging SDKs already emit dotted fields and underscore aliases
  for many APM/Log Analytics pivots.
- Shop has broader payment/Java aliases than CRM. CRM includes payment aliases
  needed for order sync and Admin views, but should be checked against the
  reuse map and parser assets before adding any field.
- `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json` and
  `octo-apm-correlation-fields.json` are the source for reuse-first mapping.
- Saved searches cover checkout, auth, GenAI, service errors, service health,
  OKE correlation, ONM ingestion, and payment/security triage.

### Java Sidecar

- Java initializes a local OpenTelemetry SDK exporter to OCI APM and extracts
  W3C `traceparent`.
- Structured Java events print JSON to stdout with `trace_id`, `span_id`,
  `oracleApmTraceId`, `oracleApmSpanId`, `service_name`, and
  `service_namespace`.
- Java payment simulation emits card, wallet, processor, network, antifraud,
  AVS/CVV, 3DS, gateway, and token-safe fields.
- Java should also be checked for `request_id`, `workflow_id`, dotted
  `service.name`, `service.namespace`, `deployment.environment`, and
  consistent payment aliases where parser promotion expects them.

### Support Services

- Async worker, load-control, object-pipeline, remediator, and edge-fuzz have
  local telemetry helpers with mostly duplicated OTel setup.
- These helpers set `service.name`, `service.version`, `service.namespace`,
  `deployment.environment`, `cloud.provider`, and `oci.demo.stack`, but not all
  include `service.instance.id`.
- `script_span` helpers accept arbitrary attributes and force flush on exit.
  They should consistently preserve `run_id`, `workflow_id`,
  `request_id`, and service metadata when supplied.

### OCI Monitoring

- Shop and CRM OCI Monitoring publishers use `OCI_MONITORING_NAMESPACE`
  defaulting to `octo_apm_demo`.
- Both resolve region from `OCI_REGION`, then `OCI_REGION_ID`, then APM
  endpoint, then Phoenix fallback.
- Metrics use low-cardinality dimensions: `serviceName`, `environment`,
  `runtime`, and `instanceId`.

### APM Assets

- Saved-query assets exist for checkout, payment Java sidecar, DB slow spans,
  login/auth, assistant GenAI LLMetry, service errors, platform workflows, and
  trace drilldown.
- Phase 1 should add root tests that verify these query assets remain present,
  named, and tied to the service/field contract.

## Validation Architecture

- Contract tests should check source behavior and asset schemas, not only file
  existence.
- Tests should favor field presence and parser/query compatibility assertions:
  `trace_id`, `span_id`, `oracleApmTraceId`, `request_id`, `workflow_id`,
  `service.name`, `service.namespace`, `deployment.environment`, payment
  gateway fields, and `octo_apm_demo`.
- Tests should be local and safe; live OCI ingestion validation belongs to a
  later deployment phase.

## Risks

- Middleware order matters. Request-id context must be read from the existing
  request middleware instead of adding another competing ID generator.
- Log Analytics fields are case/display-name sensitive. Adding aliases without
  parser/search updates can create false confidence.
- Support-service telemetry duplication can drift. A shared helper is useful
  only if it fits package boundaries and does not add brittle import paths.
- Java stdout JSON must remain parser-friendly and must not rely only on SLF4J
  text logs.

## Recommendation

Plan Phase 1 as four executable tracks:

1. Add source-level signal contract inventory tests and update the contract docs
   with the exact enforcement points.
2. Harden Shop and CRM request/log enrichment and targeted tests.
3. Harden Java and support-service resource/log/span identity and tests.
4. Validate APM, Log Analytics, and Monitoring assets with root tests and docs.

## RESEARCH COMPLETE
