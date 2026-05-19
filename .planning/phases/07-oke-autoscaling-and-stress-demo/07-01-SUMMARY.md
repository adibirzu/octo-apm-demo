---
phase: 07-oke-autoscaling-and-stress-demo
plan: 01
subsystem: deploy/k8s/oke + deploy/helm + observability pins
tags: [oke, autoscaling, hpa, helm, otel, llmetry, d-05, d-21]
dependency_graph:
  requires:
    - deploy/k8s/oke/shop/deployment.yaml (existing HPA block)
    - deploy/k8s/oke/apm-java-demo/deployment.yaml (existing Deployment)
    - deploy/helm/octo-apm-demo/templates/shop-hpa.yaml (existing template)
    - deploy/helm/octo-apm-demo/values.yaml (existing shop/javaGateway blocks)
    - shop/server/observability/logging_sdk.py (OBS-01..05 contract)
  provides:
    - shop HPA scaling 2→10 with CPU+memory+RPS metrics + behavior block
    - java APM HPA scaling 2→6 (was missing pre-Phase 7)
    - helm chart shop.autoscaling.rps gated default-off (D-05)
    - helm chart javaGateway.autoscaling block + java-gateway-hpa.yaml template
    - helm chart stressRunner top-level values block (default off, Plan 07-03 ref point)
    - OTel Java agent pinned to 2.27.0 (D-21)
    - tools/llmetry/pin.txt tracking artifact (D-21)
  affects:
    - Plan 07-02 (prometheus-adapter / RPS metric resolution) — depends on the
      External metric shape committed here
    - Plan 07-03 (stress-runner templates) — depends on the stressRunner
      values block staged here (no values.yaml re-edit needed)
tech_stack:
  added:
    - HPA v2 External metric with selector.matchLabels
    - HPA v2 behavior block (scaleUp/scaleDown stabilization windows)
    - Helm gated conditional metric blocks (`{{- if .Values.*.rps.enabled }}`)
  patterns:
    - manifest-string regex assertions over yaml-text (per tests/test_unified_deploy_surface.py)
    - sole-owner write of values.yaml (D-05 spirit) to keep cross-plan churn off the
      same file in Wave 1
key_files:
  created:
    - deploy/helm/octo-apm-demo/templates/java-gateway-hpa.yaml
    - tools/llmetry/pin.txt
    - tests/test_stress_demo_surface.py
  modified:
    - deploy/k8s/oke/shop/deployment.yaml (HPA block)
    - deploy/k8s/oke/apm-java-demo/deployment.yaml (appended HPA doc)
    - deploy/helm/octo-apm-demo/templates/shop-hpa.yaml (gated RPS + behavior)
    - deploy/helm/octo-apm-demo/values.yaml (shop+javaGateway autoscaling, stressRunner)
    - services/apm-java-demo/pom.xml (opentelemetry.javaagent.version property)
decisions:
  - "D-03 max replicas: shop 10, java 6 — matched plan target"
  - "D-05 RPS metric gated default-off in Helm; raw OKE manifest carries the External
     block unconditionally (resolves to no-op until Plan 07-02 ships the adapter)"
  - "D-21 Python OTel pins ALREADY at current stable (opentelemetry-sdk==1.41.1,
     instrumentation==0.62b1 per PyPI). No-op bump documented as Rule 1 finding."
  - "Plan referenced crm/server/requirements.txt — actual path in repo is
     crm/requirements.txt. Test reads the real path (Rule 3 — blocking issue
     auto-corrected)."
  - "tools/llmetry/pin.txt did not exist; created with llmetry==0.5.0 contract pin"
metrics:
  duration_minutes: 7
  completed_date: "2026-05-18T17:20:41Z"
---

# Phase 7 Plan 01: HPA expansion + D-21 pin bumps — Summary

Shop HPA scales 2→10 replicas with CPU 60 + memory 70 + an External
`shop_request_rate` metric (30/pod) and a flap-guard behavior block; the
Java APM gateway gains its own HPA (2→6) with the same shape; the Helm
chart gates the RPS metric default-OFF (D-05) and stages a `stressRunner:`
top-level values block so Plan 07-03 templates can render without
re-editing values.yaml; the OTel Java agent is pinned to 2.27.0 and a new
`tools/llmetry/pin.txt` tracks the in-repo LLMetry contract version.

## What landed

| Task | Outcome | Commit |
|------|---------|--------|
| 1. RED tests (14 assertions) | Created `tests/test_stress_demo_surface.py` covering HPA edits, helm gating, stressRunner values, OTel/LLMetry pins, OBS regression guard. 11 failed in RED; 3 passed pre-existing (Rule 1 finding). | `2b8a6d7` |
| 2. Raw OKE HPA manifest edits | Shop HPA: maxReplicas 4→10, CPU 70→60, memory 75→70, External `shop_request_rate` 30/pod, behavior block scaleUp=30s/scaleDown=300s. Java HPA: new doc at end of `apm-java-demo/deployment.yaml`, min=2/max=6, CPU 65/memory 75, External `java_request_rate` 20/pod, same behavior block. | `ca1e07d` |
| 3. Helm chart edits | `values.yaml` shop.autoscaling bumped; `rps:` subsection (default false); `behavior:` block; `javaGateway.autoscaling` new block (max=6); `stressRunner:` top-level block (default false, sole-owner write). `templates/shop-hpa.yaml` gated External metric + behavior toYaml/nindent. `templates/java-gateway-hpa.yaml` new file. | `b615ac9` |
| 4. D-21 pin bumps | `services/apm-java-demo/pom.xml` adds `opentelemetry.javaagent.version=2.27.0`. `tools/llmetry/pin.txt` created with `llmetry==0.5.0`. Python OTel pins already current stable — no-op. OBS contract preserved (shop/tests/test_llmetry.py 2/2 pass). | `379e2cf` |

## Verification

- `pytest tests/test_stress_demo_surface.py` — 14/14 PASS (GREEN)
- `helm template deploy/helm/octo-apm-demo --set global.image.tenancy=tenant` — 3 HPAs rendered (shop, crm, java-gateway)
- `helm template ... --set shop.autoscaling.rps.enabled=false` — 0 `type: External` blocks (D-05 backward compat proven)
- `helm template ... --set shop.autoscaling.rps.enabled=true` — 1 `type: External` block
- `helm template ...` (default) — 0 occurrences of `octo-stress-runner` (stressRunner default-off, no templates yet)
- `shop/tests/test_llmetry.py` — 2/2 PASS (OBS-01..05 field-shape contract intact)
- YAML manifests parse cleanly (5 docs each in shop + apm-java-demo)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wrong crm requirements path in plan**
- **Found during:** Task 1 test scaffold
- **Issue:** Plan `<files_modified>` lists `crm/server/requirements.txt`; the actual file in this repo is `crm/requirements.txt`. The non-existent path would have produced a `FileNotFoundError` in `test_otel_sdk_pinned_in_crm_requirements`.
- **Fix:** Test reads the actual path (`crm/requirements.txt`); behavior remains identical (assert `opentelemetry-sdk==` present and version ≥ 1.27).
- **Files modified:** `tests/test_stress_demo_surface.py`
- **Commit:** `2b8a6d7`

**2. [Rule 1 - Bug] Plan test floor too low to enforce a bump**
- **Found during:** Task 1 RED check
- **Issue:** Plan asserted `opentelemetry-sdk >= 1.27`. The repo's existing pin is already `1.41.1` (current stable per PyPI on 2026-05-18). The floor of 1.27 cannot detect drift below the current state — but the floor IS what D-21 requires (current stable, with the floor as a tripwire). Documented as a no-op rather than artificially inflating the floor to invent RED state.
- **Resolution:** Kept floor at ≥ 1.27 per D-21 behavior block. The Python pins are already current; this is the intended outcome of D-21 ("bumped to current stable"). Java agent + LLMetry pin file were the real work this task required.
- **Files modified:** none beyond Task 1 test file
- **Commit:** documented in Task 4 commit `379e2cf` message

**3. [Rule 1 - Bug] javaGateway test too loose**
- **Found during:** Task 1 RED check
- **Issue:** Initial `test_helm_java_gateway_autoscaling_block_present` checked for `javaGateway:` and `maxReplicas: 6` independently anywhere in values.yaml — but the CRM block also contains `maxReplicas: 6`, so the test would PASS pre-edit (false negative for RED).
- **Fix:** Tightened to use a regex that captures the `javaGateway:` block body and asserts `autoscaling:` + `maxReplicas: 6` inside that block specifically.
- **Files modified:** `tests/test_stress_demo_surface.py`
- **Commit:** `2b8a6d7` (committed with the rest of the RED scaffold)

**4. [Rule 1 - Bug] OBS regression test had brittle import path**
- **Found during:** Task 1 RED check
- **Issue:** Initial OBS regression test used `importlib.import_module("shop.server.observability.logging_sdk")`, but the project has no top-level `shop` package (no `__init__.py`); only `shop/tests/conftest.py` puts `shop/` on sys.path. From the project-root pytest run, `shop` is not importable.
- **Fix:** Rewrote the test to use `read_text` substring assertions on `shop/server/observability/logging_sdk.py` and `otel_setup.py` — verifies `def push_log`, `trace_id`, `span_id`, `service.name`, and `opentelemetry` symbols are still present without requiring import-time resolution.
- **Files modified:** `tests/test_stress_demo_surface.py`
- **Commit:** `2b8a6d7`

**5. [Rule 1 - Bug] Plan referenced `tools/llmetry/pin.txt` which did not exist**
- **Found during:** Task 4
- **Issue:** Plan `<read_first>` says "if file does not exist, create per behavior". Confirmed absent; created with `llmetry==0.5.0` contract pin.
- **Files modified:** `tools/llmetry/pin.txt` (new)
- **Commit:** `379e2cf`

### Architectural Changes

None.

## TDD Gate Compliance

- RED gate commit (`test(07-01): ...`): `2b8a6d7` — 11 failing tests after RED scaffold.
- GREEN gate commits (`feat(07-01): ...` / `chore(07-01): ...`): `ca1e07d`, `b615ac9`, `379e2cf` — drove each failing test to PASS.
- REFACTOR gate: not needed; edits were targeted.

Three of the 14 tests passed in the RED state because they reflected pre-existing repo state (OTel SDK already at current stable; javaGateway top-level block existed but lacked an autoscaling subblock — fixed by the test-tightening described in Deviation #3). This is per the TDD plan-level fail-fast guidance ("if a test passes unexpectedly during RED, investigate"); the investigation produced a deviation note rather than a halt, because the underlying behavior was already at the target state for an orthogonal reason (PyPI advancing the OTel package independent of repo work).

## Known Stubs

None. The External RPS metric is gated `default: false` in Helm (an intentional D-05 backward-compat design) and resolves to a no-op against the live cluster until Plan 07-02 ships prometheus-adapter — this is by design, not a stub.

## Self-Check: PASSED

All 9 created/modified files exist at their expected paths; all 4 task
commits resolve via `git log --all`. No missing artifacts.

| Artifact | Status |
|----------|--------|
| `tests/test_stress_demo_surface.py` | FOUND |
| `deploy/k8s/oke/shop/deployment.yaml` | FOUND |
| `deploy/k8s/oke/apm-java-demo/deployment.yaml` | FOUND |
| `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml` | FOUND |
| `deploy/helm/octo-apm-demo/templates/java-gateway-hpa.yaml` | FOUND |
| `deploy/helm/octo-apm-demo/values.yaml` | FOUND |
| `services/apm-java-demo/pom.xml` | FOUND |
| `tools/llmetry/pin.txt` | FOUND |
| `.planning/phases/07-oke-autoscaling-and-stress-demo/07-01-SUMMARY.md` | FOUND |
| commit `2b8a6d7` (RED tests) | FOUND |
| commit `ca1e07d` (raw HPA edits) | FOUND |
| commit `b615ac9` (Helm chart) | FOUND |
| commit `379e2cf` (D-21 pins) | FOUND |
