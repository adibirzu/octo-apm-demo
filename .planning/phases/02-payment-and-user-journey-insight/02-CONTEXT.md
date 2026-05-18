# Phase 2: Payment and User Journey Insight - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning
**Source:** GSD autonomous smart-discuss fallback, roadmap, requirements, and targeted code scout

<domain>
## Phase Boundary

Phase 2 makes a customer purchase explainable from login and browser action
through cart, checkout, simulated payment gateways, Java sidecar, CRM sync, and
ATP persistence. The deliverable is local source hardening, tests, and GSD
evidence. It does not deploy, change load-balancer routing, run Terraform, or
modify shared OCI resources.

This phase covers `JOURNEY-01`, `JOURNEY-02`, `JOURNEY-04`, `PAY-01`,
`PAY-02`, `PAY-03`, and `PAY-04`.
</domain>

<decisions>
## Implementation Decisions

### Payment Rail Evidence
- Keep Google Pay, Apple Pay, Visa, and Mastercard simulations token-safe and
  field-rich enough for APM and Log Analytics pivots.
- Surface gateway component labels in response payloads as well as spans/logs
  so checkout and Admin views can show Google Pay Gateway, Apple Pay Gateway,
  Visa Payment Network, Mastercard Payment Network, Java processor, and
  antifraud verification components.
- Preserve decline and timeout as distinct simulated outcomes for detection
  rules and troubleshooting.

### User Journey Correlation
- Login, cart, checkout, order, CRM sync, Java sidecar, and DB writes must carry
  stable workflow, request, trace, user, order, payment, and session fields.
- Authenticated checkout audit rows should reference the authenticated user id,
  not the customer id, so DB actions can be joined to orders and users.

### Runtime Safety
- Do not emit raw PAN, CVV, wallet token, wallet cryptogram, provider
  credential, OCI identifier, IP, wallet path, or secret values.
- Do not run live emdemo deployment or destructive OCI operations in this
  phase. E2E public-route checks remain documented/manual if runtime secrets or
  live access are unavailable.

### the agent's Discretion
- The executor may add focused helper functions and contract tests where they
  make the flow observable without changing business behavior.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `shop/server/modules/shop.py` owns checkout orchestration and already creates
  spans for CRM customer sync, cart resolution, user resolution, order
  persistence, payment authorization, payment state persistence, and CRM order
  sync.
- `shop/server/modules/payments/gateway_emulator.py` owns gateway step spans,
  structured logs, safe workflow payloads, and `payment_gateway_events` rows.
- `shop/server/modules/java_app_server.py` owns Python-to-Java sidecar calls.
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java` and
  `PaymentRailSimulator.java` own Java payment verification/authorization
  payloads, structured stdout events, and Java span events.
- `shop/server/modules/auth.py` owns password login and bearer-token issue.

### Established Patterns
- Use `apply_span_attributes` for span fields and `push_log` for Log Analytics
  JSON fields; both preserve the Phase 1 correlation contract.
- Persist token-safe payment rows in `payment_transactions` and
  `payment_gateway_events`.
- Use local pytest/JUnit contract tests rather than live OCI calls for source
  verification.

### Integration Points
- Checkout calls Java `/api/java-apm/payment/verify` and
  `/api/java-apm/payment/authorize`.
- Checkout calls CRM `sync_order_to_crm` after payment state is persisted.
- Admin/observability views use `/api/observability/payment-gateway/events` and
  checkout response gateway payloads as operator pivots.
</code_context>

<specifics>
## Specific Ideas

- Add Java sidecar `X-Workflow-Id`, `X-Workflow-Step`, and request-id headers
  for payment calls so Java server spans/logs can join the checkout flow.
- Add login success/failure logs, metrics, spans, and audit rows.
- Add component labels to payment gateway step response fields.
- Add tests for timeout final-step status, component labels, login audit
  evidence, and authenticated order audit user mapping.
</specifics>

<deferred>
## Deferred Ideas

- Live public VM+OKE E2E execution is deferred unless runtime credentials and
  approved deployment window are available.
- Real provider integration remains out of scope; the project remains a fake
  observability demo shop.
</deferred>
