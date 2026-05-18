# Phase 5: Admin AI and Secure Operations - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning
**Source:** GSD autonomous smart-discuss fallback, roadmap, admin coordinator, assistant, workflow gateway, and customer templates

<domain>
## Phase Boundary

Phase 5 hardens GenAI, Select AI, DB Query Lab, OCI Coordinator, and admin
operations so they remain admin-only, scoped to `octo-apm-demo`, observable in
APM/Log Analytics/LLMetry/Langfuse, and separated from the customer storefront.

This phase covers `JOURNEY-03`, `SEC-02`, `SEC-03`, `SEC-04`, `AI-01`,
`AI-02`, and `AI-03`.
</domain>

<decisions>
## Implementation Decisions

### Admin Surface Only
- OCI Coordinator stays in the Admin/CRM app under `/api/admin/coordinator/*`.
- Workflow Gateway, Query Lab, and Select AI proxy calls remain admin/internal
  authenticated and are host-bound away from the public storefront.

### OCTO Scope Only
- Coordinator answers only OCTO APM Demo admin pages, resources, traces, logs,
  ATP, payment, security, and GenAI telemetry questions.
- Broad tenancy, unrelated project, and external-domain questions are refused.

### Safe AI Observability
- LLMetry and Langfuse correlation use hashes, lengths, token counts, session
  IDs, trace IDs, guardrail outcomes, and provider/model labels.
- Raw prompts and responses stay out of logs unless explicitly redacted and
  enabled for a controlled demo.

### the agent's Discretion
- The executor may add tests and lightweight source hardening where admin-only
  boundaries, host scope, or customer-safe copy are ambiguous.
</decisions>

<code_context>
## Existing Code Insights

### Admin Coordinator
- `crm/server/modules/coordinator.py` already requires admin auth, checks host,
  scopes topics, logs decisions, and emits coordinator spans.
- Tests exist in `crm/tests/test_admin_coordinator.py`.

### Assistant and LLMetry
- `shop/server/assistant_service.py` gates the assistant through admin/internal
  auth, uses OCI GenAI when configured, records LLMetry events, and stores
  sanitized conversation metadata.
- `shop/server/observability/llmetry.py` hashes prompt/response content and
  emits Langfuse-compatible span attributes.

### Workflow Gateway
- `shop/server/modules/workflow_gateway.py` proxies Query Lab and Select AI to
  the private gateway with admin/internal auth and trace propagation.
- Before this phase, it did not also enforce the admin host boundary.

### Customer UX
- `shop/server/templates/dashboard.html` and `shop/server/templates/shop.html`
  already describe fake demo data and observability signals.
- A small amount of customer-facing copy still used backend wording.
</code_context>

<specifics>
## Specific Ideas

- Make Coordinator allowed-host logic dynamic for `admin.<DNS_DOMAIN>` and
  configured `CRM_BASE_URL`.
- Add explicit guardrail metadata to coordinator responses, spans, and logs.
- Add host-bound protection to the Workflow Gateway admin labs.
- Remove backend-oriented copy from customer-visible login/shop surfaces.
- Extend capability inventory for admin coordinator auth/scope/log fields.
</specifics>

<deferred>
## Deferred Ideas

- Live OCI GenAI, Select AI, Langfuse, and APM domain verification require
  current emdemo credentials and an approved live validation window.
</deferred>
