---
phase: 02-payment-and-user-journey-insight
plan: "01"
subsystem: payment
tags: [checkout, payment-gateway, java-sidecar, apm, log-analytics]

requires:
  - Phase 1 signal contract hardening
provides:
  - Safe payment component labels in gateway workflow payloads
  - Java sidecar request/workflow header propagation
  - Distinct timeout final gateway status
affects: [shop, java-sidecar-client, payment-gateway, tests, docs]

requirements-completed: [PAY-01, PAY-02, PAY-03, PAY-04, JOURNEY-02]
completed: 2026-05-14
---

# Phase 2 Plan 01: Payment Rail and Java Span Evidence Summary

## Accomplishments

- Added safe `component`, `component_label`, and `peer_service` fields to
  gateway step response payloads so checkout/Admin evidence can name Google
  Pay Gateway, Apple Pay Gateway, Visa/Mastercard networks, Java processor,
  and antifraud verification components.
- Preserved `timeout` as a distinct final gateway status instead of folding all
  non-authorized outcomes into `declined`.
- Added Java sidecar propagation for `X-Request-Id`, `X-Workflow-Id`, and
  `X-Workflow-Step`, alongside existing W3C/B3 trace context.
- Updated focused tests for gateway component labels, timeout final status, and
  Java sidecar workflow headers/log fields.

## Files Modified

- `shop/server/modules/payments/gateway_emulator.py`
- `shop/server/modules/java_app_server.py`
- `shop/tests/payments/test_gateway_emulator.py`
- `shop/tests/payments/test_checkout_payment_workflow.py`
- `shop/tests/test_java_app_server_client.py`
- `site/drone-shop/checkout.md`
- `site/observability-v2/event-generation-guide.md`
- `services/apm-java-demo/README.md`

## Verification

- `python3 -m pytest -q shop/tests/payments/test_gateway_emulator.py shop/tests/payments/test_checkout_payment_workflow.py shop/tests/test_java_app_server_client.py` - passed.

## Notes

No commits were created in this Codex session.
