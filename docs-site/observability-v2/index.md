# Observability v2

End-to-end correlation of Shop, CRM, DB, WAF, APM, and Log Analytics,
feeding the OCI Coordinator for incident-driven, approval-gated
auto-remediation.

## Pages

- [Golden workflows](workflows.md)
- [Chaos playbook (CRM-only)](chaos-playbook.md)
- [Security + WAF observability](waf-observability.md)

### Shop-side observability (cross-reference)

Log Analytics dashboards, APM drill-down, auto-remediation flow, and the
end-to-end demo script live on the shop's docs site since the shop owns
the ingestion pipeline:

- [Log Analytics dashboards](https://adibirzu.github.io/octo-drone-shop/observability-v2/log-analytics-dashboards/)
- [APM drill-down](https://adibirzu.github.io/octo-drone-shop/observability-v2/apm-drilldown/)
- [Auto-remediation flow](https://adibirzu.github.io/octo-drone-shop/observability-v2/autoremediation-flow/)
- [Demo script](https://adibirzu.github.io/octo-drone-shop/observability-v2/demo-script/)

## One-paragraph overview

Every request is tagged with `trace_id`, `request_id`, and a logical
`workflow_id`. All logs (app, DB audit, WAF, chaos-audit) flow through a
parser that emits the same field names in Log Analytics. Saved searches
fan out and re-join on those keys. The Coordinator reads them via
dedicated MCP tools, proposes remediation playbooks, and — only for
tier-low actions — executes them automatically.
