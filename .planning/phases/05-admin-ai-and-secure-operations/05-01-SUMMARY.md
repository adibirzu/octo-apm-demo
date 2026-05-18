---
phase: 05-admin-ai-and-secure-operations
plan: "01"
subsystem: admin-ai
tags: [coordinator, guardrails, admin-hosts, apm, logging]

requires:
  - Phase 1 signal contract
  - Phase 4 deployment parity
provides:
  - Dynamic admin Coordinator host allow-list
  - Explicit Coordinator guardrail metadata
  - Admin-only OCTO scope evidence in responses, spans, and logs
affects: [crm, tests, observability]

requirements-completed: [SEC-03, AI-03]
completed: 2026-05-14
---

# Phase 5 Plan 01: Coordinator Scope and Admin Host Enforcement Summary

## Accomplishments

- Made Coordinator allowed hosts dynamic from `admin.octodemo.cloud`,
  configured `CRM_BASE_URL`, `admin.<DNS_DOMAIN>`, `crm.<DNS_DOMAIN>`, and
  configured OCTO shop/Langfuse resource hosts.
- Preserved local test and development hosts while keeping public storefront
  hosts out of the admin browser surface.
- Added response-level guardrail metadata:
  `admin_only`, `scope_enforced`, `oci_auth_mode`, `allowed_hosts`,
  `raw_prompt_logged=false`, and `allowed_scope`.
- Added Coordinator span/log fields for `coordinator.scope.enforced`,
  `coordinator.auth.mode`, and `oci.auth.mode`.
- Extended admin capability inventory so the Admin UI can describe
  Coordinator scope, auth, and safe logging behavior.

## Files Modified

- `crm/server/modules/coordinator.py`
- `crm/server/modules/observability_dashboard.py`
- `crm/tests/test_admin_coordinator.py`
- `crm/tests/test_observability_capabilities.py`

## Verification

- `python3 -m pytest -q crm/tests/test_admin_coordinator.py` - 7 passed.
- `python3 -m pytest -q crm/tests/test_observability_capabilities.py` - 3 passed.
- `python3 -m pytest -q crm/tests/test_admin_coordinator.py crm/tests/test_observability_capabilities.py crm/tests/test_admin_data_retention.py crm/tests/test_observability_guidance_surfaces.py` - 19 passed.

## Notes

No live OCI GenAI, Select AI, APM, or Log Analytics calls were made. Live
instance-principal and telemetry confirmation remains an operator validation
with approved credentials.
