# Golden workflows

Six logical flows that every dashboard, alarm, and playbook groups on.

| `workflow_id` | Purpose | Typical steps |
| --- | --- | --- |
| `browse-catalog` | Public storefront browse | `/shop`, `/api/products` |
| `add-to-cart` | Session write path | `/api/cart` |
| `checkout` | Cross-service, DB-heavy | Shop → Java app-server payment simulator → CRM customer sync → orders → payments → shipments |
| `order-history` | Reads across Shop + CRM | `/api/orders/history` |
| `crm-lead-capture` | CRM-only, DB heavy | CRM leads + customers |
| `admin-analytics` | Slow aggregates | `/api/analytics`, `/api/campaigns` |
| `demo-storyboard` | Guided lab journey | Open shop → add drone → dummy card authorization → support ticket |
| `attack-lab` | Security investigation path | Admin trigger → WAF/app entry → Java sidecar → SQL error → OSQuery evidence |

## Mapping

Implemented in `server/observability/workflow_context.py`. Each rule is a
regex → `(workflow_id, step)`. OTel spans get `workflow.id` +
`workflow.step` attributes, and logs are enriched via
`log_enricher.WorkflowLogEnricher`.

Extending: add a tuple to `DEFAULT_RULES` or pass `extra_rules` to the
middleware. Never rename an existing id — Log Analytics searches, alarms,
and Coordinator playbooks reference it as a stable key.

For the private demo, the Admin page controls must emit these same workflow fields
in spans and logs. The Demo Storyboard and Attack Lab are designed to
produce browser RUM actions, Python spans, Java app-server spans, ATP SQL
spans, structured app logs, and Log Analytics rows tied together by
`oracleApmTraceId`.
