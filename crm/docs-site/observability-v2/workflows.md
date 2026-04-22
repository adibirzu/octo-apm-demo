# Golden workflows

Six logical flows that every dashboard, alarm, and playbook groups on.

| `workflow_id` | Purpose | Typical steps |
| --- | --- | --- |
| `browse-catalog` | Public storefront browse | `/shop`, `/api/products` |
| `add-to-cart` | Session write path | `/api/cart` |
| `checkout` | Cross-service, DB-heavy | Shop → CRM customer sync → orders → payments → shipments |
| `order-history` | Reads across Shop + CRM | `/api/orders/history` |
| `crm-lead-capture` | CRM-only, DB heavy | CRM leads + customers |
| `admin-analytics` | Slow aggregates | `/api/analytics`, `/api/campaigns` |

## Mapping

Implemented in `server/observability/workflow_context.py`. Each rule is a
regex → `(workflow_id, step)`. OTel spans get `workflow.id` +
`workflow.step` attributes, and logs are enriched via
`log_enricher.WorkflowLogEnricher`.

Extending: add a tuple to `DEFAULT_RULES` or pass `extra_rules` to the
middleware. Never rename an existing id — Log Analytics searches, alarms,
and Coordinator playbooks reference it as a stable key.
