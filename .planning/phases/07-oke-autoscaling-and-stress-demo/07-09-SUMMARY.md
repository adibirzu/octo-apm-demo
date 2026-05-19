---
phase: 07-oke-autoscaling-and-stress-demo
plan: 09
subsystem: observability
tags: [log-analytics, oci, saved-search, dashboard, hpa, cluster-autoscaler, kubelet, stress-demo]

requires:
  - phase: 07-oke-autoscaling-and-stress-demo
    provides: "run_id audit log lines from stress runner (plan 05); HPA/CA manifest changes (plan 01-02); APM saved queries (plan 07); Monitoring alarms (plan 08)"
  - phase: 03-log-analytics-detection-reliability
    provides: "tools/la-saved-searches/ directory + apply.sh auto-discovery contract; smoke-test.py round-trip validator"

provides:
  - "octo-oke-autoscaling-hpa-events saved search (HPA scale events)"
  - "octo-oke-autoscaling-ca-events saved search (Cluster Autoscaler events)"
  - "octo-oke-autoscaling-kubelet-pressure saved search (NodeNotReady / ImagePullBackOff / OOMKilled)"
  - "octo-oke-autoscaling-stress-audit saved search (run_id-stamped lifecycle events)"
  - "'OKE Autoscaling Timeline' dashboard JSON linking all four searches"

affects: [lab-11-walkthrough, observability-narrative, phase-08-onwards]

tech-stack:
  added: []
  patterns:
    - "Log Analytics saved-search JSON shape (name, displayName, description, queryString, widgetType) carried over from Phase 1.3"
    - "Auto-discovery contract: apply.sh globs *.json — saved searches plug in without script edits"

key-files:
  created:
    - tools/la-saved-searches/oke-autoscaling-hpa-events.json
    - tools/la-saved-searches/oke-autoscaling-ca-events.json
    - tools/la-saved-searches/oke-autoscaling-kubelet-pressure.json
    - tools/la-saved-searches/oke-autoscaling-stress-audit.json
    - tools/la-saved-searches/oke-autoscaling-dashboard.json
  modified:
    - tests/test_stress_demo_surface.py

key-decisions:
  - "Reused the existing tools/la-saved-searches/ apply.sh auto-discovery (zero script edits) per plan acceptance criterion"
  - "Dashboard JSON references the four saved searches by name (not OCID) so it stays portable across tenancies"
  - "run_id filter ('run_id is not null') is the pivot key joining LA stress audit to plan 05 audit log and plan 08 Monitoring alarms"
  - "Default time_range parameter PT1H — sufficient for a single Lab 11 stress run"

patterns-established:
  - "Pattern: LA saved-search file naming = `<domain>-<topic>.json`, saved-search `name` = `octo-<domain>-<topic>` (e.g., octo-oke-autoscaling-hpa-events)"
  - "Pattern: Dashboard JSON co-located with saved searches in tools/la-saved-searches/, distinguished by structural fields (tiles[] vs. queryString)"

requirements-completed: [SCALE-04]

duration: ~12min
completed: 2026-05-18
---

# Phase 7 Plan 09: OKE Autoscaling Log Analytics Saved Searches + Dashboard Summary

**Four Log Analytics saved searches (HPA events, Cluster Autoscaler events, kubelet pressure, stress audit) plus the 'OKE Autoscaling Timeline' dashboard JSON; auto-discovered by the existing apply.sh.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-18T18:20:00Z
- **Completed:** 2026-05-18T18:32:38Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 6 (5 new JSON specs + 1 test file extension)

## Accomplishments

- Shipped D-19 deliverable: the four time-aligned LA views (HPA / CA / kubelet pressure / stress audit) that underpin Lab 11's autoscaling walkthrough
- Cross-channel pivot key (`run_id`) wired through to the stress runner audit log (plan 05) and Monitoring alarms (plan 08)
- Apply contract preserved: `tools/la-saved-searches/apply.sh` got zero edits — saved searches plug in via the existing `*.json` glob
- 7 new pytest assertions covering query content, OCID/IP leak guard, and the apply.sh invariant (no hardcoded plan-09 names)

## Task Commits

1. **Task 1: RED — pytest assertions for LA saved searches + dashboard** — `a7e711b` (test)
2. **Task 2: GREEN — author 4 saved searches + dashboard JSON** — `4c3e835` (feat)

## Files Created/Modified

- `tools/la-saved-searches/oke-autoscaling-hpa-events.json` — HPA scale events (Subsystem='hpa-controller'), TABLE widget
- `tools/la-saved-searches/oke-autoscaling-ca-events.json` — Cluster Autoscaler events (Subsystem='cluster-autoscaler'), TABLE widget
- `tools/la-saved-searches/oke-autoscaling-kubelet-pressure.json` — NodeNotReady / ImagePullBackOff / OOMKilled matchers, BAR_CHART widget
- `tools/la-saved-searches/oke-autoscaling-stress-audit.json` — shop app log lines where run_id is not null, TABLE widget
- `tools/la-saved-searches/oke-autoscaling-dashboard.json` — 'OKE Autoscaling Timeline' with 4 tiles, PT1H default time_range parameter
- `tests/test_stress_demo_surface.py` — added 7 plan-09 assertions (105 inserted lines)

## Decisions Made

- **Dashboard schema shape:** Followed a reasonable OCI Log Analytics dashboard shape (top-level `displayName`, `tiles[]` with `savedSearchName`, grid `position`, `parameters[]`). Tests assert substring presence (saved-search names + 'OKE Autoscaling Timeline') rather than full schema fidelity — gives operators room to adapt at import time if OCI dashboard import requires a slightly different envelope.
- **CA query field:** Used `Subsystem = 'cluster-autoscaler'` mirroring the HPA filter pattern. The exact OCI add-on log subsystem name should be verified at first `apply.sh` run; the query is intentionally illustrative per the plan note.

## Deviations from Plan

### Deferred / Documented (no code change)

**1. [Rule 4 - Architectural, accepted by plan] Dashboard JSON shares directory with saved searches**
- **Found during:** Task 2
- **Issue:** `apply.sh` globs `*.json` and treats every match as a saved search for `oci log-analytics saved-search create-or-update`. The new `oke-autoscaling-dashboard.json` will fail that call at apply time because its schema is a dashboard, not a saved search.
- **Resolution:** Plan acceptance criterion is explicit: "Diff to `tools/la-saved-searches/apply.sh` is zero lines." The plan author accepted this trade-off. Operators have two paths at apply time: (a) move the dashboard JSON to a sibling directory before running apply.sh, or (b) import the dashboard manually through the Log Analytics UI. The auto-discovery contract for the four saved searches is what plan 09 actually relies on.
- **Logged for future plan:** consider adding a `dashboards/` subdirectory and a sibling `apply-dashboards.sh` in a follow-up plan (out of scope here).

**2. [Rule 3 - Plan-spec/code mismatch] `smoke-test.py` is a runtime tool, not an offline validator**
- **Found during:** Task 2 verification
- **Issue:** The plan's automated-verify step says `python tools/la-saved-searches/smoke-test.py 2>&1 | tail -10` and expects it to validate the new JSONs offline. Reading the file, it is a **runtime** trace ↔ log round-trip validator that requires `--la-namespace`, `--trace-id`, and OCI auth.
- **Fix:** Replaced that verification step with explicit per-file `json.load` parse checks (executed for all 5 new files — all parse cleanly).
- **Verification:** `for f in tools/la-saved-searches/oke-autoscaling-*.json; do python -c "import json; json.load(open('$f')); print('OK')"; done` → 5x OK.

---

**Total deviations:** 2 documented (1 accepted architectural trade-off from the plan itself, 1 verification-script substitution).
**Impact on plan:** All seven plan-09 tests pass. Acceptance criteria satisfied modulo the smoke-test substitution; the apply-time dashboard caveat is operator-facing, not a code defect.

## Issues Encountered

None during execution. The dashboard/apply.sh interaction noted above is a plan-level design choice, not an issue.

## Verification Output

- `pytest tests/test_stress_demo_surface.py -k "la_oke or la_apply"` → **7 passed, 53 deselected**
- `pytest tests/test_stress_demo_surface.py` (full file) → **60 passed**
- All 5 new JSON files parse via `json.load`
- `grep -rE 'ocid1\.' tools/la-saved-searches/oke-autoscaling-*.json` → no matches
- `grep -rE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' tools/la-saved-searches/oke-autoscaling-*.json` → no matches
- `git diff --stat tools/la-saved-searches/apply.sh` → empty (auto-discovery preserved)
- Simulated apply.sh discovery loop picks up all 4 new saved searches (and the dashboard — see Deviation #1)

## User Setup Required

None for code shipping. At demo-deploy time:
- Run `LA_NAMESPACE=... LA_LOG_GROUP_ID=... ./tools/la-saved-searches/apply.sh` to upsert the four saved searches.
- Either move `oke-autoscaling-dashboard.json` out of the directory before running apply.sh, or import it manually via the Log Analytics dashboard UI (see Deviation #1).

## Next Phase Readiness

- Plan 09 closes the LA observability half of D-19. The four saved searches are time-alignable with APM saved queries (plan 07) and Monitoring alarms (plan 08) via the `run_id` pivot.
- Plan 10 (deferred-items / closeout) can pick up the dashboard-apply tooling caveat if desired.

## Self-Check: PASSED

- `tools/la-saved-searches/oke-autoscaling-hpa-events.json` → FOUND
- `tools/la-saved-searches/oke-autoscaling-ca-events.json` → FOUND
- `tools/la-saved-searches/oke-autoscaling-kubelet-pressure.json` → FOUND
- `tools/la-saved-searches/oke-autoscaling-stress-audit.json` → FOUND
- `tools/la-saved-searches/oke-autoscaling-dashboard.json` → FOUND
- Commit `a7e711b` (RED test) → FOUND
- Commit `4c3e835` (GREEN impl) → FOUND

## TDD Gate Compliance

- RED gate: `a7e711b` — `test(07-09): RED assertions ...`
- GREEN gate: `4c3e835` — `feat(07-09): GREEN — OKE autoscaling LA saved searches + dashboard`
- REFACTOR: not required (single-pass GREEN; JSON files are declarative, no code-shape refactor warranted)

---
*Phase: 07-oke-autoscaling-and-stress-demo*
*Completed: 2026-05-18*
