# Observability v2

End-to-end correlation of Shop, CRM, DB, WAF, APM, RUM, Log Analytics,
OCI GenAI assistant telemetry, and optional Langfuse LLMetry comparison,
feeding the OCI Coordinator for incident-driven, approval-gated
auto-remediation.

## Pages

- [Golden workflows](workflows.md)
- [Chaos playbook (CRM-only)](chaos-playbook.md)
- [Log Analytics dashboards](log-analytics-dashboards.md)
- [APM drill-down](apm-drilldown.md)
- [Drone assistant LLMetry](../drone-shop/assistant.md)
- [Demo Storyboard and Attack Lab](demo-storyboard-attack-lab.md)
- [Auto-remediation flow](autoremediation-flow.md)
- [Security + WAF observability](waf-observability.md)
- [Demo script](demo-script.md)

## One-paragraph overview

Every request is tagged with `trace_id`, `request_id`, and a logical
`workflow_id`. Buying flows add RUM action names, payment metadata, SQL IDs,
and CRM sync fields. Assistant flows add `assistant.session_id`,
`llm.prompt.hash`, `llm.response.hash`, `gen_ai.*` token fields, and optional
Langfuse mapping attributes. All logs (app, DB audit, WAF, chaos-audit) flow
through a parser that emits the same field names in Log Analytics. Saved
searches fan out and re-join on those keys. The Coordinator reads them via
dedicated MCP tools, proposes remediation playbooks, and only for tier-low
actions executes them automatically.
