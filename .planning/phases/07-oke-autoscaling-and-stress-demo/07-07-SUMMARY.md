---
phase: 07-oke-autoscaling-and-stress-demo
plan: 07
subsystem: observability
tags: [apm, saved-queries, oci-apm, drilldowns, operator-tooling]

requires:
  - phase: 01-foundation
    provides: OBS-05 service.namespace=octo_apm_demo contract
provides:
  - Four committed APM saved-query JSON specs (D-16) scoped to octo_apm_demo
  - Operator-gated apply.sh (APPLY=false default, confirm-prompt, --help)
  - D-20 external drilldown link metadata embedded per query (lm/phoenix/openlit/grafana .octodemo.cloud)
affects: [phase-08-verification, operator-runbook, dashboards]

tech-stack:
  added: []
  patterns:
    - "JSON-spec saved query files mirror tools/la-saved-searches/ shape"
    - "apply.sh dry-run-default + confirm-on-APPLY pattern (LA analog)"
    - "external_drilldowns array carries D-20 outbound URLs as operator-readable metadata"

key-files:
  created:
    - tools/apm-saved-queries/README.md
    - tools/apm-saved-queries/apply.sh
    - tools/apm-saved-queries/oke-pod-count-over-time.json
    - tools/apm-saved-queries/oke-latency-percentiles-during-scale.json
    - tools/apm-saved-queries/oke-trace-propagation-new-pods.json
    - tools/apm-saved-queries/oke-error-saturation-slow-spans.json
  modified:
    - tests/test_stress_demo_surface.py

key-decisions:
  - "Mirrored tools/la-saved-searches/ structure verbatim (apply.sh shape, README convention) so operators have one mental model across LA + APM saved artifacts"
  - "Embedded D-20 drilldown URLs as an external_drilldowns metadata array inside each JSON — APM UI may ignore the field, but the JSON is the operator-readable source of truth for 'click here for Langfuse/Phoenix/OpenLIT/Grafana'"
  - "Used 'baseline_pod_set' as a parameter the operator fills at apply time in trace-propagation query (documented in README) rather than hardcoding pod names"
  - "Query strings are illustrative — README notes the operator will tune them at apply time against the live OCI APM filter syntax; tests assert structural tokens (service.namespace, k8s.pod.name, p95, span.status) not literal query equivalence"

patterns-established:
  - "Saved-query operator pattern: JSON spec + dry-run apply.sh + confirm-on-APPLY=true (consistent with la-saved-searches)"
  - "D-20 drilldown linkage: each APM query carries external_drilldowns metadata so the trace UI can point operators outbound to Langfuse/Phoenix/OpenLIT/Grafana"

requirements-completed: [SCALE-04]

duration: ~25min
completed: 2026-05-18
---

# Phase 7 Plan 07: APM Saved Queries Summary

**Four committed OCI APM saved-query JSON specs (pod count, latency percentiles, trace-to-new-pods, error/saturation) scoped to service.namespace=octo_apm_demo with D-20 drilldown link metadata and a dry-run-default operator apply.sh**

## Performance

- **Duration:** ~25 min (including stream-timeout recovery)
- **Started:** 2026-05-18T20:30:00Z (approx, RED commit timestamp)
- **Completed:** 2026-05-18T21:00:00Z (approx)
- **Tasks:** 2 (RED + GREEN)
- **Files modified:** 7 (6 new + 1 test extension)

## Accomplishments

- Four APM saved-query JSON specs landed under `tools/apm-saved-queries/` covering D-16 #1–#4 (pod count over time, p50/p95/p99 latency, trace propagation to new pods, error/saturation top-N)
- Operator apply.sh mirrors the LA pattern: APPLY=false default, COMPARTMENT_ID/APM_DOMAIN_ID required, confirm prompt before any mutation, `--help` supported
- Each JSON carries an `external_drilldowns` array with D-20 hosts (`lm.octodemo.cloud`, `phoenix.octodemo.cloud`, `openlit.octodemo.cloud`, `grafana.octodemo.cloud`)
- No live OCIDs, IPs, or tenancy labels committed (verified by test + grep)

## Task Commits

1. **Task 1: RED assertions for APM saved queries** — `7bb70b0` (test)
2. **Task 2: Four APM saved queries + operator apply.sh** — `aa7808a` (feat)

**Plan metadata:** TBD (this SUMMARY commit)

## Files Created/Modified

- `tools/apm-saved-queries/README.md` — Directory README: operator convention, baseline_pod_set parameter for trace query, dry-run default, OCI APM CLI shape
- `tools/apm-saved-queries/apply.sh` — Operator apply script (executable, bash -n clean, --help supported, APPLY=false default, confirm prompt, OCI_PROFILE=emdemo default)
- `tools/apm-saved-queries/oke-pod-count-over-time.json` — D-16 #1, LINE_CHART, `count_distinct(k8s.pod.name)` by service + 1min bucket
- `tools/apm-saved-queries/oke-latency-percentiles-during-scale.json` — D-16 #2, LINE_CHART, p50/p95/p99 on `/api/shop/checkout` and java-apm service at 30s bucket
- `tools/apm-saved-queries/oke-trace-propagation-new-pods.json` — D-16 #3, TABLE, k8s.pod.name first-appearance window (baseline_pod_set is operator-filled at apply time)
- `tools/apm-saved-queries/oke-error-saturation-slow-spans.json` — D-16 #4, BAR_CHART, span.status=ERROR or duration>1000ms, top-N by service/pod/status
- `tests/test_stress_demo_surface.py` — Extended with 8 apm_saved_* assertions (RED, then GREEN after Task 2)

## Decisions Made

- **Mirrored LA tooling structure verbatim.** apply.sh and README convention follow `tools/la-saved-searches/` so operators have one mental model across both saved-artifact surfaces. The CLI subcommand for APM (`oci apm-traces saved-search ...`) is documented as illustrative — the README notes the operator will reconcile against the live OCI CLI version during the apply window, falling back to manual import if the subcommand is unstable.
- **Drilldown links as JSON metadata.** Each saved-query JSON carries an `external_drilldowns` array (name/url/why per host). APM may not surface this natively, but the JSON is the operator-readable contract: when looking at a slow span in APM, the operator can pivot to `lm.octodemo.cloud` (Langfuse), `phoenix.octodemo.cloud` (Arize Phoenix), `openlit.octodemo.cloud` (OpenLIT), or `grafana.octodemo.cloud` (Grafana) per D-20.
- **baseline_pod_set is a parameter, not a literal.** The trace-propagation query references a `<baseline_pod_set>` placeholder that the operator fills at apply time by snapshotting the pre-scale pod set. Documented in README so the operator workflow is reproducible without hardcoding pod names that would drift.
- **Test contract is structural, not literal.** The RED tests assert that the query strings contain the right tokens (`service.namespace`, `k8s.pod.name`, `p95`, `span.status`, `octo_apm_demo`) and the JSON is well-formed — they do not pin the exact APM filter syntax, which the operator may need to tune at apply time against the live domain.

## Deviations from Plan

None — plan executed exactly as written. The previous executor agent died from a stream idle timeout after writing the artifact files but before committing them; this resume agent verified the on-disk files against the plan's must_haves, confirmed RED→GREEN test transition, and committed the staged work in a single `feat(07-07): ...` commit.

## Issues Encountered

- **Stream idle timeout during prior agent run** — The previous executor wrote all 6 artifact files and the RED test commit landed, but the agent process died before committing GREEN. Resume agent reconciled by:
  1. Listing untracked `tools/apm-saved-queries/` files (all 6 present)
  2. Running the apm_saved test suite — 8/8 PASS, confirming the on-disk artifacts already satisfy GREEN
  3. Running JSON parse, `bash -n`, OCID/IP grep, drilldown-host grep, `--help` exit — all clean
  4. Committing the 6 files in a single feat commit (`aa7808a`)
- No re-authoring or content changes were needed.

## User Setup Required

None — saved queries are JSON specs and an apply.sh that the operator runs during the live scale-demo window. No environment variables added; `COMPARTMENT_ID` and `APM_DOMAIN_ID` are documented as required-at-apply-time, not at session start.

## Threat Flags

None — the artifacts are JSON + a shell script with no new network endpoints, no auth paths, no schema changes. T-07-36 and T-07-37 from the plan's threat model are mitigated and verified by tests.

## Next Phase Readiness

- Phase 7 Wave 3 plan 07 is shipped. Wave 3 verification plan can now reference these saved queries as operator-runbook prerequisites.
- Outstanding for the live operator window: operator must (a) confirm OCI APM CLI subcommand shape against the current `oci` version, (b) capture baseline_pod_set before kicking the scale event, (c) snapshot the resulting saved-query IDs back into a follow-up commit if reproducible OCIDs are desired.

## Self-Check: PASSED

- `tools/apm-saved-queries/README.md` — FOUND
- `tools/apm-saved-queries/apply.sh` — FOUND (executable, bash -n clean)
- `tools/apm-saved-queries/oke-pod-count-over-time.json` — FOUND
- `tools/apm-saved-queries/oke-latency-percentiles-during-scale.json` — FOUND
- `tools/apm-saved-queries/oke-trace-propagation-new-pods.json` — FOUND
- `tools/apm-saved-queries/oke-error-saturation-slow-spans.json` — FOUND
- Commit `7bb70b0` (RED) — FOUND in git log
- Commit `aa7808a` (GREEN feat) — FOUND in git log
- `pytest -k apm_saved` — 8/8 PASS
- OCID/IP scan — clean

---
*Phase: 07-oke-autoscaling-and-stress-demo*
*Plan: 07*
*Completed: 2026-05-18*
