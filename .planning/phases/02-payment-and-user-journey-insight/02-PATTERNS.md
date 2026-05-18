# Phase 2: Payment and User Journey Insight - Patterns

## Span and Log Field Pattern

Use the same field names in spans, logs, and persisted metadata:

- `workflow.id`, `workflow.step`
- `request_id`
- `trace_id`, `span_id`, `oracleApmTraceId`, `oracleApmSpanId`
- `auth.user_id`, `auth.username`, `auth.role`
- `shop.session_id`, `shop.journey_id`, `browser.trace_id`, `enduser.action`
- `orders.order_id`, `orders.status`, `orders.payment_status`
- `payment.gateway.request_id`, `payment.gateway.step`,
  `payment.gateway.phase`, `payment.component`, `payment.network`

## Payment Gateway Pattern

Gateway step responses should expose operator-friendly component names without
leaking sensitive values. Step attributes remain the source of truth for APM
and Log Analytics; response fields should mirror safe component labels for UI
and API evidence.

## Java Sidecar Header Pattern

Every payment-sidecar HTTP request should propagate W3C/B3 trace context plus
`X-Request-Id`, `X-Workflow-Id`, and `X-Workflow-Step`. Java uses these headers
for MDC and span attributes.

## Auth Evidence Pattern

Login should emit:

- `auth.login` root span
- `db.query.auth_user_lookup`, `db.query.auth_last_login_update`, and
  `db.query.auth_audit_log` child spans where applicable
- success/failure structured logs
- business login metrics
- `audit_logs` row for successful login with authenticated user id
