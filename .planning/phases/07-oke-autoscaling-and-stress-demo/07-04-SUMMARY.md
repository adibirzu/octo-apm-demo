---
phase: 07-oke-autoscaling-and-stress-demo
plan: 04
subsystem: admin
tags: [admin, host-binding, refactor, fastapi, phase5-extension, single-source-of-truth]

requires:
  - phase: 05-admin-ai-and-secure-operations
    provides: "Host-bound admin enforcement primitives (_require_admin_host, _request_host, _configured_admin_hosts) and the Phase 5 admin-host contract that /api/admin/coordinator/* enforces"
provides:
  - "Shared helper module crm/server/modules/_admin_host.py — single source of truth for host-bound admin enforcement"
  - "coordinator.py now imports the helpers (no re-implementation) — drift-resistant by construction"
  - "10 helper-contract tests in tests/test_admin_host_helper.py that pin parsing (port stripping, X-Forwarded-Host precedence, IPv6 bracket handling) and policy (local-host allow-list, admin surface, DNS-domain-derived allow-list extension)"
  - "Structural anti-drift guard: a test asserts coordinator.py contains the import line, so future copy-paste regressions fail loudly"
affects: [07-05-stress-test-admin-api, 07-06-stress-test-admin-ui, future-admin-surfaces]

tech-stack:
  added: []
  patterns:
    - "Internal-only shared helper module pattern (`_admin_host.py` with leading underscore signaling internal-to-crm consumption)"
    - "Structural anti-drift test (source-grep assertion that coordinator imports rather than re-implements)"

key-files:
  created:
    - crm/server/modules/_admin_host.py
    - tests/test_admin_host_helper.py
    - .planning/phases/07-oke-autoscaling-and-stress-demo/07-04-SUMMARY.md
  modified:
    - crm/server/modules/coordinator.py
    - crm/tests/test_admin_coordinator.py

key-decisions:
  - "Extract three helpers + two constants verbatim (no behavioral change) — refactor-scope plan"
  - "Place helper at `crm/server/modules/_admin_host.py` with leading underscore to signal internal-to-crm usage (mirrors `_authz.py` sibling)"
  - "Existing test_query_allows_configured_admin_host needs to monkeypatch both `coordinator.cfg` AND `_admin_host.cfg` — both modules bind `cfg` at import time; production behavior unchanged (same singleton)"

patterns-established:
  - "Shared admin-host module — single import path `from server.modules._admin_host import _require_admin_host` for any new admin-only surface (consumed by Plan 07-05 stress-test module)"
  - "Anti-drift structural test — assert source contains the canonical import line so a future copy-paste regression fails CI"

requirements-completed: [SCALE-03]

duration: 8min
completed: 2026-05-18
---

# Phase 7 Plan 04: Single-source `_admin_host` helper extraction Summary

**Extracted `_require_admin_host`, `_request_host`, and `_configured_admin_hosts` from `coordinator.py` into shared `crm/server/modules/_admin_host.py` so Plan 07-05's stress-test surface imports the same host-gate that Phase 5 hardened — drift impossible by construction.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-18T17:40:00Z
- **Completed:** 2026-05-18T17:48:00Z
- **Tasks:** 2 of 2 complete
- **Files modified:** 5 (2 created, 2 modified, 1 SUMMARY)

## Accomplishments

- New shared helper module `crm/server/modules/_admin_host.py` (57 lines) owns the host-bound admin boundary
- `coordinator.py` lost ~22 lines of inline duplication and gained a single import line — same call sites, same behavior
- 10/10 helper-contract tests pass, pinning parsing edge cases (X-Forwarded-Host precedence, port stripping, IPv6 bracket handling) and policy gates (local hosts, admin surface, DNS-domain-derived allow-list)
- 7/7 Phase 5 coordinator regression tests pass — `/api/admin/coordinator/*` still 403s non-admin hosts bit-identically
- 97/97 full crm test suite passes; 38/38 Phase 7 stress demo surface tests pass; no telemetry/observability regression

## Task Commits

Each task was committed atomically:

1. **Task 1: RED tests for shared _admin_host helper extraction** — `d4f5295` (test)
2. **Task 2: Extract helpers into _admin_host.py and update coordinator.py to import** — `e42ff1f` (refactor)

## Files Created/Modified

- `crm/server/modules/_admin_host.py` — **created**. Houses `_ADMIN_SURFACE`, `_LOCAL_HOSTS`, `_request_host`, `_configured_admin_hosts`, `_require_admin_host`. Module docstring states "Do not duplicate this logic — import from here."
- `crm/server/modules/coordinator.py` — **modified**. Deleted inline definitions of those five names; added single `from server.modules._admin_host import (...)` line. All call sites unchanged.
- `crm/tests/test_admin_coordinator.py` — **modified**. `test_query_allows_configured_admin_host` now patches `_admin_host.cfg` alongside `coordinator.cfg` so the monkeypatch reaches both module-level bindings of the same singleton (see Deviations).
- `tests/test_admin_host_helper.py` — **created**. 10 tests: module shape (1), `_request_host` parsing (3), `_require_admin_host` policy (4), structural anti-drift guard (1), Phase 5 endpoint regression guard (1).

## Decisions Made

- **Verbatim copy, no behavior change.** This is refactor-scope: the helpers are moved exactly as written. Any behavioral tweak would belong in a separate plan with its own threat-model row.
- **Module naming `_admin_host.py` (leading underscore).** Mirrors the sibling `_authz.py` convention signaling "internal to the crm package; not a public router or API surface."
- **Tests live at the repo-root `tests/` directory.** The plan specified `tests/test_admin_host_helper.py`; this matches the Phase 7 surface tests pattern (`tests/test_stress_demo_surface.py`). The test file adds `crm/` to `sys.path` at import time to make `server.*` importable (same trick `crm/tests/conftest.py` uses for its own scope).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing `test_query_allows_configured_admin_host` to monkeypatch both `coordinator.cfg` and `_admin_host.cfg`**
- **Found during:** Task 2 verification (running `pytest crm/tests/test_admin_coordinator.py`)
- **Issue:** After moving `_configured_admin_hosts` out of `coordinator.py` and into `_admin_host.py`, the helper module captures its own `cfg` reference at import time (`from server.config import cfg`). The existing Phase 5 test uses `monkeypatch.setattr(coordinator, "cfg", fake_cfg)` which only patches the `coordinator` module's binding — not the `_admin_host` module's binding. The call chain `coordinator._configured_admin_hosts -> _admin_host._configured_admin_hosts -> _admin_host.cfg.dns_domain` therefore reads the real `cfg`, so `admin.example.test` is not in the allow-list and the request 403s instead of 200s.
- **Fix:** Added `monkeypatch.setattr(_admin_host, "cfg", fake_cfg)` alongside the existing `coordinator` patch. Imported `_admin_host` at the top of the test file. Production runtime behavior unchanged because both modules import the same `cfg` singleton — the dual patch is only needed because `monkeypatch` operates on module attribute bindings, not on the underlying object.
- **Files modified:** `crm/tests/test_admin_coordinator.py`
- **Verification:** Full `crm/tests/test_admin_coordinator.py` suite now passes (7/7). Full `crm/tests/` suite still passes (97/97). The fix is local to the test; the production cfg-binding semantics are unchanged.
- **Committed in:** `e42ff1f` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — test isolation pattern needed update for new module structure)
**Impact on plan:** The fix is necessary for the regression guard to keep passing. No scope creep — it's a one-line test setup adjustment that follows directly from the refactor. The plan's must-have ("Phase 5 admin-host contract continues to work bit-identically") is preserved because production behavior is unchanged; only the test's monkeypatch surface area moved.

## Issues Encountered

None beyond the test-monkeypatch adjustment documented under Deviations.

## User Setup Required

None — refactor-only change; no new env vars, dashboards, or operator steps.

## Threat Surface Review

No new threat surface introduced. T-07-17 (XFH spoofing) and T-07-18 (drift between coordinator and future stress_test enforcement) are unchanged or improved:

- **T-07-17:** Helper logic identical to pre-refactor; ingress XFH stripping contract unchanged.
- **T-07-18:** *Materially mitigated by this plan.* Drift is now structurally impossible — the structural anti-drift test (`test_coordinator_still_imports_admin_host_helpers`) will fail loudly if any future change copy-pastes the helpers back inline. Plan 07-05's stress-test module will import from the same source.
- **T-07-19:** `_LOCAL_HOSTS` set unchanged (`localhost`, `127.0.0.1`, `::1`, `testserver`).

## Next Phase Readiness

- Plan 07-05 (`stress_test.py`) can now `from server.modules._admin_host import _require_admin_host` and inherit the Phase 5 host gate identically — the must-have "import, not re-implement" rule is mechanically enforceable.
- No blockers, no concerns.

## Self-Check: PASSED

- File exists: `crm/server/modules/_admin_host.py` — FOUND
- File exists: `tests/test_admin_host_helper.py` — FOUND
- Modified: `crm/server/modules/coordinator.py` — FOUND
- Modified: `crm/tests/test_admin_coordinator.py` — FOUND
- Commit `d4f5295` (RED) — FOUND
- Commit `e42ff1f` (GREEN refactor) — FOUND
- Acceptance: `grep -c 'def _require_admin_host' coordinator.py` = 0 — PASSED
- Acceptance: `grep -c 'def _require_admin_host' _admin_host.py` = 1 — PASSED
- Acceptance: `grep -c 'from server.modules._admin_host import' coordinator.py` = 1 — PASSED
- All 10 helper tests pass — PASSED
- All 7 coordinator regression tests pass — PASSED
- Full crm suite 97/97 pass — PASSED
- Phase 7 stress demo surface 38/38 pass — PASSED

---
*Phase: 07-oke-autoscaling-and-stress-demo*
*Completed: 2026-05-18*
