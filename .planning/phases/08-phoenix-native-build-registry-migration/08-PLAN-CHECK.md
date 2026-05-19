---
phase: 08-phoenix-native-build-registry-migration
checked: 2026-05-19T00:00:00Z
verdict: gaps_found
score: 7 / 10
reviewer: gsd-plan-checker (pre-execute review)
---

# Phase 8 PLAN-CHECK — Phoenix-Native Build + Registry Migration

8 plans across 6 waves reviewed against ROADMAP success criteria 1..7 and REQUIREMENTS BUILD-01..07. Verdict is **gaps_found** — three closable issues must be resolved before `/gsd-execute-phase 8`. None are security violations; none leave a BUILD-* unmapped; all are mechanical fixes to plan frontmatter or one section of prose.

---

## Per-Dimension Verdict

| # | Dimension | Verdict | One-line justification |
|---|---|---|---|
| 1 | Goal coverage | PASS | Every ROADMAP success criterion 1..7 maps to ≥1 plan; every BUILD-* maps to ≥1 plan. See coverage matrix below. |
| 2 | Dependency correctness | **FAIL** | 08-02 modifies `deploy/oke/jumphost-bootstrap.sh` (created by 08-01) but declares `depends_on: []` and `wave: 1` — parallel with its own input. 08-03 is also in wave 1 with `depends_on: []` but it is independent (different file), so that one is fine. |
| 3 | Artifact contracts | **FAIL** | ARTIFACT-CONTRACT mismatch: 08-04 builds `build-push-one-image.sh` with `--image-dir <path> --image-name <name>` signature. 08-05 invokes it as `--service <repo>` (key_links line 28, action line 74). The `--service` flag does not exist in the 08-04 contract. Executor will hit shell parse error. |
| 4 | Acceptance gates | PASS | Every `truths:` entry has a concrete probe — bash -n, grep gates, helm-template grep counts, kubectl jsonpath audits, crictl pull timing, pytest assertions, mkdocs --strict. No vague truths. |
| 5 | Security compliance | PASS | All 8 plans cite `.planning/SECURITY.md`. Frontmatter `autonomous: false` set on 08-01, 08-02, 08-03, 08-04, 08-07 (operator-gated). 08-05, 08-06, 08-08 marked `autonomous: true` and only touch repo files / OCIR pushes — appropriate. 08-07 explicitly enumerates kubectl set image as the cluster mutation, gated by APPLY=true + interactive confirm. No real OCIDs/IPs/tenancy namespace inline in any plan; verify steps grep for leaks. |
| 6 | TDD discipline | PASS | 08-04 is `type: tdd`; Task 1 is RED commit (file does not exist → FileNotFoundError on read_text) and is explicitly committed before Task 2 GREEN. Other plans are `execute` which is appropriate (shell wrappers, docs, manifest edits). |
| 7 | Frankfurt-fallback preservation | PASS | 08-06 verification step 2 explicitly proves `helm template ... --set global.ociRegion=eu-frankfurt-1` still renders frankfurt refs (≥1). 08-06 step 3 proves envsubst override works. 08-05 has `--allow-non-phx` rollback escape hatch. 08-07 same. 08-08 runbook documents the override + 7-day soak. BUILD-06 preserved. |
| 8 | APM signal continuity | PASS | 08-07 Task 1 specifies `probe_apm_continuity` with window_seconds=300 (5 min), interval=30s, >60s lag aborts via set -e. Concrete oci CLI invocation provided. Implementation note about reusing existing helpers in `tools/apm-saved-queries/` is reasonable. |
| 9 | Cold-pull benchmark | PARTIAL | 08-04 Task 3 step 6 records phoenix cold-pull + best-effort frankfurt comparison for traffic-gen only. 08-04 success_criteria explicitly defers "Full BUILD-05 < 25% comparison happens in Plan 08-07". **However, 08-07 does NOT include a `crictl pull` benchmark step** — its scope is rolling cutover + APM probe. BUILD-05 < 25% acceptance has no plan that fully closes it. Either 08-04 must measure both regions on the same fresh OKE node (not best-effort), or 08-07 must add a benchmark task, or a new step in 08-08 verify-work must run the comparison before declaring BUILD-05 complete. |
| 10 | Plan-size sanity | PASS | 102-269 line bodies, 1-3 tasks each (plus checkpoints). All within single-executor-agent budget. 08-07 (247 lines) and 08-08 (269 lines) are largest but contain detailed inline specs, not bloat. |

---

## BUILD-* Coverage Matrix

| Req | Plans satisfying | Notes |
|---|---|---|
| BUILD-01 (5 phx repos image_count > 0) | 08-04 (traffic-gen), 08-05 (4 app services) | OK |
| BUILD-02 (reproducible jumphost pipeline) | 08-01, 08-02, 08-03, 08-04, 08-05 | OK (full chain) |
| BUILD-03 (phx default + grep gate = 0) | 08-06 | OK — helm values flip + pytest regression gate |
| BUILD-04 (rolling deploy, ≤60s APM gap, canary order) | 08-07 | OK — locked canary order, probe spec, abort path |
| BUILD-05 (cold-pull < 25%) | 08-04 (partial, single service) | **PARTIAL — full < 25% comparison has no owner plan.** Recommend adding a benchmark step in 08-08 verify-work or new task in 08-07. |
| BUILD-06 (helm rollback ≤5min, drill in runbook) | 08-08 Task 2 (rollback section + drill transcript) | OK |
| BUILD-07 (CLAUDE.md update + ADR) | 08-08 Task 1 (ADR), 08-08 Task 2 (runbook documents required CLAUDE.md edit) | OK — operator-side CLAUDE.md edit documented, not executed from repo (correct per scope) |

ROADMAP success criteria 1..7 map cleanly: SC#1 → 08-04/05, SC#2 → 08-01..05, SC#3 → 08-06, SC#4 → 08-07, SC#5 → 08-04/05/07/08, SC#6 → 08-08, SC#7 → 08-08.

---

## Gap List (must close before execute)

### Gap 1 — Dependency error in 08-02 (BLOCKER)

**Symptom:** 08-02 modifies `deploy/oke/jumphost-bootstrap.sh` (the file 08-01 creates) but its frontmatter says `depends_on: []` and `wave: 1`. If the executor honors waves, 08-01 and 08-02 will run in parallel and 08-02 will either fail (file not yet created) or race-condition the file.

**Owner:** Planner agent.

**Fix:** In `08-02-PLAN.md` frontmatter, change:
- `wave: 1` → `wave: 2`
- `depends_on: []` → `depends_on: [08-01]`

Then update ROADMAP.md Phase 8 entry to reshuffle the wave grid:
- Wave 1: 08-01, 08-03 (independent — different files)
- Wave 2: 08-02 (extends 08-01's file)
- Wave 3: 08-04 (depends on 08-01, 08-02, 08-03 — already correct)
- subsequent waves shift accordingly OR keep numbering and accept the irregular grid.

Alternative (lighter touch): merge 08-02's --install mode into 08-01 as a second task, drop 08-02. Reduces plan count to 7 and avoids the cross-wave file edit.

### Gap 2 — Argument-signature mismatch between 08-04 and 08-05 (BLOCKER)

**Symptom:** 08-04 implements `build-push-one-image.sh --image-dir <path> --image-name <name>`. 08-05 key_links and action both call it as `--service <repo>` — a flag that does not exist in 08-04's contract.

**Owner:** Planner agent (08-05).

**Fix:** Two options:

A. Update 08-05 to match 08-04's contract. Replace `--service "$repo"` with `--image-dir "<service-specific-path>" --image-name "$repo"`. Add a small lookup table inside the wrapper:
```bash
declare -A IMAGE_DIRS=(
  [octo-drone-shop]="${REPO_ROOT}/shop"
  [octo-apm-java-demo]="${REPO_ROOT}/services/octo-apm-java-demo"
  [octo-workflow-gateway]="${REPO_ROOT}/services/octo-workflow-gateway"
  [enterprise-crm-portal]="${REPO_ROOT}/services/enterprise-crm-portal"
)
```
(Executor must verify the actual Dockerfile paths against the existing `build-push-images.sh:169-176` analog.)

B. Add a `--service <repo>` selector to 08-04's contract that internally maps to (image_dir, image_name) for the known service set. Update 08-04 Task 1 RED tests and Task 2 GREEN script.

Option A is the safer correction — keeps 08-04 generic (parameterized over arbitrary paths) and pushes the per-service mapping into the wrapper (08-05), which is where it logically belongs.

### Gap 3 — BUILD-05 < 25% acceptance has no owner plan (BLOCKER for full BUILD-05 closure, but downgradable)

**Symptom:** BUILD-05 requires `crictl pull phx... completes in < 25% of frankfurt pull wall-clock time` on the same OKE node, both pulls cold. 08-04 measures traffic-gen on a best-effort basis (frankfurt comparison "when available"). 08-04's own success_criteria says "full BUILD-05 < 25% comparison happens in Plan 08-07" — but 08-07's Task 1 is rolling cutover + APM probe, no `crictl pull` benchmark. 08-08's verify section also has no benchmark step.

**Owner:** Planner agent (decide between 08-07 or 08-08).

**Fix:** Add a benchmark task in 08-08 Task 2 "Rollback drill transcript" or as a new step in 08-08 verification. Recommended language:

```markdown
### BUILD-05 cold-pull benchmark (required during verify-work)

On a fresh OKE worker node (one that has not yet pulled the new tag):
1. `time crictl pull phx.ocir.io/${OCIR_TENANCY}/octo-drone-shop:obs-<head-tag>` — record wall-clock.
2. `crictl rmi phx.ocir.io/${OCIR_TENANCY}/octo-drone-shop:obs-<head-tag>` to evict.
3. `time crictl pull eu-frankfurt-1.ocir.io/${OCIR_TENANCY}/octo-drone-shop:<equivalent-tag>` — record.
4. Compute ratio: phx_seconds / frankfurt_seconds < 0.25 → BUILD-05 PASS, else FAIL.
5. Capture both numbers in the runbook benchmark section.
```

Why `octo-drone-shop` and not `octo-traffic-generator`: BUILD-05 in REQUIREMENTS.md explicitly cites `octo-drone-shop` as the benchmark image (largest layer set, most representative of cold-pull impact).

Alternative: tighten 08-04 Task 3 step 6 to require both pulls on the same OKE node from a known-cold state, and move the benchmark forward to the pilot. But 08-04 only pushes traffic-gen, so the BUILD-05 requirement cannot be satisfied there.

---

## Nit List (style/format, non-blocking)

- 08-01 frontmatter says `requirements: [BUILD-02]` but the plan is essentially NSG + reachability — closer to BUILD-04 infrastructure prep than BUILD-02 (pipeline). Not wrong (BUILD-02 includes "runs natively on jumphost"), just less precise. Acceptable.
- 08-05 Task 2 writes 7 new tests into `tests/test_phoenix_build_surface.py` which was created in 08-04. Plan says "extended in 08-07". The append-vs-overwrite semantics are clear in the action text, but the frontmatter `files_modified` says `tests/test_phoenix_build_surface.py` (same path as 08-04). Not a collision because the file is treated as append-only by both plans, but it deserves an explicit "append, do not overwrite" line in 08-05 Task 2 action. Currently implied.
- 08-07 Task 1 hardcodes 5 deployment+namespace+container triples but acknowledges the executor must verify these against the live cluster before commit. This is correct ("verify before hardcoding" is the right discipline), but the SUMMARY produced by 08-07 should record any names that differed from the plan so 08-08 runbook can stay accurate.
- 08-06 verification step 2 + 3 are excellent (proves the rollback escape hatch). Could be promoted to truths in must_haves for tighter goal-backward traceability.
- 08-08 Task 2 verify command pipes mkdocs build through `tail -5` — that loses the actual exit code in some shells. Recommend `mkdocs build --strict` as a standalone assertion + separate `2>&1 | tail -5` for log capture.

---

## Pre-execute Recommendation

Three blockers, all closable in a follow-on `/gsd-plan-phase 8 --revise` run touching 3 files:
1. 08-02-PLAN.md frontmatter (wave + depends_on)
2. 08-05-PLAN.md key_links + action (replace `--service` with `--image-dir + --image-name`)
3. 08-08-PLAN.md Task 2 verification (add BUILD-05 cold-pull benchmark step)

No security violations, no unmapped BUILD-*, no scope reduction, no architectural-tier issues, no CLAUDE.md compliance issues. Verdict **gaps_found** (not blocked) because each fix is mechanical and bounded; total revision touches ~30 lines across 3 plan files.

After fixes, re-run `/gsd-plan-phase 8 --recheck` to verify clean, then `/gsd-execute-phase 8`.
