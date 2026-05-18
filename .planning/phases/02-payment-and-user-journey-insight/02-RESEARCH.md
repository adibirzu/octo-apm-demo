# Phase 2: Payment and User Journey Insight - Research

**Date:** 2026-05-14

## Findings

- Payment simulation is already split into a Python gateway emulator, optional
  Java sidecar verification/authorization, safe transaction persistence, and
  response payloads for checkout/Admin pivots.
- Java request filters already read `X-Request-Id`, `X-Workflow-Id`, and
  `X-Workflow-Step`, but the Python Java client did not explicitly set those
  headers for payment calls.
- Gateway step spans/logs already carry `component`, `peer.service`, and
  `payment.component`, but `PaymentGatewayStep.response_fields()` only exposed
  name/phase/status/latency/details.
- Checkout creates orders with `user_id`, but `place_order()` wrote
  `audit_logs.user_id` from the customer id. That weakens user-to-order DB
  joins.
- Password login starts an `auth.login` span and updates `last_login`, but it
  does not currently emit enough success/failure logs, metrics, audit rows, or
  DB sub-spans for fast Log Analytics troubleshooting.

## Source Files Read

- `shop/server/modules/shop.py`
- `shop/server/modules/auth.py`
- `shop/server/store_service.py`
- `shop/server/modules/payment_gateway_simulation.py`
- `shop/server/modules/payments/checkout_workflow.py`
- `shop/server/modules/payments/gateway_emulator.py`
- `shop/server/modules/java_app_server.py`
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java`
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/PaymentRailSimulator.java`
- `shop/tests/payments/test_gateway_emulator.py`
- `shop/tests/payments/test_checkout_payment_workflow.py`
- `shop/tests/test_java_app_server_client.py`
- `shop/tests/test_checkout_idempotency.py`
- `shop/tests/e2e/payment-gateway-trace.spec.ts`

## Constraints

- Keep public docs and artifacts sanitized.
- Do not run live OCI mutation or deployment from this phase.
- Preserve existing VM/OKE peer-runtime assumptions.
