---
phase: 01-signal-contract-hardening
plan: "01"
subsystem: observability
tags: [apm, log-analytics, monitoring, pytest, documentation]

requires:
  - phase: GSD onboarding
    provides: Brownfield project map and Phase 1 execution plan
provides:
  - Source-level signal contract inventory test
  - Documentation for signal contract enforcement points
  - Core Log Analytics field reuse entries for trace and service joins
affects: [signal-contract, log-analytics, apm, monitoring, phase-1]

tech-stack:
  added: []
  patterns:
    - Source-level contract tests for observability asset drift
    - Reuse-first Log Analytics field inventory checks

key-files:
  created:
    - tests/test_signal_contract_inventory.py
  modified:
    - site/architecture/correlation-contract.md
    - site/architecture/service-inventory.md
    - deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json

key-decisions:
  - "Keep the signal contract guard source-level and dependency-light so it can run in release validation without live OCI credentials."
  - "Record core Trace ID, Span ID, Service Name, and Service Namespace in the reuse map because the planned guard requires those join fields."

patterns-established:
  - "Required MELTS fields are declared once as pytest constants and checked against source assets."
  - "APM saved-query descriptors must keep Log Analytics pivots reviewable in source control."

requirements-completed: [OBS-01, OBS-02, OBS-03, OBS-05]

duration: 5 min
completed: 2026-05-14
---

# Phase 1 Plan 01: Signal Contract Inventory Summary

**Source-level observability contract guard for Shop, CRM, Java payment sidecar, support telemetry, APM saved queries, Log Analytics field reuse, and OCI Monitoring.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-14T10:00:00Z
- **Completed:** 2026-05-14T10:04:28Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `tests/test_signal_contract_inventory.py` to catch removal of trace, span, workflow, service identity, payment, saved-query, Log Analytics, and Monitoring contract fields.
- Replaced the stale enforcement section in `site/architecture/correlation-contract.md` with the current guard and enforcement surfaces.
- Added the signal contract inventory check to `site/architecture/service-inventory.md`.
- Added core trace and service display-name entries to `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json`.

## Task Commits

No commits were created in this Codex session. The repository already has a large dirty worktree, so the plan output remains staged as working-tree changes for user-controlled review and commit.

## Files Created/Modified

- `tests/test_signal_contract_inventory.py` - New local pytest guard for signal-contract drift.
- `site/architecture/correlation-contract.md` - Documents the guard and enforcement points.
- `site/architecture/service-inventory.md` - Adds the guard to operator validation surfaces.
- `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json` - Adds core reusable trace and service fields required by the guard.

## Decisions Made

- The new test reads source files and JSON descriptors directly rather than importing app modules, avoiding database, OCI SDK, and web framework startup dependencies.
- The Log Analytics field-map guard checks semantic, parser, and existing display names so reuse-first mappings can evolve without changing the test shape.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Core Log Analytics join fields absent from reuse map**

- **Found during:** Task 1 (Add source-level signal contract inventory test)
- **Issue:** `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json` did not list `Trace ID`, `Span ID`, `Service Name`, or `Service Namespace`, but the plan required the inventory test to enforce them.
- **Fix:** Added reuse-first entries for those core fields with `createIfMissing=false`.
- **Files modified:** `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json`
- **Verification:** `python3 -m pytest -q tests/test_signal_contract_inventory.py`
- **Committed in:** Not committed; working-tree change only.

**Total deviations:** 1 auto-fixed (missing critical signal-contract inventory data).
**Impact on plan:** The extra file change keeps the guard actionable and aligned with the reuse-first Log Analytics requirement.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- `python3 -m pytest -q tests/test_signal_contract_inventory.py` - passed, 7 tests.
- `python3 -m mkdocs build --strict` - passed.
- `git diff --check -- tests/test_signal_contract_inventory.py site/architecture/correlation-contract.md site/architecture/service-inventory.md deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json` - passed.
- Secret scan across touched files for OCIDs, Langfuse keys, IPs, and live domains - passed.

## Next Phase Readiness

Ready for Phase 1 Plan 02. The local guard now gives the next plans a fast check while hardening Shop and CRM request/log enrichment.

---
*Phase: 01-signal-contract-hardening*
*Completed: 2026-05-14*
