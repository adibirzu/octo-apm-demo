---
phase: 7
slug: oke-autoscaling-and-stress-demo
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-18
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (Python), maven-surefire (Java apm-java-demo) |
| **Config file** | `pyproject.toml`, `tests/conftest.py` |
| **Quick run command** | `pytest tests/test_stress_demo_surface.py tests/test_unified_deploy_surface.py -x` |
| **Full suite command** | `pytest tests/ -q && bash deploy/verify.sh` |
| **Estimated runtime** | ~45 seconds (quick), ~3 min (full + verify.sh) |

---

## Sampling Rate

- **After every task commit:** Run quick: `pytest tests/test_stress_demo_surface.py -x`
- **After every plan wave:** Run full suite + `bash deploy/verify.sh`
- **Before `/gsd-verify-work`:** Full suite + verify.sh must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Each task row maps a `<task>` from a PLAN.md to its automated check, sourced from the plan's `<verify><automated>` block.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01.T1 | 07-01 | 1 | SCALE-01 | T-07-01..04a | Wave-0 RED tests for HPA + stressRunner values + OTel pins | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "hpa or rps or java or stress_runner_values or otel or llmetry or obs_field"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-01.T2 | 07-01 | 1 | SCALE-01 | T-07-01, T-07-02 | Raw HPA manifests bumped (shop max=10, java new HPA) | unit (manifest grep) | `pytest tests/test_stress_demo_surface.py -x -k "shop_hpa or java_hpa"` | ✅ deploy/k8s/oke/shop/deployment.yaml, deploy/k8s/oke/apm-java-demo/deployment.yaml | ⬜ pending |
| 07-01.T3 | 07-01 | 1 | SCALE-01 | T-07-04 | Helm chart edits (sole values.yaml owner) + java-gateway-hpa.yaml + stressRunner block | helm-template + pytest | `pytest tests/test_stress_demo_surface.py -x -k "helm or stress_runner_values" && helm template deploy/helm/octo-apm-demo \| grep -c "kind: HorizontalPodAutoscaler"` | ✅ deploy/helm/octo-apm-demo/values.yaml, templates/java-gateway-hpa.yaml | ⬜ pending |
| 07-01.T4 | 07-01 | 1 | SCALE-01 | T-07-04a | D-21 OTel SDK + agent + LLMetry pin bumps with OBS field-shape regression guard | pin diff + regression suite | `pytest tests/test_stress_demo_surface.py -x -k "otel or llmetry or obs_field" && pytest tests/ -k "obs_field_shape or otel_resource_attrs or logging_sdk_contract"` | ✅ shop/requirements.txt, crm/server/requirements.txt, services/apm-java-demo/pom.xml, tools/llmetry/pin.txt | ⬜ pending |
| 07-02.T1 | 07-02 | 1 | SCALE-01, SCALE-02 | T-07-05..09 | Wave-0 RED tests for CA script + adapter values | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "cluster_autoscaler or prometheus_adapter"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-02.T2 | 07-02 | 1 | SCALE-02 | T-07-05, T-07-06, T-07-08, T-07-09 | Idempotent CA operator script with dry-run default + envsubst placeholder for node-pool OCID | shell-syntax + pytest | `pytest tests/test_stress_demo_surface.py -x -k "cluster_autoscaler" && bash -n deploy/oke/configure-cluster-autoscaler.sh && deploy/oke/configure-cluster-autoscaler.sh --help` | ✅ deploy/oke/configure-cluster-autoscaler.sh, deploy/oke/cluster-autoscaler-config.json | ⬜ pending |
| 07-02.T3 | 07-02 | 1 | SCALE-01 | T-07-07 | Prometheus adapter values declare shop_request_rate + java_request_rate as External Metrics | yaml-parse + pytest | `pytest tests/test_stress_demo_surface.py -x -k "prometheus_adapter" && python -c "import yaml; list(yaml.safe_load_all(open('deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml')))"` | ✅ deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml | ⬜ pending |
| 07-03.T1 | 07-03 | 1 | SCALE-03 | T-07-10..16 | Wave-0 RED tests for stress-runner manifests + wrapper + scenarios + single-writer guard | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "stress_runner or scenarios or plan_07_03_does_not_edit"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-03.T2 | 07-03 | 1 | SCALE-03 | T-07-10, T-07-11, T-07-12, T-07-16 | FastAPI wrapper concurrency=1 + SIGTERM + run_id + Pydantic caps | pytest + import smoke | `pytest tests/test_stress_demo_surface.py -x -k "wrapper or pyproject" && python -c "import sys; sys.path.insert(0,'tools/stress-runner'); from octo_stress_runner.main import app"` | ✅ tools/stress-runner/octo_stress_runner/main.py | ⬜ pending |
| 07-03.T3 | 07-03 | 1 | SCALE-03 | T-07-13, T-07-14 | Three k6 scenarios + Dockerfile (no hardcoded hosts/PII) | pytest + grep gate | `pytest tests/test_stress_demo_surface.py -x -k "scenarios or dockerfile"` | ✅ tools/stress-runner/scenarios/{checkout_journey,catalog_browse,login_burst}.js, tools/stress-runner/Dockerfile | ⬜ pending |
| 07-03.T4 | 07-03 | 1 | SCALE-03 | T-07-15 | Raw OKE manifests + Helm templates (minimal RBAC; values.yaml NOT touched by Plan 07-03) | pytest + yaml-parse + helm-template + single-writer guard | `pytest tests/test_stress_demo_surface.py -x -k "stress_runner and (namespace or deployment or service or rbac or helm) or plan_07_03_does_not_edit" && helm template deploy/helm/octo-apm-demo --set stressRunner.enabled=true \| grep -c "octo-stress-runner"` | ✅ deploy/k8s/oke/stress-runner/*.yaml, deploy/helm/octo-apm-demo/templates/stress-runner-*.yaml | ⬜ pending |
| 07-04.T1 | 07-04 | 1 | SCALE-03 | T-07-17, T-07-18 | Wave-0 RED + regression tests for _admin_host helper extraction | TDD-RED (pytest) | `pytest tests/test_admin_host_helper.py -x` | ✅ tests/test_admin_host_helper.py | ⬜ pending |
| 07-04.T2 | 07-04 | 1 | SCALE-03 | T-07-17, T-07-18, T-07-19 | Single-source `_admin_host.py` helper; coordinator.py imports rather than re-implements | pytest GREEN + regression | `pytest tests/test_admin_host_helper.py -x && pytest tests/ -x -k "coordinator"` | ✅ crm/server/modules/_admin_host.py, crm/server/modules/coordinator.py | ⬜ pending |
| 07-05.T1 | 07-05 | 2 | SCALE-03, SCALE-04 | T-07-20..30 | Wave-0 RED tests for /api/admin/stress/* surface (17 tests incl. nav_key) | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "stress_apply or stress_clear or stress_state or stress_presets or stress_page or admin_module or main_includes or oci_monitoring_increment or stress_page_route_passes_nav_key"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-05.T2 | 07-05 | 2 | SCALE-03, SCALE-04 | T-07-20..30 | GREEN — implement endpoints + three-channel MELTS audit + D-17 metrics + nav_key page context | pytest GREEN + regression | `pytest tests/test_stress_demo_surface.py -x -k "stress_apply or stress_clear or stress_state or stress_presets or stress_page or admin_module or main_includes or oci_monitoring_increment or stress_page_route_passes_nav_key" && pytest tests/ -x -k "coordinator or chaos"` | ✅ crm/server/modules/stress_test.py, admin.py, main.py, config.py, shop/server/observability/oci_monitoring.py | ⬜ pending |
| 07-05.T3 | 07-05 | 2 | SCALE-03 | (refactor) | REFACTOR — extract _emit_lifecycle_event helper if needed; keep file ≤ 400 lines | pytest + wc -l | `pytest tests/test_stress_demo_surface.py -x && wc -l crm/server/modules/stress_test.py` | ✅ crm/server/modules/stress_test.py | ⬜ pending |
| 07-06.T1 | 07-06 | 2 | SCALE-03 | T-07-31..35 | Wave-0 RED tests for stress admin template + nav | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "stress_template or base_html_has_stress"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-06.T2 | 07-06 | 2 | SCALE-03 | T-07-31, T-07-32, T-07-33, T-07-34 | stress_test_admin.html clones chaos_admin.html; nonced inline script; reuses style.css tokens | pytest + grep gate | `pytest tests/test_stress_demo_surface.py -x -k "stress_template"` | ✅ crm/server/templates/stress_test_admin.html | ⬜ pending |
| 07-06.T3 | 07-06 | 2 | SCALE-03 | T-07-35 | base.html sidebar nav entry for /admin/stress-test (active when Plan 07-05 page route fires) | pytest + cross-check | `pytest tests/test_stress_demo_surface.py -x -k "base_html_has_stress"` | ✅ crm/server/templates/base.html | ⬜ pending |
| 07-07.T1 | 07-07 | 1 | SCALE-04 | (info-disclosure guards on saved queries) | Wave-0 RED tests for APM saved queries | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "apm_saved"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-07.T2 | 07-07 | 1 | SCALE-04 | T-07-36..38 | Four APM saved queries + README + apply.sh; offline JSON-parse + no live OCIDs | pytest + JSON parse + bash -n | `pytest tests/test_stress_demo_surface.py -x -k "apm_saved" && for f in tools/apm-saved-queries/*.json; do python -c "import json; json.load(open('$f'))"; done && bash -n tools/apm-saved-queries/apply.sh` | ✅ tools/apm-saved-queries/*.json, apply.sh | ⬜ pending |
| 07-08.T1 | 07-08 | 1 | SCALE-04 | (info-disclosure guards on alarm shape) | Wave-0 RED tests for monitoring alarms | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "monitoring_alarms or high_cpu_alarm or hpa_max_replicas_alarm"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-08.T2 | 07-08 | 1 | SCALE-04 | T-07-39..41 | OCI Monitoring alarm definitions + apply.sh; offline JSON-parse | pytest + JSON parse + bash -n | `pytest tests/test_stress_demo_surface.py -x -k "monitoring_alarms or high_cpu_alarm or hpa_max" && for f in tools/monitoring-alarms/*.json; do python -c "import json; json.load(open('$f'))"; done && bash -n tools/monitoring-alarms/apply.sh` | ✅ tools/monitoring-alarms/*.json, apply.sh | ⬜ pending |
| 07-09.T1 | 07-09 | 1 | SCALE-04 | (info-disclosure guards on LA saved-search shape) | Wave-0 RED tests for LA saved searches + dashboard | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py -x -k "la_oke"` | ✅ tests/test_stress_demo_surface.py | ⬜ pending |
| 07-09.T2 | 07-09 | 1 | SCALE-04 | T-07-42, T-07-43 | Four LA saved searches + autoscaling dashboard JSON; smoke test | pytest + JSON parse + smoke | `pytest tests/test_stress_demo_surface.py -x -k "la_oke" && for f in tools/la-saved-searches/oke-autoscaling-*.json; do python -c "import json; json.load(open('$f'))"; done && python tools/la-saved-searches/smoke-test.py` | ✅ tools/la-saved-searches/oke-autoscaling-*.json | ⬜ pending |
| 07-10.T1 | 07-10 | 3 | SCALE-01..04 | T-07-44..46 | Wave-0 RED tests for Lab 11 + LB runbook + unified surface coverage | TDD-RED (pytest) | `pytest tests/test_stress_demo_surface.py tests/test_unified_deploy_surface.py -x -k "lab11 or lb_routing or mkdocs or unified_deploy_surface"` | ✅ tests/test_stress_demo_surface.py, tests/test_unified_deploy_surface.py | ⬜ pending |
| 07-10.T2 | 07-10 | 3 | SCALE-04 | T-07-44, T-07-45 | Lab 11 narrative + LB routing runbook; no live OCIDs/IPs | pytest + grep gate | `pytest tests/test_stress_demo_surface.py -x -k "lab11 or lb_routing"` | ✅ site/workshop/lab-11-oke-autoscaling.md, site/operations/stress-demo-lb-routing.md | ⬜ pending |
| 07-10.T3 | 07-10 | 3 | SCALE-04 | T-07-46 | mkdocs.yml nav + unified deploy surface test extension; mkdocs build strict-green | pytest + mkdocs build | `pytest tests/test_stress_demo_surface.py tests/test_unified_deploy_surface.py -x -k "mkdocs or unified_deploy_surface" && mkdocs build --strict` | ✅ mkdocs.yml, tests/test_unified_deploy_surface.py | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Sampling continuity check:** Every plan's Task 1 is a Wave-0 RED test row that lands a failing pytest assertion before any production code. Subsequent tasks each have an `<automated>` verify reading from `tests/test_stress_demo_surface.py` (or its sibling `tests/test_admin_host_helper.py` / `tests/test_unified_deploy_surface.py`). No 3 consecutive tasks lack automated verification.

---

## Wave 0 Requirements

- [x] `tests/test_stress_demo_surface.py` — created by Plan 07-01 Task 1; extended by every plan's Task 1 (RED rows above)
- [x] `tests/test_unified_deploy_surface.py` — extended by Plan 07-10 Task 1 with stress-runner manifest + CA script checks
- [x] `tests/conftest.py` — existing CRM app fixture covers admin role + host-bound headers via TestClient (no new fixtures required for Plan 07-05 except the mocked stress-runner endpoint, declared inline in test functions per existing project style)
- [x] `tests/test_admin_host_helper.py` — new test file created by Plan 07-04 Task 1 for the shared `_admin_host.py` helper extraction

---

## Validation Architecture — System Boundaries

> Seeded from `07-RESEARCH.md ## Validation Architecture`. Every named boundary must have at least one automated check OR a `manual-only` entry below.

| Boundary | What to prove | Strategy | Automated? |
|----------|---------------|----------|------------|
| HPA decision → scale-up | HPA reads RPS metric, fires scale-up at threshold | Unit: prometheus-adapter rule config parses; Manifest: HPA YAML targets `External` metric `octo_apm_demo_shop_request_rate` | ✅ pytest + yaml lint |
| RPS metric publish | Metric reaches `octo_apm_demo` namespace with `pod_name`/`run_id` dims | Unit: `oci_monitoring.py` publisher receives gauge call with correct dims | ✅ pytest |
| Cluster Autoscaler decision → node add | CA add-on configured with `2:4:<nodepool-ocid>` | Manifest: `configure-cluster-autoscaler.sh` config JSON shape; idempotency: `list-addons` precheck | ✅ shell test + jq schema check |
| Stress audit event shape | Audit event has all MELTS fields (trace_id, span_id, run_id, admin_user, ...) | Unit: `stress_test.py` audit emit matches Phase 5 contract; integration: POST `/api/admin/stress/apply` produces structured log line | ✅ pytest |
| LB header pinning | `X-Octo-Stress-Target: oke` routes to OKE backend-set | Runbook only (live LB apply is operator action) | ⚠️ manual |
| Stress concurrency=1 | Second POST returns 409 with active `run_id` | Integration: pytest with two concurrent POSTs | ✅ pytest |
| Stop button → SIGTERM | `/api/admin/stress/clear` terminates k6 within 30s | Integration: mock subprocess assertion | ✅ pytest |
| Stress run auto-expire | Server-side hard timeout = `duration + 30s` | Unit: timeout calc; integration: short-duration scenario expires | ✅ pytest |
| Helm parity (D-05) | `autoscaling.rps.enabled=false` produces identical manifest to current chart | Helm template diff: `helm template ... --set autoscaling.rps.enabled=false` vs main | ✅ `deploy/verify.sh` extension |
| OBS-01..05 field shape (D-21) | OTel/LLMetry version bump preserves field shape | Schema test: existing OTel field assertions still pass | ✅ pytest |
| Admin host-bound | `/admin/stress-test` rejects non-`admin.${DNS_DOMAIN}` Host | Integration: pytest with mocked Host header | ✅ pytest |
| `stress-operator` role gate | Role added to `_ALLOWED_ROLES`; non-role admin gets 403 | Unit: `admin.py` role list; integration: pytest | ✅ pytest |
| Single-writer of values.yaml | Plan 07-01 sole writer in Wave 1; Plan 07-03 never edits values.yaml | Manifest: `git diff` empty + `stressRunner:` appears exactly once | ✅ pytest |
| nav_key=stress wiring | Plan 07-05 page route passes `nav_key="stress"`; Plan 07-06 base.html consumes | Manifest: pytest grep on stress_test.py + base.html | ✅ pytest |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LB header-routing rule | SCALE-02 / D-09 | Live LB listener config change is operator action (deferred apply) | Runbook in `site/operations/stress-demo-lb-routing.md` — apply rule via OCI Console, then curl with header and verify reaches OKE backend |
| CA add-on apply | SCALE-02 / D-04 | Live `oci ce cluster install-addon` is operator action | Run `deploy/oke/configure-cluster-autoscaler.sh` interactively, confirm prompt, then `kubectl get pods -n kube-system | grep cluster-autoscaler` |
| RPS custom-metrics adapter live apply | SCALE-01 | Live apply gated behind same operator window as CA | Run `helm install prometheus-adapter ...` per Lab 11 prelude |
| Lab 11 walkthrough | SCALE-04 | End-to-end demo flow involves OCI Console + APM + Logan UI | Workshop attendee follows `site/workshop/lab-11-oke-autoscaling.md` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready for execution
