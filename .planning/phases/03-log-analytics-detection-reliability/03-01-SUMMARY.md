---
phase: 03-log-analytics-detection-reliability
plan: "01"
subsystem: log-analytics
tags: [saved-searches, dashboards, detection-rules, dry-run, tests]

requires:
  - Phase 2 payment and user journey evidence
provides:
  - Offline-safe Log Analytics apply dry-run
  - Detection-rule metric/dimension contract tests
  - Dashboard payload compile tests
affects: [log-analytics, tests, docs]

requirements-completed: [OBS-04, SEC-01]
completed: 2026-05-14
---

# Phase 3 Plan 01: Detection Rule and Dashboard Reliability Summary

## Accomplishments

- Made `apply_saved_searches_and_dashboards.py` dry-run mode avoid OCI lookup
  calls for saved-search and scheduled-rule upserts.
- Added `tests/test_log_analytics_detection_reliability.py`.
- The new test verifies every `rule-*.sql` file matches the scheduled-rule
  metric alias and dimension metadata.
- The new test compiles dashboard payloads locally and rejects unsupported
  colon-style Log Analytics parameters.

## Files Modified

- `deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py`
- `deploy/oci/log_analytics/README.md`
- `tests/test_log_analytics_detection_reliability.py`

## Verification

- `python3 -m pytest -q tests/test_log_analytics_detection_reliability.py tests/test_log_analytics_attack_assets.py tests/test_observability_asset_contract.py` - passed.

## Notes

No commits were created in this Codex session.
