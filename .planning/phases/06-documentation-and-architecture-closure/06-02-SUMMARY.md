---
phase: 06-documentation-and-architecture-closure
plan: "02"
subsystem: operations-docs
tags: [runbooks, deploy-readiness, log-analytics, onm, connector-hub]

requires:
  - Phase 6 Plan 01
provides:
  - Zero-warning release gate evidence
  - Log Analytics troubleshooting quick pivots
  - Synthetic monitoring nav entry
  - Diagram layer authoring conventions
affects: [docs, mkdocs, tests]

requirements-completed: [DOC-02, DOC-03]
completed: 2026-05-14
---

# Phase 6 Plan 02: Release and Troubleshooting Runbook Summary

## Accomplishments

- Added the current `VERIFY PASSED - 0 warning(s)` source gate result to
  deploy readiness.
- Added Log Analytics troubleshooting quick pivots for Connector Hub live-log
  coverage, OKE ONM ingestion, OKE checkout/payment correlation,
  service trace/log coverage, and GenAI assistant LLMetry.
- Added Synthetic Monitoring to the MkDocs navigation.
- Documented DrawIO layer authoring and flow movement conventions.
- Added an Observability v2 row for Admin AI operations.

## Files Modified

- `site/operations/deploy-readiness.md`
- `site/observability-v2/log-analytics-dashboards.md`
- `site/observability-v2/index.md`
- `site/architecture/diagrams/README.md`
- `mkdocs.yml`
- `tests/test_documentation_architecture_closure.py`

## Verification

- `python3 -m pytest -q tests/test_documentation_architecture_closure.py` - 3 passed.
- `python3 -m mkdocs build --strict` - passed.

## Notes

Live dashboard and saved-search execution still requires approved OCI
credentials and a live validation window.
