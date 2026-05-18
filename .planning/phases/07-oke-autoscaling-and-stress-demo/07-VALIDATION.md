---
phase: 7
slug: oke-autoscaling-and-stress-demo
status: draft
nyquist_compliant: false
wave_0_complete: false
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

> Filled by planner during PLAN.md generation. Each task row maps a `<task id>` from a PLAN.md to its automated check.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SCALE-01..04 | TBD | TBD | TBD | TBD | TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_stress_demo_surface.py` — new test file, stubs for SCALE-01..04
- [ ] `tests/test_unified_deploy_surface.py` — extend with k6 wrapper + CA script + RPS adapter checks
- [ ] `tests/conftest.py` — ensure stress-test fixtures (mock admin role, host-bound headers) available

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
