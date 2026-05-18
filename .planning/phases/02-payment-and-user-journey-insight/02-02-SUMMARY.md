---
phase: 02-payment-and-user-journey-insight
plan: "02"
subsystem: user-journey
tags: [login, orders, audit-logs, db, apm, log-analytics]

requires:
  - Phase 2 Plan 01 payment rail evidence
provides:
  - Login success/failure span, metric, log, and audit evidence
  - Authenticated user id on order-created audit rows
affects: [shop-auth, shop-orders, tests, docs]

requirements-completed: [JOURNEY-01, JOURNEY-04, PAY-04]
completed: 2026-05-14
---

# Phase 2 Plan 02: Login, Order, CRM, and DB User Evidence Summary

## Accomplishments

- Enriched `auth.login` with workflow/action fields, DB child spans, success
  and failure metrics, structured logs, and success audit rows.
- Successful login audit rows now include authenticated user id, source IP,
  user agent, and trace id.
- Checkout order-created audit rows now use the authenticated user id when a
  checkout is signed in, rather than the customer id.
- Added tests for login observability and authenticated order audit mapping.

## Files Modified

- `shop/server/modules/auth.py`
- `shop/server/store_service.py`
- `shop/tests/test_auth_login_observability.py`
- `shop/tests/test_checkout_idempotency.py`
- `site/drone-shop/checkout.md`
- `site/observability-v2/event-generation-guide.md`

## Verification

- `python3 -m pytest -q shop/tests/test_auth_login_observability.py shop/tests/test_checkout_idempotency.py` - passed.

## Notes

No commits were created in this Codex session.
