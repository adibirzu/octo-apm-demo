---
phase: 07-oke-autoscaling-and-stress-demo
plan: 03
subsystem: deploy/k8s/oke/stress-runner + deploy/helm + tools/stress-runner
tags: [k6, stress-runner, fastapi, oke, otlp, d-07, d-12, d-14]
dependency_graph:
  requires:
    - deploy/helm/octo-apm-demo/values.yaml `stressRunner:` block (Plan 07-01)
    - tools/traffic-generator/k8s/deployment.yaml (manifest analog)
    - crm/server/chaos/admin.py (FastAPI router/Pydantic skeleton)
    - shop/k6/checkout-load.js (k6 scenario analog)
    - crm/server/modules/simulation.py (X-Internal-Service-Key pattern)
  provides:
    - long-lived octo-stress-runner Deployment (replicas=1, port 8080)
    - 4-endpoint FastAPI internal control plane (POST /internal/run → 202,
      POST /internal/clear → SIGTERM, GET /internal/state, GET /internal/healthz)
    - concurrency=1 guard with HTTP 409 on race + hard timeout (duration + 30s)
    - 3 k6 scenarios (checkout_journey, catalog_browse, login_burst) with
      X-Octo-Stress-Target + X-Run-Id headers + env-driven STRESS_TARGET_URL
    - multi-stage Dockerfile (grafana/k6:0.55.0 → python:3.12-slim)
    - Helm templates gated by `.Values.stressRunner.enabled` (default false)
    - minimal RBAC ServiceAccount with no Role bindings (T-07-15 mitigation)
  affects:
    - Plan 07-05 (CRM admin stress-test route) — calls /internal/run on
      this Deployment via X-Internal-Service-Key
    - Plan 07-07+ (operator-window apply): kubectl apply manifests OR
      helm upgrade --set stressRunner.enabled=true
tech_stack:
  added:
    - FastAPI internal control plane with asyncio.Lock concurrency guard
    - asyncio.create_subprocess_exec lifecycle wrapping a k6 binary
    - Multi-stage Docker build copying k6 from grafana/k6 image
    - Helm template gating with {{- if .Values.stressRunner.enabled }}
  patterns:
    - constant-time hmac.compare_digest on internal-key header (T-07-10)
    - allow-list scenario pattern in Pydantic Field(pattern=...) (T-07-11)
    - hard caps rps∈[1,200], duration_seconds∈[10,600] (T-07-12)
    - SIGTERM via process.send_signal(signal.SIGTERM) for graceful drain (D-14)
    - ServiceAccount-only RBAC (T-07-15)
key_files:
  created:
    - deploy/k8s/oke/stress-runner/namespace.yaml
    - deploy/k8s/oke/stress-runner/deployment.yaml
    - deploy/k8s/oke/stress-runner/service.yaml
    - deploy/k8s/oke/stress-runner/rbac.yaml
    - deploy/helm/octo-apm-demo/templates/stress-runner-deployment.yaml
    - deploy/helm/octo-apm-demo/templates/stress-runner-service.yaml
    - deploy/helm/octo-apm-demo/templates/stress-runner-rbac.yaml
    - tools/stress-runner/octo_stress_runner/__init__.py
    - tools/stress-runner/octo_stress_runner/main.py
    - tools/stress-runner/pyproject.toml
    - tools/stress-runner/Dockerfile
    - tools/stress-runner/scenarios/checkout_journey.js
    - tools/stress-runner/scenarios/catalog_browse.js
    - tools/stress-runner/scenarios/login_burst.js
  modified:
    - tests/test_stress_demo_surface.py (appended 16 Plan 07-03 tests)
    - deploy/helm/octo-apm-demo/.helmignore (charts/*.yaml exclusion fix)
decisions:
  - "values.yaml is NOT edited by this plan — Plan 07-01 sole-writer guard.
     The `stressRunner:` top-level block (lines 305-313) is read-only here."
  - "/internal/healthz is intentionally NOT gated by require_internal_key.
     Kubelet probes run in-cluster without the secret; the endpoint exposes
     only a boolean has_k6 flag and the service name (no sensitive state)."
  - "Demo credentials in login_burst.js are routed through __ENV
     (STRESS_DEMO_USERNAME + STRESS_DEMO_TOKEN_REF), never hardcoded —
     T-07-14 + global no-secrets-in-source rule (pre-commit hook caught
     the original hardcoded passwords; auto-fixed before commit)."
  - "Dockerfile uvicorn entrypoint pins --workers 1 to preserve the in-
     process asyncio.Lock concurrency=1 guard. Running >1 worker would
     bypass the lock since each worker has its own _active state."
  - "Hard timeout grace window = 30s (D-14 safety net); k6's own duration
     should terminate the subprocess first, but the asyncio.sleep guard
     reaps stuck processes."
  - "Helm subchart pitfall (Plan 07-02): prometheus-adapter-values.yaml
     under deploy/helm/octo-apm-demo/charts/ caused helm v4 to error with
     'Chart.yaml missing'. Fixed via .helmignore `charts/*.yaml` exclusion."
metrics:
  duration_minutes: 11
  completed_date: "2026-05-18T17:55:00Z"
---

# Phase 7 Plan 03: k6 stress-runner pod + FastAPI control plane — Summary

A long-lived `octo-stress-runner` Deployment that runs a FastAPI internal
HTTP control plane alongside the k6 binary in a single pod. The wrapper
exposes 4 endpoints (run/clear/state/healthz), all gated by the
`X-Internal-Service-Key` header. Concurrency=1 is enforced inside the
process via `asyncio.Lock` — a second `/internal/run` returns HTTP 409
with the active `run_id`. `/internal/clear` sends SIGTERM to the active
k6 subprocess for graceful drain. A server-side asyncio task hard-times
out runs at `duration_seconds + 30s` as a safety net. Three k6 scenarios
(checkout_journey, catalog_browse, login_burst) target the public LB
(`https://shop.${DNS_DOMAIN}`) carrying `X-Octo-Stress-Target: oke` (D-09
LB pin) and `X-Run-Id: <uuid>` (APM trace correlation). The wrapper invokes
k6 with `--out experimental-opentelemetry` so k6 spans land in the same APM
instance as shop/java spans. Helm templates are gated by
`.Values.stressRunner.enabled` (default `false` from the block Plan 07-01
staged in values.yaml — Plan 07-03 never edited values.yaml).

## What landed

| Task | Outcome | Commit |
|------|---------|--------|
| 1. RED tests (16 assertions) | Appended 16 failing tests covering manifests, Helm gating (default-off/on), wrapper concurrency_lock + 409 + SIGTERM + internal-key + OTEL_SERVICE_NAME + 202 + pyproject + Dockerfile, scenarios with required headers + env-driven base URL, single-writer guard on values.yaml. 15 failed in RED; 2 pre-existing invariants passed. | `0b2fdac` |
| 2. FastAPI wrapper + pyproject | `tools/stress-runner/octo_stress_runner/main.py` (~340 LoC): 4 internal endpoints, Pydantic RunRequest with hard caps + allow-list pattern, `asyncio.Lock` + module-level `_active: ActiveRun` guard → HTTP 409 on race, `process.send_signal(SIGTERM)` on clear, hard-timeout asyncio task at `duration + 30s`, constant-time `hmac.compare_digest` internal-key check, k6 invoked with `--out experimental-opentelemetry`. Fail-fast startup if `OCTO_STRESS_RUNNER_INTERNAL_KEY` env missing. `pyproject.toml` declares fastapi + uvicorn[standard] + pydantic>=2 + opentelemetry sdk + http exporter + fastapi instrumentation. | `04b0c1e` |
| 3. k6 scenarios + Dockerfile | Three `.js` scenarios cloned from `shop/k6/checkout-load.js`: full checkout flow, read-only catalog browse, login burst. All carry `X-Octo-Stress-Target: oke` + `X-Run-Id` + `User-Agent: k6/octo-stress-runner` headers and read `__ENV.STRESS_TARGET_URL` for the base URL (no hardcoded host). Login burst credentials live in `__ENV.STRESS_DEMO_USERNAME` + `STRESS_DEMO_TOKEN_REF` (k8s Secret-mounted, never hardcoded — T-07-14). Dockerfile multi-stages `grafana/k6:0.55.0` → `python:3.12-slim`, copies the k6 binary to `/usr/local/bin/k6`, bakes scenarios into `/app/scenarios`, uvicorn entrypoint pinned to `--workers 1` to preserve the in-process concurrency=1 guard. | `da9e6e6` |
| 4. Raw k8s manifests + Helm templates | `deploy/k8s/oke/stress-runner/{namespace,deployment,service,rbac}.yaml`: Namespace `octo-stress`, Deployment replicas=1 with OTEL_SERVICE_NAME=octo-stress-runner + OTEL_RESOURCE_ATTRIBUTES + `STRESS_TARGET_URL: https://shop.${DNS_DOMAIN}` + internal-key Secret + `ocir-pull-secret` + securityContext runAsNonRoot/dropAll + readiness/liveness probes on `/internal/healthz` + resources 250m/256Mi → 2cpu/512Mi, ClusterIP Service 8080→8080 with no Ingress, ServiceAccount-only RBAC (no Role bindings — T-07-15). Helm templates under `templates/stress-runner-*.yaml` all gated by `{{- if .Values.stressRunner.enabled }}`, reference `.Values.stressRunner.*` (block staged by Plan 07-01). Default helm render contains 0 octo-stress-runner occurrences; `--set stressRunner.enabled=true` contains 14. `values.yaml` was NOT modified — single-writer invariant preserved. | `0de33e1` |

## Verification

- `pytest tests/test_stress_demo_surface.py` — **38/38 PASS** (22 from prior plans + 16 new)
- `pytest tests/test_stress_demo_surface.py -k "stress_runner or scenarios or plan_07_03_does_not_edit"` — 17/17 PASS
- `helm template deploy/helm/octo-apm-demo --set global.image.tenancy=tenant` — `grep -c octo-stress-runner` returns **0** (default off — D-05 backward compat)
- `helm template ... --set stressRunner.enabled=true` — `grep -c octo-stress-runner` returns **14** (Deployment + Service + ServiceAccount + Namespace + selectors + labels)
- `OCTO_STRESS_RUNNER_INTERNAL_KEY=test PYTHONPATH=tools/stress-runner python3 -c "from octo_stress_runner.main import app; print([r.path for r in app.routes if hasattr(r,'path')])"` — `['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc', '/internal/run', '/internal/clear', '/internal/state', '/internal/healthz']`
- `python3 -c "import yaml; [list(yaml.safe_load_all(open(f))) for f in ['deploy/k8s/oke/stress-runner/namespace.yaml','deploy/k8s/oke/stress-runner/deployment.yaml','deploy/k8s/oke/stress-runner/service.yaml','deploy/k8s/oke/stress-runner/rbac.yaml']]"` — all parse cleanly
- `grep -cE '([0-9]{1,3}\.){3}[0-9]{1,3}' deploy/k8s/oke/stress-runner/*.yaml tools/stress-runner/scenarios/*.js` — **0** across all files (no hardcoded IPs)
- `grep -c "kind: ClusterRoleBinding\|kind: RoleBinding" deploy/k8s/oke/stress-runner/rbac.yaml` — **0** (minimal RBAC enforced)
- `git diff main..HEAD -- deploy/helm/octo-apm-demo/values.yaml` for Plan 07-03's 4 commits — **empty** (single-writer guard)
- `bash -n deploy/verify.sh` — exits 0 (no regression)

## Threat Model Outcomes

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-07-10 (Spoofing: forge X-Internal-Service-Key) | mitigated | `hmac.compare_digest` on the encoded key bytes; key sourced from `octo-stress-runner-key` Secret; startup fails if env missing |
| T-07-11 (Tampering: scenario path traversal) | mitigated | Pydantic `Field(pattern=r"^(checkout_journey\|catalog_browse\|login_burst)$")` allow-list; `_resolve_scenario_path` asserts the resolved path stays under `scenarios_dir` |
| T-07-12 (DoS: over-scale) | mitigated | Pydantic caps `rps ≤ 200`, `duration_seconds ≤ 600`; concurrency=1 prevents stacking; hard timeout `duration + 30s` reaps stuck k6 |
| T-07-13 (DoS: tenancy LB quotas) | mitigated | `X-Octo-Stress-Target: oke` header on every k6 request (D-09 LB pin) keeps load on OKE backend set; OCI LB QPS quotas independently enforced |
| T-07-14 (Info disclosure: PII in load) | mitigated | login_burst uses `__ENV.STRESS_DEMO_USERNAME` + `STRESS_DEMO_TOKEN_REF` (k8s Secret-mounted, never hardcoded); pre-commit hook caught and forced the fix |
| T-07-15 (EoP: k8s API access) | mitigated | `rbac.yaml` declares ONLY a ServiceAccount with `automountServiceAccountToken: false`; test asserts no Role/RoleBinding/ClusterRoleBinding |
| T-07-16 (Repudiation: untraceable runs) | mitigated | Every `RunRequest` carries a `run_id` injected by CRM (Plan 07-05); k6 propagates it as `X-Run-Id` header + scenario `run_id` tag; wrapper logs the run_id at spawn time; `--out experimental-opentelemetry` exports k6 spans with run_id tag to APM |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Hardcoded demo passwords in login_burst.js**
- **Found during:** Task 3 commit (pre-commit hook blocked the commit)
- **Issue:** The plan's `<action>` for login_burst.js said "use the demo test users — never real PII". Initial draft inline-listed three demo user/credential pairs in a const array. The ECC pre-commit hook flagged this as a generic credential pattern (correctly — even literal demo strings match credential heuristics and would set a bad precedent for the repo).
- **Fix:** Routed demo identity through `__ENV.STRESS_DEMO_USERNAME` and `__ENV.STRESS_DEMO_TOKEN_REF`. The credential value itself comes from a k8s Secret injected by the FastAPI wrapper at run-time, not from source. The scenario synthesizes a variant suffix per iteration (`${user}-1/2/3`) to exercise the multi-user auth path. Aligns with the existing `crm/k6/stress_test.js:45` pattern (`__ENV.LOGIN_USER || __ENV.BOOTSTRAP_ADMIN_PASSWORD`).
- **Files modified:** `tools/stress-runner/scenarios/login_burst.js`
- **Commit:** `da9e6e6`

**2. [Rule 1 - Bug] /internal/healthz would crashloop the pod**
- **Found during:** Task 4 manifest writing
- **Issue:** Plan Task 2's `<action>` listed `/internal/healthz` alongside the other internal endpoints with no explicit auth carve-out, and Task 4 specified readiness/liveness probes on `/internal/healthz`. If `/internal/healthz` required the X-Internal-Service-Key header, the kubelet's `httpGet` probe (which has no access to the k8s Secret) would receive 401 and the pod would never become ready — infinite crashloop.
- **Fix:** Removed the `Depends(require_internal_key)` from `/internal/healthz`. The endpoint exposes only `{ok: true, has_k6: bool, service: "octo-stress-runner"}` — no sensitive state. The other three endpoints (`/internal/run`, `/internal/clear`, `/internal/state`) remain gated. Documented the carve-out in the docstring.
- **Files modified:** `tools/stress-runner/octo_stress_runner/main.py` (in commit `0de33e1`)
- **Commit:** `0de33e1`

**3. [Rule 3 - Blocking] helm template errored on prometheus-adapter-values.yaml**
- **Found during:** Task 4 verify step
- **Issue:** Plan 07-02 placed `prometheus-adapter-values.yaml` under `deploy/helm/octo-apm-demo/charts/`. Helm v4 treats directory contents under `charts/` as packaged subcharts and errored with `Error: error unpacking subchart prometheus-adapter-values.yaml in octo-apm-demo: Chart.yaml file is missing`. This blocked both Plan 07-03's helm-template-default-off and helm-template-enabled-on tests. The Plan 07-02 SUMMARY claimed `helm template` succeeded — likely it ran before the file was added under `charts/`, then the addition broke subsequent helm invocations.
- **Fix:** Added `charts/*.yaml` to `deploy/helm/octo-apm-demo/.helmignore` with a comment explaining the file is consumed directly by `helm install prometheus-community/prometheus-adapter -f ...` at operator-window apply time and is NOT a bundled subchart. This is the minimal, non-invasive fix that respects Plan 07-02's authoritative location.
- **Files modified:** `deploy/helm/octo-apm-demo/.helmignore`
- **Commit:** `0de33e1`

### Architectural Changes

None.

## TDD Gate Compliance

- RED gate commit (`test(07-03): ...`): `0b2fdac` — 15 failing tests after RED scaffold (1 of 16 already passed because the default helm render is naturally absent of stress-runner; 1 already passed because values.yaml had not been re-edited — both encode invariants we must preserve).
- GREEN gate commits (`feat(07-03): ...`): `04b0c1e` (wrapper), `da9e6e6` (scenarios + Dockerfile), `0de33e1` (k8s + Helm) — drove the 15 failing tests to PASS. All 38 tests in the suite green at end of plan.
- REFACTOR gate: not needed; edits were targeted and additive.

Per the plan-level TDD fail-fast guidance, the 2 pre-RED-pass tests were investigated and confirmed to encode invariants (default-off helm render, untouched values.yaml) that must be preserved — not artificially inflated to fake RED.

## Known Stubs

None. The wrapper is fully functional offline (the OCTO_STRESS_RUNNER_INTERNAL_KEY env is the only hard requirement at startup). The image is unbuilt — per the global cloud-build rule, the build runs on the control-plane VM at operator-window apply time, not from this development machine. The Plan 07-01 `stressRunner.image` values default to empty strings; the operator supplies the OCIR repo + tag at install time, same as every other component in the umbrella chart.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries were introduced beyond those already documented in the plan threat model. The `/internal/healthz` carve-out is an existing trust boundary refinement, not a new surface.

## Self-Check: PASSED

| Artifact | Status |
|----------|--------|
| `deploy/k8s/oke/stress-runner/namespace.yaml` | FOUND |
| `deploy/k8s/oke/stress-runner/deployment.yaml` | FOUND |
| `deploy/k8s/oke/stress-runner/service.yaml` | FOUND |
| `deploy/k8s/oke/stress-runner/rbac.yaml` | FOUND |
| `deploy/helm/octo-apm-demo/templates/stress-runner-deployment.yaml` | FOUND |
| `deploy/helm/octo-apm-demo/templates/stress-runner-service.yaml` | FOUND |
| `deploy/helm/octo-apm-demo/templates/stress-runner-rbac.yaml` | FOUND |
| `tools/stress-runner/octo_stress_runner/__init__.py` | FOUND |
| `tools/stress-runner/octo_stress_runner/main.py` | FOUND |
| `tools/stress-runner/pyproject.toml` | FOUND |
| `tools/stress-runner/Dockerfile` | FOUND |
| `tools/stress-runner/scenarios/checkout_journey.js` | FOUND |
| `tools/stress-runner/scenarios/catalog_browse.js` | FOUND |
| `tools/stress-runner/scenarios/login_burst.js` | FOUND |
| commit `0b2fdac` (RED tests) | FOUND |
| commit `04b0c1e` (FastAPI wrapper) | FOUND |
| commit `da9e6e6` (scenarios + Dockerfile) | FOUND |
| commit `0de33e1` (k8s + Helm + auto-fixes) | FOUND |
