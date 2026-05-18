---
phase: 01-signal-contract-hardening
plan: "04"
subsystem: observability
tags: [apm, log-analytics, monitoring, dashboards, documentation]

requires:
  - phase: 01-signal-contract-hardening
    provides: Plans 01-03 signal-contract source hardening
provides:
  - APM, Log Analytics, dashboard, and Monitoring asset contract test
  - Local validation runbooks for APM and Log Analytics assets
  - Phase 1 combined validation evidence
affects: [apm, log-analytics, monitoring, docs, phase-1]

tech-stack:
  added: []
  patterns:
    - Observability assets are validated locally before live OCI import
    - Dashboard widget searches must reference versioned SQL files

key-files:
  created:
    - tests/test_observability_asset_contract.py
  modified:
    - deploy/oci/apm/saved-queries/README.md
    - deploy/oci/log_analytics/README.md
    - deploy/oci/log_analytics/searches/db-slowness-hotspots.sql
    - deploy/oci/log_analytics/searches/oke-onm-ingestion-health.sql
    - site/observability-v2/apm-drilldown.md
    - site/observability-v2/log-analytics-dashboards.md

key-decisions:
  - "Keep live OCI import/deployment separate from the local source validation gate."
  - "Guard Monitoring namespace and ingestion endpoint assumptions from source without requiring OCI credentials."

patterns-established:
  - "Required APM saved queries and Log Analytics searches are declared in one root pytest contract."
  - "Docs must name the same local validation command used by the phase gate."

requirements-completed: [OBS-02, OBS-03, OBS-05]

duration: 4 min
completed: 2026-05-14
---

# Phase 1 Plan 04: Observability Asset Contract Summary

**APM saved queries, Log Analytics searches/dashboards, field reuse, and Monitoring assumptions now have a local source gate and documented operator validation path.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-14T10:16:57Z
- **Completed:** 2026-05-14T10:21:03Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added `tests/test_observability_asset_contract.py` for APM saved-query descriptors, Log Analytics saved searches, field reuse, dashboard widget references, and Monitoring namespace/endpoint assumptions.
- Updated APM and Log Analytics runbooks with the local validation command and required asset filenames.
- Updated observability docs to state that live OCI import/deployment is a separate operator action and this phase does not run Terraform apply or create OCI resources.
- Ran the Phase 1 combined validation gate successfully.

## Task Commits

No commits were created in this Codex session. The changes remain in the working tree for user-controlled review and commit.

## Files Created/Modified

- `tests/test_observability_asset_contract.py` - New root contract test for observability source assets.
- `deploy/oci/apm/saved-queries/README.md` - Adds local saved-query validation.
- `deploy/oci/log_analytics/README.md` - Adds field-map and saved-search validation guidance.
- `deploy/oci/log_analytics/searches/db-slowness-hotspots.sql` - Adds trace count to preserve trace-pivot coverage.
- `deploy/oci/log_analytics/searches/oke-onm-ingestion-health.sql` - Adds trace count to preserve trace-pivot coverage.
- `site/observability-v2/apm-drilldown.md` - Adds APM descriptor validation gate.
- `site/observability-v2/log-analytics-dashboards.md` - Adds dashboard/search validation gate.

## Decisions Made

- The asset contract checks source descriptors and docs only; it intentionally does not call OCI APIs.
- Dashboards are validated by resolving every widget `search` to a versioned SQL file in `deploy/oci/log_analytics/searches/`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Two required searches lacked explicit trace-field tokens**

- **Found during:** Task 1 (Add observability asset contract test)
- **Issue:** `db-slowness-hotspots.sql` and `oke-onm-ingestion-health.sql` did not include `Trace ID` or `oracleApmTraceId`, but the asset contract requires required searches to expose a trace pivot token.
- **Fix:** Added `distinctcount('Trace ID') as Traces` to both searches without changing their grouping dimensions.
- **Files modified:** `deploy/oci/log_analytics/searches/db-slowness-hotspots.sql`, `deploy/oci/log_analytics/searches/oke-onm-ingestion-health.sql`
- **Verification:** `python3 -m pytest -q tests/test_observability_asset_contract.py tests/test_log_analytics_attack_assets.py`
- **Committed in:** Not committed; working-tree change only.

**Total deviations:** 1 auto-fixed (missing critical asset contract token).
**Impact on plan:** The fix aligns required searches with the APM-to-Log Analytics trace-pivot contract.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- `python3 -m pytest -q tests/test_observability_asset_contract.py tests/test_log_analytics_attack_assets.py` - passed, 22 tests.
- `python3 -m pytest -q tests/test_signal_contract_inventory.py tests/test_observability_asset_contract.py tests/test_log_analytics_attack_assets.py` - passed, 29 tests.
- `python3 -m mkdocs build --strict` - passed.
- `git diff --check` - passed.

## Next Phase Readiness

Phase 1 local source gates are complete. The next GSD step should be Phase 1 verification or Phase 2 planning for payment and user journey insight.

---
*Phase: 01-signal-contract-hardening*
*Completed: 2026-05-14*
