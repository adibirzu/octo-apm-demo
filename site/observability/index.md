# Observability

The OCTO Drone Shop implements **MELTS** — a complete observability stack covering Metrics, Events, Logs, Traces, and Security. All pillars are correlated through shared trace IDs and `oracleApmTraceId` for end-to-end visibility.

## MELTS Correlation Matrix

Every pillar links to every other pillar through shared identifiers:

| From → To | Correlation Key |
|---|---|
| Traces → Logs | `oracleApmTraceId` in every log entry |
| Traces → Metrics | Request counting increments business counters |
| Traces → Security | Security events create spans AND log entries |
| Logs → Security | Security events table stores `trace_id` |
| Metrics → Alarms | OCI Monitoring MQL queries trigger notifications |

## 360 Observability Dashboard

The `/api/observability/360` endpoint provides a single-pane-of-glass view:

```json
{
  "pillars": {
    "apm": { "configured": true, "rum_configured": true },
    "logging": { "configured": true },
    "metrics": { "prometheus": true, "otlp_export": true }
  },
  "vulnerability_scanning": { "configured": true },
  "circuit_breakers": {
    "crm": { "state": "closed", "failure_threshold": 5 },
    "workflow_gateway": { "state": "closed", "failure_threshold": 3 }
  }
}
```

## Sections

- [MELTS Overview](melts.md) — Complete stack with verification paths
- [Traces (APM)](traces.md) — 50+ custom spans, distributed tracing, topology
- [Metrics](metrics.md) — Prometheus, OCI Monitoring, business KPIs
- [Logs](logs.md) — OCI Logging SDK, Splunk HEC, trace correlation
- [Security Events](security.md) — MITRE ATT&CK, OWASP, WAF, Cloud Guard
- [RUM](rum.md) — Real User Monitoring with custom events
