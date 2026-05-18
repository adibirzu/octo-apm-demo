---
phase: 05-admin-ai-and-secure-operations
plan: "02"
subsystem: shop-admin-boundary
tags: [workflow-gateway, select-ai, query-lab, customer-ux, security]

requires:
  - Phase 5 Plan 01
provides:
  - Admin host binding for Workflow Gateway labs
  - Public storefront refusal for admin-token browser calls
  - Customer copy without backend/internal wording
affects: [shop, tests, templates]

requirements-completed: [SEC-02, SEC-04, AI-01, AI-02]
completed: 2026-05-14
---

# Phase 5 Plan 02: Admin Workflow Labs and Customer UX Boundary Summary

## Accomplishments

- Added admin surface host enforcement in the Shop Workflow Gateway proxy for
  Query Lab, Select AI, and other private workflow calls.
- Preserved internal-service role access for backend-to-backend calls while
  rejecting browser/admin-token calls from public storefront hostnames.
- Kept localhost, loopback, and `testserver` valid for local tests and
  development.
- Removed customer-visible backend/API wording from the login page.
- Renamed the visible storefront APM status DOM id from `backendChip` to
  `apmChip`.
- Extended tests for public shop host refusal, service-role bypass, and
  customer-safe storefront copy.

## Files Modified

- `shop/server/modules/workflow_gateway.py`
- `shop/server/templates/login.html`
- `shop/server/templates/shop.html`
- `shop/tests/test_workflow_gateway_proxy.py`
- `shop/tests/test_dashboard_demo_page.py`

## Verification

- `python3 -m pytest -q shop/tests/test_workflow_gateway_proxy.py` - 6 passed.
- `python3 -m pytest -q shop/tests/test_dashboard_demo_page.py` - 3 passed.
- `python3 -m pytest -q shop/tests/test_workflow_gateway_proxy.py shop/tests/test_dashboard_demo_page.py shop/tests/test_assistant_guardrails.py shop/tests/test_llmetry.py shop/tests/test_observability_capabilities.py` - 18 passed.

## Notes

This plan keeps admin operational labs available through the Admin surface and
internal service path only; it does not change public Load Balancer routes.
