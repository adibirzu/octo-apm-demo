# Observability

OCTO APM Demo is a demo project for showcasing OCI Observability service
capabilities in a customer-friendly commerce scenario. The latest walkthroughs
live in [Observability v2](../observability-v2/index.md); this section keeps
the foundational MELTS pages and implementation references.

## Current Overview

The platform emits **MELTS** signals: Metrics, Events, Logs, Traces, and SQL.
The current demo joins those signals across browser RUM, Drone Shop, Enterprise
CRM, the Java payment/app-server sidecar, Oracle ATP, OCI GenAI assistant
flows, OCI APM, OCI Logging, Log Analytics, OCI Monitoring, and Stack
Monitoring / database tooling.

| Pillar | Current demo surface |
|---|---|
| Metrics | OCI Monitoring custom metrics, runtime health, business counters, and alarm-ready query examples. |
| Events | Checkout, payment, load-control, remediation, WAF/API Gateway, Cloud Guard, and attack-lab events. |
| Logs | Structured application logs with `oracleApmTraceId`, token-safe payment fields, assistant LLMetry fields, and parser-ready JSON. |
| Traces | OCI APM service traces, browser RUM sessions, Java App Servers data, checkout spans, login spans, assistant spans, and service-error drill-downs. |
| SQL | Sanitized SQL span metadata, `DbOracleSqlId`, ATP service names, DB Management / Stack Monitoring pivots, and Log Analytics slow-query searches. |

## Correlation Matrix

Every pillar links to the others through stable, reusable identifiers:

| From to | Correlation key |
|---|---|
| RUM to traces | `trace_id`, RUM page action, session id |
| Traces to logs | `TraceId`, `trace_id`, `oracleApmTraceId` |
| Traces to SQL | `DbOracleSqlId`, sanitized DB statement metadata |
| Logs to payment | `Payment Gateway Request ID`, `Transaction ID`, `Order ID` |
| Logs to assistant | `Assistant Session ID`, `Application Hash`, `gen_ai.*` |
| Metrics to alarms | OCI Monitoring MQL and Log Analytics scheduled-rule metrics |

## 360 Observability Dashboard

The `/api/observability/360` endpoint remains the app-facing health summary for
demo operators. It should expose readiness and signal configuration status, not
secret values, live IP addresses, or tenancy-specific identifiers.

```json
{
  "pillars": {
    "apm": { "configured": true, "rum_configured": true },
    "logging": { "configured": true },
    "metrics": { "prometheus": true, "otlp_export": true }
  },
  "circuit_breakers": {
    "crm": { "state": "closed" },
    "workflow_gateway": { "state": "closed" }
  }
}
```

## Latest Demo Assets

- APM saved-query descriptors live under `deploy/oci/apm/saved-queries/` and
  cover checkout, Java payment sidecar, DB slow spans, login, assistant
  LLMetry, service errors, platform workflows, and one-trace drill-down.
- Log Analytics fields, parsers, saved searches, dashboards, and scheduled-rule
  helpers live under `deploy/oci/log_analytics/`.
- The Java sidecar emits OCI APM App Servers data and token-safe payment rail
  spans for verification, authorization, wallet, processor, and network
  outcomes.
- Public docs and diagrams must stay sanitized: use `<OCI_PROFILE>`,
  `<COMPARTMENT_OCID>`, `<APM_DOMAIN_OCID>`, `<LA_NAMESPACE>`, and placeholder
  hostnames instead of resolved infrastructure values.

## Sections

- [Observability v2](../observability-v2/index.md) — current customer demo overview and guided workflows
- [Enhancement Plan](enhancement-plan.md) — rollout sequence for golden flows, APM, Logging, Log Analytics, drilldowns, and DB tooling
- [OCI 360 Development Plan](oci-360-development-plan.md) — phased platform expansion with new services, edge visibility, load control, and runtime coverage
- [MELTS Overview](melts.md) — complete stack with verification paths
- [Traces (APM)](traces.md) — custom spans, distributed tracing, topology
- [Metrics](metrics.md) — Prometheus, OCI Monitoring, business KPIs
- [Logs](logs.md) — OCI Logging SDK, Splunk HEC, trace correlation
- [Security Events](security.md) — MITRE ATT&CK, OWASP, WAF, Cloud Guard
- [RUM](rum.md) — Real User Monitoring with custom events
