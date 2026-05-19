---
phase: 07-oke-autoscaling-and-stress-demo
verified: 2026-05-18T19:23:40Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
  gaps_closed: []
  gaps_remaining: []
  regressions: []
operator_deferred:
  - item: "Cluster Autoscaler add-on live apply"
    requirement: SCALE-02 / D-04
    why_deferred: "Live `oci ce cluster install-addon` against emdemo node pool is operator action gated behind approved rollout window (STATE.md Blockers/Concerns)"
    artifact: deploy/oke/configure-cluster-autoscaler.sh (offline dry-run validated; live apply gated)
  - item: "LB header-routing rule live apply"
    requirement: SCALE-02 / D-09
    why_deferred: "Live OCI Load Balancer routing-policy rule add is operator action gated behind same approved window as CA add-on enablement"
    artifact: site/operations/stress-demo-lb-routing.md (runbook ships; live apply gated)
  - item: "Prometheus-adapter (RPS custom metrics) live install"
    requirement: SCALE-01 / D-05
    why_deferred: "Helm values + manifest ship; `helm install prometheus-adapter` against emdemo gated behind same operator window"
    artifact: deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml
  - item: "APM saved-queries / Monitoring alarms / LA saved-searches live apply"
    requirement: SCALE-04
    why_deferred: "Operator runs `apply.sh APPLY=true` with COMPARTMENT_ID + APM_DOMAIN_ID + NOTIFICATION_TOPIC_OCID at demo-deploy time; offline JSON contracts + dry-run apply scripts verified locally"
    artifact: tools/apm-saved-queries/apply.sh, tools/monitoring-alarms/apply.sh, tools/la-saved-searches/apply.sh
  - item: "Lab 11 end-to-end walkthrough"
    requirement: SCALE-04 / D-22
    why_deferred: "End-to-end demo flow requires live OCI Console + APM + Logan UI + cluster; doc ships, attendee runtime is an operator/workshop action"
    artifact: site/workshop/lab-11-oke-autoscaling.md
gaps: []
deferred:
  - item: "3 pre-existing test failures in tests/test_unified_deploy_surface.py (README docs drift)"
    addressed_in: "Phase 8 (or dedicated docs-drift fix)"
    evidence: ".planning/phases/07-oke-autoscaling-and-stress-demo/deferred-items.md — verified pre-existing via git stash; out of Phase 7 scope"
  - item: "5 pre-existing test failures in tests/test_log_analytics_*.py (payment-gateway/checkout LA SQL drift)"
    addressed_in: "Out of Phase 7 scope — payment-security telemetry surface (commit 92905bc), not autoscaling/stress demo"
    evidence: "Failures reference deploy/oci/log_analytics/searches/payment-gateway-timeline.sql and checkout-security-checks.sql — both untouched by Phase 7"
human_verification: []
---

# Phase 7: OKE Autoscaling and Stress Demo — Verification Report

**Phase Goal:** Demonstrate OCI-native cluster elasticity end-to-end. Wire HPA + Cluster Autoscaler against shop / java APM gateway; expose admin-only `/admin/stress-test` for parameterized, audited k6 load; surface the scale narrative through APM saved queries, Monitoring alarms + custom metrics, and Log Analytics saved searches/dashboard; ship Workshop Lab 11 walkthrough.

**Verified:** 2026-05-18T19:23:40Z
**Status:** PASS
**Re-verification:** No — initial verification

---

## Success Criteria — Goal Achievement

| # | Success Criterion | Requirement | Status | Evidence |
|---|-------------------|-------------|--------|----------|
| 1 | HPA scaling for shop + java APM gateway with sensible CPU/memory/RPS targets | SCALE-01 | VERIFIED | shop HPA `min=2/max=10` + java HPA `min=2/max=6` in raw manifests + Helm; D-05 RPS metric gated behind `autoscaling.rps.enabled=false` default |
| 2 | OKE Cluster Autoscaler configured against worker pool | SCALE-02 | VERIFIED | `deploy/oke/configure-cluster-autoscaler.sh` (executable, dry-run default, idempotent upsert via `oci ce cluster install-addon`); operator-gated apply |
| 3 | Admin-only `/admin/stress-test` page with parameterized load + safe-stop + audit | SCALE-03 | VERIFIED | `crm/server/modules/stress_test.py` + `stress_test_admin.html`; admin-host + admin-role gated; three-channel MELTS audit (span + push_log + increment_stress_run); concurrency=1, SIGTERM-on-stop, Pydantic caps |
| 4 | APM saved queries + Monitoring alarms + Log Analytics dashboards capturing scale narrative | SCALE-04 | VERIFIED | 4 APM JSONs + 2 alarm JSONs + 4 LA saved-searches + dashboard JSON; all parse, all carry `run_id` pivot; D-20 drilldown links embedded |
| 5 | Workshop Lab 11 walking the full demo | SCALE-04 / D-22 | VERIFIED | `site/workshop/lab-11-oke-autoscaling.md` (271 lines, 7-step arc, cross-links to Labs 01/05/09); mkdocs `--strict` green |

**Score:** 5/5 success criteria VERIFIED.

---

## Required Artifacts — Existence + Substance + Wiring + Data Flow

### Plan 07-01 — HPA + Helm + OTel/LLMetry pin

| Artifact | Status | Evidence |
|----------|--------|----------|
| `deploy/k8s/oke/shop/deployment.yaml` | VERIFIED | HPA bumped to `minReplicas=2, maxReplicas=10` (lines 380-381) |
| `deploy/k8s/oke/apm-java-demo/deployment.yaml` | VERIFIED | New HPA block `minReplicas=2, maxReplicas=6` (lines 193-203) |
| `deploy/helm/octo-apm-demo/templates/java-gateway-hpa.yaml` | VERIFIED | New template, 1545 bytes |
| `deploy/helm/octo-apm-demo/values.yaml` | VERIFIED | `autoscaling.rps.enabled: false` default (D-05); `stressRunner.enabled: false` (sole-writer contract) |
| `tools/llmetry/pin.txt` | VERIFIED | `llmetry==0.5.0` pin + bump rule documented |
| OTel SDK pin | VERIFIED | `opentelemetry-api==1.41.1` in `shop/requirements.txt` |

### Plan 07-02 — Cluster Autoscaler + Prometheus adapter

| Artifact | Status | Evidence |
|----------|--------|----------|
| `deploy/oke/configure-cluster-autoscaler.sh` | VERIFIED | 7024 bytes, executable, `bash -n` clean, dry-run default, envsubst placeholder for `OKE_NODE_POOL_OCID` |
| `deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml` | VERIFIED | 3761 bytes, External Metrics for `shop_request_rate` + `java_request_rate` |

### Plan 07-03 — k6 stress-runner pod + FastAPI wrapper

| Artifact | Status | Evidence |
|----------|--------|----------|
| `tools/stress-runner/octo_stress_runner/main.py` | VERIFIED | FastAPI app, concurrency=1, SIGTERM handler, run_id propagation |
| `tools/stress-runner/scenarios/{checkout_journey,catalog_browse,login_burst}.js` | VERIFIED | All 3 k6 scenarios present; all carry `X-Octo-Stress-Target: oke` header (D-09 LB pin) |
| `tools/stress-runner/Dockerfile` | VERIFIED | Multi-stage grafana/k6 → python:3.12 |
| `deploy/k8s/oke/stress-runner/{namespace,deployment,service,rbac}.yaml` | VERIFIED | All 4 raw manifests present |
| `deploy/helm/octo-apm-demo/templates/stress-runner-{deployment,service,rbac}.yaml` | VERIFIED | All 3 Helm templates; gated behind `stressRunner.enabled` (default false) |

### Plan 07-04 — `_admin_host` helper extraction (Phase 5 regression guard)

| Artifact | Status | Evidence |
|----------|--------|----------|
| `crm/server/modules/_admin_host.py` | VERIFIED | Contains `_require_admin_host`, `_request_host`, `_configured_admin_hosts` |
| `crm/server/modules/coordinator.py` | VERIFIED | Imports from `_admin_host` (verbatim refactor); no duplicate implementation |
| `crm/server/modules/stress_test.py` | VERIFIED | Imports `_require_admin_host` from same shared module — single-source guarantee |
| `tests/test_admin_host_helper.py` | VERIFIED | 10/10 tests pass; structural anti-drift test guards regression |

### Plan 07-05 — `/api/admin/stress/*` API + three-channel MELTS audit

| Artifact | Status | Evidence |
|----------|--------|----------|
| `crm/server/modules/stress_test.py` | VERIFIED | 4 endpoints (`presets`, `apply`, `clear`, `state`) + page route; audit-before-side-effect ordering; nav_key="stress" wiring |
| `shop/server/observability/oci_monitoring.py` | VERIFIED | `increment_stress_run(run_id, status)` helper at line 331 |
| `crm/server/observability/oci_monitoring.py` | VERIFIED | Mirror `increment_stress_run` at line 264 — resolves CRM-side import |
| `crm/server/main.py` | VERIFIED | `stress_admin_router` + `stress_admin_page_router` both included (lines 223-225) |
| `crm/server/modules/admin.py` | VERIFIED | `_ALLOWED_ROLES` includes `stress-operator` (line 20) |
| Audit channels | VERIFIED | `push_log`, `increment_stress_run`, OTel `tracer.start_as_current_span` all present + wired in `_emit_lifecycle_event` |

### Plan 07-06 — Admin template + sidebar nav

| Artifact | Status | Evidence |
|----------|--------|----------|
| `crm/server/templates/stress_test_admin.html` | VERIFIED | 233 lines, extends base.html, CSP-nonced inline JS, ARIA-live audit `<pre>`, 2s/10s polling cadence, `prefers-reduced-motion` guard |
| `crm/server/templates/base.html` | VERIFIED | Sidebar nav entry "Stress Test" with `nav_key == 'stress'` active-state |

### Plan 07-07 — APM saved queries

| Artifact | Status | Evidence |
|----------|--------|----------|
| `tools/apm-saved-queries/oke-{pod-count-over-time,latency-percentiles-during-scale,trace-propagation-new-pods,error-saturation-slow-spans}.json` | VERIFIED | All 4 D-16 saved queries present; structural tokens (`service.namespace`, `k8s.pod.name`, `p95`, `span.status`); D-20 external_drilldowns embedded |
| `tools/apm-saved-queries/apply.sh` | VERIFIED | Dry-run-default + confirm-on-APPLY pattern (mirrors LA apply.sh) |

### Plan 07-08 — Monitoring alarms

| Artifact | Status | Evidence |
|----------|--------|----------|
| `tools/monitoring-alarms/octo-high-cpu-saturation.json` | VERIFIED | D-18 #1: WARNING / PT2M / `shop_cpu_saturation_pct > 80` |
| `tools/monitoring-alarms/octo-hpa-at-max-replicas.json` | VERIFIED | D-18 #2: CRITICAL / PT5M / `shop_pod_count >= 10` (cross-file invariant: matches `shop.autoscaling.maxReplicas` in values.yaml) |
| `tools/monitoring-alarms/apply.sh` | VERIFIED | Dry-run default, idempotent upsert via list-by-display-name, envsubst placeholder sanity check |

### Plan 07-09 — Log Analytics saved searches + dashboard

| Artifact | Status | Evidence |
|----------|--------|----------|
| `tools/la-saved-searches/oke-autoscaling-{hpa-events,ca-events,kubelet-pressure,stress-audit}.json` | VERIFIED | All 4 D-19 saved searches present |
| `tools/la-saved-searches/oke-autoscaling-dashboard.json` | VERIFIED | "OKE Autoscaling Timeline" dashboard, 4 tiles, PT1H time range |
| `tools/la-saved-searches/apply.sh` | VERIFIED | Zero diff (auto-discovery contract preserved per acceptance criterion) |

### Plan 07-10 — Lab 11 + LB runbook + surface test closure

| Artifact | Status | Evidence |
|----------|--------|----------|
| `site/workshop/lab-11-oke-autoscaling.md` | VERIFIED | 271 lines, 7-step arc; cross-links to Labs 01/05/09; D-20 drilldown section; mkdocs strict-green |
| `site/operations/stress-demo-lb-routing.md` | VERIFIED | 173 lines, case-insensitive header match, dry-run + rollback documented |
| `mkdocs.yml` | VERIFIED | Nav entries for Lab 11 + LB runbook added |
| `tests/test_unified_deploy_surface.py` | VERIFIED | 2 new tests for stress-runner manifest + CA script presence |

---

## Key Link Verification (Wiring)

| From | To | Via | Status | Detail |
|------|----|-----|--------|--------|
| stress_test.py `_emit_lifecycle_event` | OTel span | `tracer.start_as_current_span("admin.stress.apply")` | WIRED | line 239; `stress.run_id`, `stress.scenario`, `admin.host` attrs |
| stress_test.py `_emit_lifecycle_event` | Log Analytics | `push_log("INFO", f"stress_test.{status}", **fields)` | WIRED | line 162; `run_id` + MELTS fields |
| stress_test.py `_emit_lifecycle_event` | OCI Monitoring counter | `increment_stress_run(run_id, status)` | WIRED | line 166; counter in `octo_apm_demo` namespace |
| stress_test.py `/apply` route | Stress runner pod | HTTPX POST to in-cluster k6 wrapper | WIRED | concurrency=1 → 409 with `active_run_id` when busy |
| stress_test.py routes | Admin-host gate | `Depends(_require_admin_host)` | WIRED | lines 121, 127; shared helper from `_admin_host.py` |
| stress_test.py routes | Admin-role gate | `Depends(require_admin_user)` | WIRED | same dependency chain |
| k6 scenarios | OKE backend pin | `X-Octo-Stress-Target: oke` header in `params.headers` | WIRED | all 3 scenarios; LB runbook documents matching rule |
| base.html nav | Stress page | `nav_key == 'stress'` Jinja conditional | WIRED | template + route context match |
| stress-runner Helm | Default-off gate | `{{- if .Values.stressRunner.enabled }}` | WIRED | `helm template` with default produces 0 mentions; `--set stressRunner.enabled=true` produces 14 mentions |
| Shop HPA Helm | RPS metric gate | `{{- if .Values.shop.autoscaling.rps.enabled }}` | WIRED | `rps.enabled=false` (default) emits 0 RPS metric refs; `rps.enabled=true` emits the External metric |

---

## Helm Parity (D-05 Backward Compatibility Check)

```
$ helm template deploy/helm/octo-apm-demo --set global.image.tenancy=test-tenancy | grep -c "kind: HorizontalPodAutoscaler"
3   # crm + shop + java-gateway

$ helm template ... --set shop.autoscaling.rps.enabled=false --set javaGateway.autoscaling.rps.enabled=false | grep -cE "shop_request_rate|java_request_rate"
0   # backward-compatible: no RPS metric refs

$ helm template ... --set shop.autoscaling.rps.enabled=true | grep -cE "shop_request_rate"
1   # opt-in path works

$ helm template ... --set stressRunner.enabled=true | grep -c "octo-stress-runner"
14   # stress-runner only when explicitly enabled

$ helm template ... (default) | grep -c "octo-stress-runner"
0   # additive — no surprise resources
```

D-05 contract holds: `autoscaling.rps.enabled=false` and `stressRunner.enabled=false` defaults are bit-additive to the legacy chart output.

---

## Cross-Phase Regression Check — Phase 5 Admin-Host Boundary

| Check | Status | Evidence |
|-------|--------|----------|
| Single-source `_admin_host` helper | VERIFIED | `crm/server/modules/_admin_host.py` is the only definition of `_require_admin_host` |
| `coordinator.py` imports (not re-implements) | VERIFIED | `from server.modules._admin_host import _require_admin_host` (line 18) |
| `stress_test.py` imports from same helper | VERIFIED | Same import path — drift impossible by construction |
| `tests/test_admin_host_helper.py` regression suite | PASS | 10/10 tests pass |
| Coordinator/chaos test suite | PASS | Per Plan 07-04 SUMMARY: 97/97 green |
| Structural anti-drift test | VERIFIED | Test exists; passes on current tree |

Phase 5 admin-host contract bit-identical post-refactor.

---

## Security Scan (CLAUDE.md global rule — no PII, secrets, public IPs)

| Surface | Result |
|---------|--------|
| Phase 7 published docs (`site/workshop/lab-11-*.md`, `site/operations/stress-demo-*.md`) | CLEAN — no live OCIDs, no public IPs |
| Phase 7 tooling JSON (`tools/apm-saved-queries/`, `tools/monitoring-alarms/`, `tools/la-saved-searches/oke-autoscaling-*`) | CLEAN — only envsubst placeholders (`${COMPARTMENT_ID}`, `${NOTIFICATION_TOPIC_OCID}`) |
| Phase 7 Helm templates + raw manifests | CLEAN — no live OCIDs |
| `deploy/oke/configure-cluster-autoscaler.sh` | CLEAN — only `ocid1.cluster.oc1..dry-run-placeholder` literal (intentional, gated behind dry-run default) |
| k6 scenarios | CLEAN — only `${SHOP_HOST}` / `${TARGET_HOST}` env-driven targets |
| `crm/server/modules/stress_test.py` + `_admin_host.py` | CLEAN |
| `terraform.tfstate` (pre-existing, contains real OCIDs) | OUT OF SCOPE — gitignored (verified in `.gitignore`); not Phase-7-introduced; not committed |

No new secret-leak surface introduced by Phase 7.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 7 surface tests pass | `pytest tests/test_stress_demo_surface.py -q` | 103 passed in 0.66s | PASS |
| Admin-host helper tests pass | `pytest tests/test_admin_host_helper.py -q` | 10 passed | PASS |
| Stress-runner FastAPI app importable | `python -c "from octo_stress_runner.main import app"` | (no import errors) | PASS |
| Helm chart renders w/ defaults | `helm template ... --set global.image.tenancy=test-tenancy` | 3 HPAs, 0 stress-runner | PASS |
| Helm chart renders w/ stressRunner.enabled=true | `helm template --set stressRunner.enabled=true` | 14 stress-runner mentions | PASS |
| `mkdocs build --strict` | `mkdocs build --strict` | exit 0, "Documentation built in 2.04s" | PASS |
| All Phase 7 JSON files parse | `python -c "import json; json.load(open(...))"` per file | All 10 JSON files parse | PASS |
| `configure-cluster-autoscaler.sh` syntax | `bash -n deploy/oke/configure-cluster-autoscaler.sh` | exit 0 | PASS |
| All apply.sh scripts syntax | `bash -n tools/*/apply.sh` | exit 0 each | PASS |

---

## Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| SCALE-01 | HPA expansion (shop, crm, java-apm) with CPU+memory + D-05 RPS gate default-off | SATISFIED | shop max=10, java max=6, crm unchanged (D-01); `autoscaling.rps.enabled=false` default verified via `helm template` parity check |
| SCALE-02 | Idempotent dry-run-default operator script for Cluster Autoscaler add-on + prometheus-adapter values | SATISFIED | `configure-cluster-autoscaler.sh` + `prometheus-adapter-values.yaml` ship; live apply operator-gated |
| SCALE-03 | Admin-only `/admin/stress-test` with three-channel MELTS audit + host-bound + k6 internal-key | SATISFIED | Endpoints + template + audit channels all wired; admin-host enforcement verified |
| SCALE-04 | APM saved queries + Monitoring alarms + LA saved-searches + dashboard via existing apply tooling, offline contract tests | SATISFIED | 4 APM + 2 alarms + 4 LA + dashboard; all JSON parses; apply.sh dry-run default mirrors LA pattern |

No orphaned requirements. All 4 SCALE-* requirements claimed by plans + verified in codebase.

---

## Anti-Pattern Scan (Phase 7 files)

| Check | Result |
|-------|--------|
| Debt markers (`TBD`, `FIXME`, `XXX`) in Phase 7 source | CLEAN — only `XXXXXX` mktemp templates (not debt) |
| Warning markers (`TODO`, `HACK`, `PLACEHOLDER`) | None blocking |
| Empty implementations / stub returns | None — `stress_test.py` audit + endpoint logic substantive |
| Hardcoded empty data flowing to render | None — page route passes substantive context (`nav_key`, `cfg`, `brand_logo_url`) |
| Hardcoded credentials / secrets | None in Phase 7 surface |

---

## Deferred / Out-of-Scope Items (Informational)

Three pre-existing test failures in `tests/test_unified_deploy_surface.py` and five pre-existing failures in `tests/test_log_analytics_*.py` were observed during verification. Both groups were verified pre-existing (failures persist with all Phase 7 edits stashed) and are out of Phase 7 scope:

- **Unified deploy surface failures** (3): assert README.md content that has been restructured by an earlier commit; logged to `.planning/phases/07-oke-autoscaling-and-stress-demo/deferred-items.md`.
- **Log Analytics attack assets failures** (5): assert `payment-gateway-timeline.sql` / `checkout-security-checks.sql` query shape — these files belong to a separate payment-security telemetry surface (introduced by commit `92905bc feat: add payment security telemetry dashboards`), unrelated to autoscaling/stress demo.

Recommendation: open a separate docs-drift / LA-LAQL-cleanup phase or roll into Phase 8.

---

## Operator-Deferred Live OCI Actions (Expected — see STATE.md Blockers/Concerns)

These items are EXPECTED to remain unverified locally per the project's "shared emdemo resources are live" boundary. They are pre-baked for operator execution during an approved rollout window:

| Action | Artifact | Status |
|--------|---------|--------|
| `oci ce cluster install-addon` (Cluster Autoscaler) | `deploy/oke/configure-cluster-autoscaler.sh` | Awaits operator window |
| OCI LB routing-policy rule add | `site/operations/stress-demo-lb-routing.md` | Awaits operator window |
| `helm install prometheus-adapter` | `deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml` | Awaits operator window |
| APM saved queries `apply.sh APPLY=true` | `tools/apm-saved-queries/apply.sh` | Awaits operator window |
| Monitoring alarms `apply.sh APPLY=true` | `tools/monitoring-alarms/apply.sh` | Awaits operator window |
| LA saved searches `apply.sh APPLY=true` | `tools/la-saved-searches/apply.sh` | Awaits operator window |
| Lab 11 end-to-end attendee walkthrough | `site/workshop/lab-11-oke-autoscaling.md` | Awaits workshop session |

These do NOT block the verification verdict — all offline contracts, dry-run paths, and apply-script shapes are verified locally.

---

## Overall Verdict

**PASS** — Phase 7 OKE Autoscaling and Stress Demo goal achieved.

- All 5 success criteria VERIFIED in the codebase (not just claimed in SUMMARY.md).
- All 4 SCALE-* requirements SATISFIED with offline contract evidence.
- Phase 5 admin-host boundary regression-checked: no drift; helper single-source.
- Helm D-05 backward-compatibility holds: `autoscaling.rps.enabled=false` and `stressRunner.enabled=false` defaults produce additive-only manifests.
- Security scan clean: no live OCIDs / public IPs / secrets in Phase-7-introduced files.
- All 103 Phase 7 surface tests + 10 admin-host helper tests pass; `mkdocs build --strict` green.
- Three-channel MELTS audit (OTel span + push_log + OCI Monitoring counter) wired and traceable via `run_id` end-to-end.
- Live OCI apply actions (CA add-on, LB rule, prometheus-adapter, saved-artifact apply.sh runs) appropriately gated and deferred to an operator window per STATE.md Blockers/Concerns.

No gap-closure plan required. Phase 7 is ready for `/gsd-ship 7`.

---

*Verified: 2026-05-18T19:23:40Z*
*Verifier: Claude (gsd-verifier, Opus 4.7 1M)*
