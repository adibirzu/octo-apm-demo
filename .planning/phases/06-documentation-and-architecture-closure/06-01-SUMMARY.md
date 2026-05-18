---
phase: 06-documentation-and-architecture-closure
plan: "01"
subsystem: architecture
tags: [drawio, diagrams, admin-ai, coordinator, workflow-gateway]

requires:
  - Phase 5 Admin AI and Secure Operations
provides:
  - Layered editable DrawIO sources
  - Admin-only AI architecture documentation
  - Updated SVG preview labels
affects: [docs, diagrams, tests]

requirements-completed: [DOC-01]
completed: 2026-05-14
---

# Phase 6 Plan 01: Layered Architecture and Admin AI Boundary Summary

## Accomplishments

- Added `tests/test_documentation_architecture_closure.py` with assertions for
  layered DrawIO files and Admin-only AI architecture language.
- Added named layers to `platform-overview.drawio`,
  `observability-flow.drawio`, `deploy-topology.drawio`, and
  `private-demo-observability-reference.drawio`.
- Updated platform/system diagrams to show Coordinator, Query Lab, Select AI,
  and GenAI LLMetry on the Admin/CRM path.
- Updated visible SVG preview labels for the changed platform and private
  compute diagram text.
- Updated Coordinator docs with guardrail response fields and safe APM/Log
  Analytics pivot attributes.

## Files Modified

- `tests/test_documentation_architecture_closure.py`
- `site/architecture/platform-overview.md`
- `site/architecture/system-design.md`
- `site/integrations/coordinator.md`
- `site/architecture/diagrams/platform-overview.drawio`
- `site/architecture/diagrams/observability-flow.drawio`
- `site/architecture/diagrams/deploy-topology.drawio`
- `site/architecture/diagrams/private-demo-observability-reference.drawio`
- `site/architecture/diagrams/platform-overview.svg`
- `site/architecture/diagrams/private-demo-observability-reference.svg`

## Verification

- `python3 -m pytest -q tests/test_documentation_architecture_closure.py` - 3 passed.
- XML parse for all public `.drawio` files - passed.

## Notes

No live OCI resources or public routes were changed.
