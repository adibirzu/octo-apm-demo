---
phase: 07-oke-autoscaling-and-stress-demo
plan: 10
subsystem: docs
tags: [docs, workshop, runbook, mkdocs, surface-test]

requires:
  - phase: 07-oke-autoscaling-and-stress-demo
    provides: "All prior 9 plans — HPA (01), CA + adapter (02), stress-runner (03), admin-host helper (04), stress API (05), admin template (06), APM saved queries (07), Monitoring alarms (08), LA saved searches + dashboard (09)"
  - phase: 04-deployment-parity-and-release-gates
    provides: "DEPLOY-03 VM/OKE round-robin contract — drives the D-09 LB header pin"
  - phase: 06-documentation-and-architecture-closure
    provides: "DOC-03 mkdocs --strict gate carried forward through Phase 7"

provides:
  - "site/workshop/lab-11-oke-autoscaling.md — full Phase 7 walking tour (271 lines)"
  - "site/operations/stress-demo-lb-routing.md — D-09 LB header-routing operator runbook (173 lines)"
  - "mkdocs.yml nav entries for Lab 11 + LB routing runbook"
  - "tests/test_unified_deploy_surface.py — stress-runner manifest + CA script presence checks"
  - "12 new tests in tests/test_stress_demo_surface.py covering lab/runbook/mkdocs/unified-surface"

affects: [workshop-attendee-experience, mkdocs-published-site, operator-runbook-library, phase-7-narrative-closure]

tech-stack:
  added: []
  patterns:
    - "Workshop-lab structural template carried over from Lab 09 (objective → time-budget → prerequisites → 7 steps → external drilldowns → verify → troubleshoot → read-more)"
    - "Operator-runbook pattern carried over from site/operations/chaos.md (audit + rollback sections)"
    - "Unified-deploy-surface presence checks mirror test_unified_deploy_wrapper_exists shape — ROOT + read_text + assert exists + executable"

key-files:
  created:
    - site/workshop/lab-11-oke-autoscaling.md
    - site/operations/stress-demo-lb-routing.md
    - .planning/phases/07-oke-autoscaling-and-stress-demo/deferred-items.md
  modified:
    - mkdocs.yml
    - tests/test_stress_demo_surface.py
    - tests/test_unified_deploy_surface.py

key-decisions:
  - "Lab 11 is the last lab — no 'Next →' pointer at the bottom; it closes the workshop arc (D-22)"
  - "Operator-gated prerequisites are flagged in a single table at the top of Lab 11 (live-run vs read-only walkthrough disambiguation)"
  - "LB routing rule expression uses case-insensitive header match `(i 'X-Octo-Stress-Target') eq (i 'oke')` — OCI LB grammar"
  - "Two .planning/* cross-links in the runbook were dropped to satisfy mkdocs --strict (planning docs are not published); prose references the contracts by name instead"
  - "Pre-existing failures in test_unified_deploy_surface.py (README.md content drift) logged to deferred-items.md — out of plan 07-10 scope"

patterns-established:
  - "Pattern: workshop-lab cross-link block at bottom = back-arrow to previous + (optional) next-arrow. Last lab in the arc omits the next-arrow."
  - "Pattern: external-drilldown link blocks (D-20) live in their own H2 section after the steps and before Verify, each with a one-line 'use when…' description."
  - "Pattern: operator-runbook live-mutation steps default to --dry-run with explicit operator-confirm gate before drop-the-flag apply."

requirements-completed: [SCALE-01, SCALE-02, SCALE-03, SCALE-04]

duration: ~14min
completed: 2026-05-18
---

# Phase 7 Plan 10: Workshop Lab 11 + LB Routing Runbook + Surface Test Closure Summary

**The Phase 7 narrative closes: Lab 11 walks the full elasticity demo end-to-end with cross-channel `run_id` pivots; the LB header-routing operator runbook documents the D-09 stress-pin rule; mkdocs builds strict-green; the unified-deploy-surface test now catches stress-runner + Cluster Autoscaler drift.**

## Performance

- **Duration:** ~14 min
- **Tasks completed:** 3/3
- **Files created:** 3 (Lab 11, LB runbook, deferred-items.md)
- **Files modified:** 3 (mkdocs.yml, test_stress_demo_surface.py, test_unified_deploy_surface.py)
- **Test surface delta:** +12 plan 07-10 tests + 2 unified-deploy-surface tests; all 103 stress-demo + 12 plan-07-10 tests green
- **Doc surface delta:** +444 lines of operator/workshop docs; mkdocs strict-green

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `e010a2e` | test | RED assertions for Lab 11 + LB runbook + unified surface coverage |
| `c650c67` | feat | GREEN — Workshop Lab 11 + LB header-routing runbook |
| `611b6c2` | feat | Wire mkdocs nav + extend unified deploy surface test |

## What Shipped

### Workshop Lab 11 (`site/workshop/lab-11-oke-autoscaling.md`, 271 lines)

A 15-minute walking tour of the entire Phase 7 demo:

1. **Verify baseline** — 2 shop pods, 2 nodes; `kubectl` + OCI Console
2. **Trigger Medium preset** — 50 RPS / 3 min `checkout_journey` from
   `/admin/stress-test`; capture `run_id`
3. **Watch HPA add pods** — `kubectl -w` + APM `octo-oke-pod-count`;
   shop scales 2 → ~6 within 60s; HPA ceiling 10 leaves Heavy-preset
   headroom
4. **Watch Cluster Autoscaler add a node** + CPU-saturation alarm
   fires (expected — alarm-path validation per D-18)
5. **Drill into APM** — 4 saved queries (pod count, latency
   percentiles, trace-to-new-pods, error/saturation), all scoped by
   `run_id`
6. **Drill into Log Analytics** — "OKE Autoscaling Timeline"
   dashboard, 4 saved searches, all aligned on `run_id`
7. **Cool-down** — 5-min `stabilizationWindowSeconds`; back to
   baseline; alarm clears

Cross-links: Labs 01 (first trace), 05 (metric+alarm), 09 (run_id
pivot pattern). External drilldowns: `lm`, `phoenix`, `openlit`,
`grafana` `.octodemo.cloud` — each with a "use when…" description
(D-20). Operator-gated prerequisites table makes live vs read-only
walkthrough explicit. Troubleshooting table covers 7 failure modes.

### LB Header-Routing Runbook (`site/operations/stress-demo-lb-routing.md`, 173 lines)

Operator runbook for the OCI Flexible LB routing-policy rule that
pins `X-Octo-Stress-Target: oke` requests to the OKE backend set
while leaving the VM round-robin path untouched (D-09 / DEPLOY-03).

- Prerequisites table — `OCTO_LB_OCID` env, OCI CLI profile, operator
  approval, backend-set name lookup
- 4 steps — inspect existing policy → compose rule JSON (case-
  insensitive header match) → dry-run apply → curl-verify
- 2 rollback options — drop rule from policy, or detach policy from
  listener (incident response)
- Audit + recording section — record workshop `run_id` in PR
  comment; OCI Audit log carries the LB mutation automatically
  (T-07-46 mitigation)
- Cross-links to Lab 11 + `configure-cluster-autoscaler.sh` (same
  operator window)

All `${OCTO_LB_OCID}` / `${DNS_DOMAIN}` / `${OCI_CLI_PROFILE}`
placeholders — no live OCIDs / IPs / tenancy labels (SEC-04,
T-07-44 mitigation).

### MkDocs Nav Wiring (`mkdocs.yml`)

- Workshop nav: added `Lab 11 — OKE Autoscaling` after Lab 10
- Operations nav: added `Stress demo LB routing` after `Alarms & Health`
- Indentation matches existing style; `mkdocs build --strict` green

### Unified Deploy Surface Test Extension (`tests/test_unified_deploy_surface.py`)

Two new functions mirroring `test_unified_deploy_wrapper_exists` shape:

- `test_stress_runner_manifest_in_unified_surface` — asserts
  `deploy/k8s/oke/stress-runner/deployment.yaml` exists and declares
  `octo-stress-runner`
- `test_configure_cluster_autoscaler_in_unified_surface` — asserts
  `deploy/oke/configure-cluster-autoscaler.sh` exists, is
  executable, and calls `oci ce cluster install-addon`

Added `os` import. Appended at end of file — no refactor of
existing tests.

### Stress Demo Surface Tests (`tests/test_stress_demo_surface.py`)

12 new test functions covering the 4 must-have artifacts:

- 6 Lab 11 assertions — file exists, cross-links Labs 01/05/09,
  4 drilldown hosts, 7-step arc, admin path reference, run_id pivot
- 2 LB-routing assertions — file exists with header + CLI command,
  no live OCIDs / IPs
- 2 mkdocs-nav assertions — Lab 11 + runbook in `mkdocs.yml`
- 2 unified-surface assertions — `tests/test_unified_deploy_surface.py`
  itself contains the stress-runner + CA script presence checks

## Verification

```bash
# Plan 07-10 tests (12 new + 2 unified)
$ pytest tests/test_stress_demo_surface.py tests/test_unified_deploy_surface.py \
    -k "lab11 or lb_routing or mkdocs or stress_runner_manifest_in_unified_surface or configure_cluster_autoscaler_in_unified_surface"
12 passed in 0.14s

# Full stress demo surface (103 tests — all Phase 7 surface)
$ pytest tests/test_stress_demo_surface.py -q
103 passed in 0.51s

# mkdocs strict-green
$ mkdocs build --strict
Documentation built in 1.92 seconds
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Dropped two `.planning/*` cross-links from LB
runbook to satisfy mkdocs --strict**

- **Found during:** Task 3 (mkdocs build --strict)
- **Issue:** Runbook referenced `../../.planning/phases/04-…/04-CONTEXT.md`
  and `…/07-CONTEXT.md` — planning docs are excluded from the
  published site, so mkdocs --strict fails with a broken-link warning
- **Fix:** Replaced both inline `[link](…)` references with prose
  ("Phase 4 deployment-parity contract", "Phase 7 deferred operator-
  window items"). The semantic cross-reference is preserved; the
  broken hyperlink is removed
- **Files modified:** `site/operations/stress-demo-lb-routing.md`
- **Commit:** `611b6c2`

### Deferred Issues

**Pre-existing failures in `tests/test_unified_deploy_surface.py`**
unrelated to plan 07-10 — logged to
`.planning/phases/07-oke-autoscaling-and-stress-demo/deferred-items.md`:

- `test_default_profile_docs_and_examples_target_cyber_sec_ro`
- `test_resource_manager_deploy_button_and_docs_publish_zip_url`
- `test_two_instance_compute_surface_is_offline_validated_and_observable`

All three assert README.md content (`shop.example.test`,
`COMPUTE_RESOURCE_MANAGER_BUTTON_URL`, etc.) that has since been
restructured. Verified pre-existing via `git stash` — failures
persist with all plan 07-10 edits stashed. Out of plan scope;
defer to a dedicated docs-drift fix.

## Threat Model Disposition

| Threat ID | Disposition | Evidence |
|---|---|---|
| T-07-44 (info disclosure: live OCIDs/IPs in docs) | mitigated | `test_lb_routing_runbook_no_live_ocids` enforces; grep verified clean |
| T-07-45 (runbook misleads operator into too-broad apply) | accepted | Runbook explicitly scopes to `${OCTO_LB_OCID}`; dry-run-default; rollback documented |
| T-07-46 (LB rule applied without record) | mitigated | OCI Audit log auto-captures; runbook documents querying the audit log |

No new threat surface introduced by Lab 11 (it documents existing
APIs only). No new endpoints, no schema changes.

## TDD Gate Compliance

The plan was executed as TDD per the task spec:

1. **RED** — `e010a2e` — 12 assertions defined, all fail
2. **GREEN** — `c650c67`, `611b6c2` — content + nav + test extension
   land; assertions pass

Plan-level type is `execute` (not `tdd`), but Task 1 was explicitly
TDD-tagged in the plan; gate sequence honored.

## Self-Check: PASSED

- `site/workshop/lab-11-oke-autoscaling.md` — FOUND (271 lines, ≥120)
- `site/operations/stress-demo-lb-routing.md` — FOUND (173 lines, ≥60)
- `mkdocs.yml` contains `lab-11-oke-autoscaling.md` — FOUND
- `mkdocs.yml` contains `stress-demo-lb-routing.md` — FOUND
- `tests/test_unified_deploy_surface.py` contains `stress-runner` + `octo-stress-runner` + `configure-cluster-autoscaler.sh` + `install-addon` + `os.access` — FOUND
- Commit `e010a2e` (RED) — FOUND in `git log`
- Commit `c650c67` (GREEN content) — FOUND in `git log`
- Commit `611b6c2` (nav + surface test) — FOUND in `git log`
- `mkdocs build --strict` exit 0 — VERIFIED
- All 103 stress demo surface tests pass — VERIFIED
- All 12 plan 07-10 tests pass — VERIFIED
- Pre-existing test failures verified out-of-scope (logged to deferred-items.md) — VERIFIED
