---
phase: 07-oke-autoscaling-and-stress-demo
plan: 08
subsystem: monitoring-alarms
tags: [monitoring, alarms, oci, observability, scale-narrative]
requires:
  - D-17 (shop_cpu_saturation_pct + shop_pod_count metrics from plan 07-05)
  - octo_apm_demo Monitoring namespace (Phase 1 OBS-05)
provides:
  - D-18 #1 alarm — High CPU saturation (alarm-path validation)
  - D-18 #2 alarm — HPA stuck at maxReplicas
  - operator-gated apply.sh wrapper (dry-run default + confirm phrase)
affects:
  - tools/ surface area (new monitoring-alarms subdir)
tech_stack_added:
  - OCI Monitoring alarm definitions (MQL queries)
  - envsubst-based OCID placeholder pattern
patterns:
  - mirrors tools/apm-saved-queries/apply.sh + tools/la-saved-searches/apply.sh
  - dry-run + APPLY=true + interactive confirm phrase
  - idempotent upsert (list-by-display-name then create-or-update)
key_files:
  created:
    - tools/monitoring-alarms/README.md
    - tools/monitoring-alarms/octo-high-cpu-saturation.json
    - tools/monitoring-alarms/octo-hpa-at-max-replicas.json
    - tools/monitoring-alarms/apply.sh
  modified:
    - tests/test_stress_demo_surface.py (+125 lines, 7 new tests)
decisions:
  - alarm thresholds hardcoded in JSON; cross-file invariant test guards drift vs values.yaml
  - upsert via list-by-display-name (mirrors install-oci-kubernetes-monitoring.sh idempotency)
  - envsubst-temp-dir approach keeps committed JSON portable across compartments/tenants
metrics:
  tasks_completed: 2
  duration_minutes: ~5
  files_created: 4
  files_modified: 1
  tests_added: 7
  completed_date: 2026-05-18
requirements:
  - SCALE-04
---

# Phase 7 Plan 08: OCI Monitoring Alarms Summary

Ship the two D-18 OCI Monitoring alarms — `shop_cpu_saturation_pct > 80`
(WARNING, PT2M) and `shop_pod_count >= 10` (CRITICAL, PT5M) — as
committed JSON specs in a new `tools/monitoring-alarms/` directory,
with an operator-gated `apply.sh` wrapper that mirrors the existing
`tools/apm-saved-queries/` and `tools/la-saved-searches/` patterns.

## What Shipped

### Tests (RED → GREEN)

7 new assertions in `tests/test_stress_demo_surface.py`:

| Test | Asserts |
|------|---------|
| `test_monitoring_alarms_directory_exists` | `tools/monitoring-alarms/` + README present |
| `test_high_cpu_alarm_valid` | JSON parses; `octo_apm_demo` namespace; `shop_cpu_saturation_pct`; `> 80`; `PT2M` |
| `test_hpa_max_replicas_alarm_valid` | JSON parses; `octo_apm_demo` namespace; `shop_pod_count`; `>= 10`; `PT5M` |
| `test_monitoring_alarms_apply_script_dry_run_default` | `apply.sh` executable; `APPLY:=false`; confirm prompt |
| `test_monitoring_alarms_use_envsubst_for_ocids` | `${COMPARTMENT_ID}` + `${NOTIFICATION_TOPIC_OCID}` placeholders |
| `test_monitoring_alarms_no_live_ocids` | No `ocid1.` substring leaks anywhere in directory |
| `test_hpa_max_replicas_value_matches_helm_values` | Cross-file invariant: alarm threshold == `shop.autoscaling.maxReplicas` in values.yaml |

RED commit: `fb1682a` — 4 failed / 4 passed (early-return guards).
GREEN commit: `4095d97` — 8 passed / 0 failed.

### Alarms

**`octo-high-cpu-saturation.json`** (D-18 #1, alarm-path validation):
```
WARNING / PT2M / shop_cpu_saturation_pct[1m].mean() > 80
```
Expected to fire on every stress run during Phase 7 demo — this is how
we validate the alarm wiring end-to-end.

**`octo-hpa-at-max-replicas.json`** (D-18 #2, capacity ceiling):
```
CRITICAL / PT5M / shop_pod_count[1m].mean() >= 10
```
Indicates the HPA is stuck at maxReplicas and the cluster may need
capacity beyond Cluster Autoscaler max=4 nodes.

### `apply.sh` Wrapper

Mirrors `tools/apm-saved-queries/apply.sh` shape:
- `set -euo pipefail` + `require_tool` helper (python3, oci, jq, envsubst)
- `APPLY=false` default — dry-run lists what would change and writes
  resolved payloads to a tempdir for inspection
- `APPLY=true` → interactive `Type 'APPLY' to confirm:` phrase prompt
- Idempotent upsert: `oci monitoring alarm list --display-name "<name>"`
  then update if found, create otherwise (parallels the
  `install-oci-kubernetes-monitoring.sh` pattern)
- Hard-fails if `COMPARTMENT_ID` or `NOTIFICATION_TOPIC_OCID` unset
- Sanity-checks that envsubst resolved every `${VAR}` before mutating

## Verification

```bash
$ python3 -m pytest tests/test_stress_demo_surface.py -k "monitoring_alarms or high_cpu_alarm or hpa_max_replicas"
8 passed, 45 deselected in 0.13s

$ bash -n tools/monitoring-alarms/apply.sh   # exits 0
$ tools/monitoring-alarms/apply.sh --help    # exits 0
$ for f in tools/monitoring-alarms/*.json; do python3 -c "import json; json.load(open('$f'))"; done
# both parse OK

$ grep -rE 'ocid1\.' tools/monitoring-alarms/
# (no matches — clean)

$ grep -rE '([0-9]{1,3}\.){3}[0-9]{1,3}' tools/monitoring-alarms/
# (no matches — no IPs)
```

## Deviations from Plan

**1. [Rule 1 - Bug] README initially leaked literal `ocid1.` substring**
- **Found during:** Task 2 acceptance check
- **Issue:** README mentioned "no `ocid1.` substring leaks" verbatim, which
  the regex-based test caught as a leak.
- **Fix:** Reworded README line to "no OCID-prefix substring" (preserves
  meaning, removes the regex hit).
- **Files modified:** `tools/monitoring-alarms/README.md`
- **Commit:** folded into `4095d97`

**2. [Rule 2 - Critical functionality] Added unresolved-placeholder
sanity check in `apply.sh`**
- **Reason:** Without this, a misconfigured operator environment could
  silently send `${COMPARTMENT_ID}` as a literal string to OCI and
  either mis-attribute the alarm or error out cryptically. The check
  greps the post-`envsubst` payload for any remaining `${[A-Z_]+}`
  pattern and hard-fails before any mutation.
- **Why critical:** Trust-boundary protection on the operator → OCI
  Monitoring path (T-07-40 in the plan's threat register).

**3. [Rule 2 - Critical functionality] Tempdir cleanup behavior**
- **Reason:** In dry-run mode, kept the tempdir so the operator can
  inspect the resolved JSON before re-running with `APPLY=true`. In
  apply mode, the EXIT trap removes it.

Total commits: 2 (1 RED, 1 GREEN). No auth gates. No checkpoints hit.

## Threat Flags

None. All surface introduced (alarm JSON specs + operator shell wrapper)
is covered by the existing `<threat_model>` register in
`07-08-PLAN.md` (T-07-39, T-07-40, T-07-41). No new trust boundaries
introduced.

## Self-Check: PASSED

- FOUND: tools/monitoring-alarms/README.md
- FOUND: tools/monitoring-alarms/octo-high-cpu-saturation.json
- FOUND: tools/monitoring-alarms/octo-hpa-at-max-replicas.json
- FOUND: tools/monitoring-alarms/apply.sh (executable bit set)
- FOUND: tests/test_stress_demo_surface.py (7 new tests; all passing)
- FOUND: commit fb1682a (RED tests)
- FOUND: commit 4095d97 (alarms + apply.sh)
