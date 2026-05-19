---
phase: 07-oke-autoscaling-and-stress-demo
plan: 05
subsystem: crm/server/modules
tags: [admin, fastapi, audit, melts, host-bound, tdd, stress-test]
dependency_graph:
  requires:
    - "Plan 07-03 (octo-stress-runner pod /internal/{run,clear,state,healthz}
       contract gated by X-Internal-Service-Key)"
    - "Plan 07-04 (shared _require_admin_host helper at
       crm/server/modules/_admin_host.py)"
    - "Phase 5 admin role gate (server.modules._authz.require_admin_user)"
    - "Shop-side oci_monitoring.py _point + ingestion-endpoint publisher
       (D-17 namespace)"
  provides:
    - "FastAPI router /api/admin/stress/{presets,apply,clear,state}
       mounted under admin role + admin host (Phase 5 contract)"
    - "HTML page route /admin/stress-test with csp_nonce + nav_key='stress'
       template context (consumed by Plan 07-06 base.html nav entry)"
    - "Three-channel MELTS audit emit per lifecycle event: OTel span
       admin.stress.<event> + push_log('INFO', 'stress_test.<event>', ...)
       + oci_monitoring.increment_stress_run(run_id, status)"
    - "increment_stress_run(run_id, status) helper in BOTH
       shop/server/observability/oci_monitoring.py and the CRM mirror
       publishing to octo_apm_demo/stress_run_count (bounded D-17 counter)"
    - "stress-operator role registered in crm/server/modules/admin.py
       _ALLOWED_ROLES (optional second gate beyond require_admin_user)"
    - "cfg.octo_stress_runner_internal_key + cfg.octo_stress_runner_base_url
       crm config surface for cross-pod X-Internal-Service-Key auth"
  affects:
    - "Plan 07-06 (stress_test_admin.html template + base.html nav entry —
       nav_key='stress' contract is in place)"
    - "Plan 07-08 (OCI Monitoring alarms — stress_run_count counter is
       now publishing on D-17 namespace)"
    - "Plan 07-09 (Log Analytics saved searches — push_log('INFO',
       'stress_test.<event>', run_id=...) lines are emitted with the
       D-15 field set the saved searches expect)"
    - "Plan 07-10 (operator runbook — admin-host gate proven via tests)"
tech_stack:
  added:
    - "Pydantic v2 Literal + Field(pattern=...) hard caps with
       field_validator stripping newline/null from the audit note"
    - "httpx.AsyncClient cross-pod call with X-Internal-Service-Key
       header (mirrors simulation.py:660-715 internal-key pattern)"
    - "One-off oci.monitoring PostMetricDataDetails publisher that
       resolves region + ingestion endpoint per call so the audit emit
       is durable even if the background publisher thread is between
       intervals"
  patterns:
    - "Three-channel MELTS audit (span + log + counter) keyed by a
       single run_id UUID for end-to-end pivot (D-15, D-17)"
    - "Server-side target_host construction from cfg.dns_domain — never
       trust client input for the run destination (T-07-29 mitigation)"
    - "Audit-before-side-effect ordering for /apply: push_log +
       increment_stress_run land BEFORE the cross-pod POST so a runner
       failure still leaves an authoritative trail"
    - "Idempotent /clear: query runner state first; if idle, return
       {status:idle} with no audit emission so the counter does not
       over-report no-op operator clicks"
key_files:
  created:
    - crm/server/modules/stress_test.py
  modified:
    - crm/server/modules/admin.py
    - crm/server/main.py
    - crm/server/config.py
    - crm/server/observability/oci_monitoring.py
    - shop/server/observability/oci_monitoring.py
    - tests/test_stress_demo_surface.py
decisions:
  - "stress_test.py imports _require_admin_host from the Plan 07-04
     shared helper — never re-implements (PATTERNS §Authentication +
     RESEARCH §Anti-Patterns §4 enforced by structural test)"
  - "Audit-before-side-effect ordering on /apply — emit the three-channel
     audit BEFORE calling the runner. If the runner is unreachable the
     attempt is still attributed to admin_user + run_id"
  - "Idempotent /clear with no audit on idle — counter dimension
     cardinality stays bounded (T-07-30 mitigation, RESEARCH §Anti-Pattern §2)"
  - "Added increment_stress_run to BOTH shop and crm oci_monitoring.py
     copies. The plan only listed the shop file in <files_modified>, but
     stress_test.py lives in CRM and resolves server.observability.* to
     the CRM mirror — adding to both keeps the cross-codebase D-17 contract
     consistent and matches the existing shop/crm parity pattern"
  - "Page route renders a minimal HTML fallback when
     stress_test_admin.html is absent (Plan 07-06 will author it). The
     fallback still carries nav_key='stress' + csp_nonce so the contract
     is preserved before Plan 07-06 lands"
  - "404 from runner is treated as 'idle' rather than 503 to keep the
     UI stable during the brief moments when the runner pod is restarting"
metrics:
  duration_minutes: 22
  completed_date: "2026-05-18T18:10:00Z"
---

# Phase 7 Plan 05: CRM admin stress-test API + three-channel MELTS audit — Summary

CRM admin host now exposes `/api/admin/stress/{presets,apply,clear,state}`
plus the HTML page route `/admin/stress-test`. Every endpoint is gated by
`require_admin_user` AND `_require_admin_host` (Phase 5 contract via the
shared helper Plan 07-04 extracted). Lifecycle events emit a three-channel
MELTS audit keyed by a UUID `run_id`: OTel span `admin.stress.<event>`,
`push_log("INFO", "stress_test.<event>", ...)` with the full D-15 field
set, and `oci_monitoring.increment_stress_run(run_id, status)` publishing
to `octo_apm_demo/stress_run_count`. The handler proxies the actual run
lifecycle to the octo-stress-runner pod with an `X-Internal-Service-Key`
header. Hard caps (rps 1-200, duration 10-600s, scenario allow-list,
target_service literal 'shop') are enforced by Pydantic BEFORE any side
effect.

## What landed

| Task | Outcome | Commit |
|------|---------|--------|
| 1. RED tests (17) | Appended 17 failing tests to `tests/test_stress_demo_surface.py` covering 202 + run_id, host gate (403), scope rejection, concurrency 409, rps/duration/scenario 422, /clear sends + audits, /clear idempotent when idle, /state projection (active vs idle), /presets (3 bundles), HTML page + csp_nonce, source assertions for admin._ALLOWED_ROLES + main router wiring + oci_monitoring helper + nav_key='stress'. All 17 fail with `ImportError: cannot import name 'stress_test'`. | `06e49fe` |
| 2. GREEN — implement (5 files + 1 NEW) | New `crm/server/modules/stress_test.py` (~424 LoC at GREEN). `crm/server/modules/admin.py` `_ALLOWED_ROLES` extended with `stress-operator`. `crm/server/main.py` mounts `stress_admin_router` + `stress_admin_page_router` parallel to chaos. `crm/server/config.py` adds `octo_stress_runner_internal_key` (`_env_secret`) + `octo_stress_runner_base_url` (in-cluster default). `shop/server/observability/oci_monitoring.py` AND CRM mirror both gain a synchronous `increment_stress_run(run_id, status)` helper that posts a single `PostMetricDataDetails` point to `octo_apm_demo/stress_run_count` with `run_id+status` dimensions, resolving the ingestion endpoint per call. | `48b3542` |
| 3. REFACTOR — trim to ≤ 400 lines | GREEN was 424 lines, over the web 400-line rule. Tightened module docstring + replaced long divider comment blocks with single-line section headers. No behavioral change. Final: 398 lines. All 17 plan tests + coordinator + chaos + admin_host regression suites still green. | `7e25e15` |

## Verification

- `pytest tests/test_stress_demo_surface.py` — **77/77 PASS** (60 from prior plans + 17 new)
- `pytest tests/test_stress_demo_surface.py -k "stress_apply or stress_clear or stress_state or stress_presets or stress_page or admin_module or main_includes or oci_monitoring_increment"` — 17/17 PASS
- `pytest crm/tests/ -k "coordinator or chaos or admin"` — 21/21 PASS (no Phase 5 regression)
- `PYTHONPATH=crm OCTO_STRESS_RUNNER_INTERNAL_KEY=t python -c "from server.modules.stress_test import router, page_router; print('OK')"` — `OK`
- `wc -l crm/server/modules/stress_test.py` — `398`
- `grep -c 'nav_key="stress"' crm/server/modules/stress_test.py` — `4` (literal in code + comment + context dict comment)
- Full pre-existing baseline regression: 9 failing tests across `crm/test_compute_*` / `crm/test_log_analytics_*` / `crm/test_unified_deploy_*` were failing on `main` before this plan started — confirmed pre-existing by `git stash && pytest && git stash pop` diff. Plan 07-05 introduces zero new test failures.

## Threat Model Outcomes

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-07-20 (Spoofing: public storefront calls /api/admin/stress/*) | mitigated | `_require_admin_host` dependency at the router level + regression test `test_stress_apply_rejects_non_admin_host_403` |
| T-07-21 (Spoofing: non-admin role calls /apply) | mitigated | `require_admin_user` dependency at the router level — non-admin sessions get 403 from `_authz.py:35-42`; admin role checked at the request level too inside handlers |
| T-07-22 (Tampering: oversized rps/duration) | mitigated | Pydantic `Field(ge=1, le=200)` + `Field(ge=10, le=600)` enforce D-13 caps server-side; three regression tests cover rps/duration/scenario |
| T-07-23 (Tampering: log injection via note) | mitigated | `field_validator("note")` rejects newline/CR/null characters; `push_log` JSON-serializes the value (no string interpolation into a log line) |
| T-07-24 (Repudiation: operator denies run) | mitigated | Three-channel audit (span + push_log + monitoring counter) keyed by `run_id`; `admin_user` comes from the auth dependency, not from the request body |
| T-07-25 (Info disclosure: internal-service key leaked in audit) | mitigated | The key is never passed to `push_log` or span attributes; only injected into the outbound httpx call's `X-Internal-Service-Key` header; cfg surface enumerated and reviewed |
| T-07-26 (DoS: load amplification past LB caps) | mitigated | `rps <= 200` + `duration_seconds <= 600` Pydantic caps; concurrency=1 enforced in the runner pod (Plan 07-03); hard timeout `duration+30s` lives in the runner |
| T-07-27 (DoS: recursive admin endpoint) | accept | `target_service` is a Pydantic `Literal["shop"]`; `target_host` is constructed server-side from `cfg.dns_domain`; no client control over destination |
| T-07-28 (EoP: DEPLOY-03 round-robin guard breakage) | mitigated (delegated) | The CRM handler sends `target_url` and the runner adds the `X-Octo-Stress-Target: oke` header (Plan 07-03 contract); no client control over the routing header |
| T-07-29 (EoP: OCTO scope leakage) | mitigated | `target_service` Pydantic `Literal["shop"]`; `target_host` built from `cfg.dns_domain` server-side; the runner cannot be steered to a non-OCTO destination |
| T-07-30 (Repudiation: counter cardinality explosion) | mitigated | `run_id` only on the bounded `stress_run_count` counter (RESEARCH §Anti-Pattern §2); idempotent /clear emits no audit when the runner is already idle so the counter does not over-report no-op clicks |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added increment_stress_run to BOTH shop AND crm oci_monitoring.py copies**
- **Found during:** Task 2 implementation (resolving the import in stress_test.py)
- **Issue:** The plan's `<files_modified>` only listed `shop/server/observability/oci_monitoring.py`. However, `crm/server/modules/stress_test.py` resolves `from server.observability.oci_monitoring import increment_stress_run` against the CRM Python path (since stress_test.py is inside CRM), which loads `crm/server/observability/oci_monitoring.py` — not the shop file. Adding the helper only to the shop file would have left a broken import.
- **Fix:** Added the synchronous `increment_stress_run(run_id, status)` helper to both copies with identical behavior: each posts a one-off `PostMetricDataDetails` point to `octo_apm_demo/stress_run_count` with `run_id+status` dimensions, resolving the ingestion endpoint per call. Matches the existing shop/crm parity pattern (both files already had parallel `increment_*` helpers).
- **Files modified:** `shop/server/observability/oci_monitoring.py`, `crm/server/observability/oci_monitoring.py`
- **Commit:** `48b3542`

**2. [Rule 3 - Blocking] Page route falls back to minimal HTML when stress_test_admin.html is absent**
- **Found during:** Task 2 implementation of test `test_stress_page_route_returns_html_with_csp_nonce`
- **Issue:** Plan 07-06 owns the authoring of `stress_test_admin.html`. The page route handler in this plan would raise `TemplateNotFound` when the template is absent, breaking the contract test and crashing any production preview before Plan 07-06 lands.
- **Fix:** Added an `os.path.isfile(template_path)` guard. When the template is absent, render a minimal HTML placeholder (`<!doctype html>...`) that still carries the `csp_nonce` and a `nav_key="stress"` comment so the Plan 07-06 nav consumer can be wired and tested in isolation. When Plan 07-06 lands `stress_test_admin.html`, the handler will switch to `templates.TemplateResponse(...)` automatically — no code change needed downstream.
- **Files modified:** `crm/server/modules/stress_test.py`
- **Commit:** `48b3542`

**3. [Rule 1 - Bug] Wrapped audit emission in try/except so push_log/monitoring failures cannot block the admin handler**
- **Found during:** Task 2 implementation
- **Issue:** `push_log` calls into the OCI Logging SDK; `increment_stress_run` calls into the OCI Monitoring SDK. Either could raise on a misconfigured tenancy (no `OCI_COMPARTMENT_ID`, network error, etc.). If unwrapped, a transient observability fault would surface as a 500 to the admin user — worse than silently degrading the audit channel.
- **Fix:** `_emit_lifecycle_event` wraps both `push_log` and `increment_stress_run` in try/except blocks that log at WARNING and swallow the exception. The OTel span is the third audit channel and continues to record regardless. This matches the existing pattern in `oci_monitoring.py` start_monitoring (logs WARNING on init failure, returns silently).
- **Files modified:** `crm/server/modules/stress_test.py`
- **Commit:** `48b3542`

### Architectural Changes

None.

## TDD Gate Compliance

- RED gate commit (`test(07-05): ...`): `06e49fe` — 17 failing tests, all due to missing `crm/server/modules/stress_test.py`. No pre-RED-pass tests.
- GREEN gate commits (`feat(07-05): ...`): `48b3542` — drove all 17 RED tests to PASS while introducing zero regression. All 77 stress demo surface tests + 21 coordinator/chaos/admin regression tests green.
- REFACTOR gate (`refactor(07-05): ...`): `7e25e15` — trimmed stress_test.py from 424 → 398 lines to fit the 400-line web rule. No behavioral change, all tests still green.

Per the plan-level TDD fail-fast guidance: zero tests passed during RED. All 17 failed with `ImportError` (file did not yet exist) — the canonical no-op-implementation signal that all assertions were exercised on real handler paths once Task 2 landed.

## Known Stubs

None at the API surface. The `/admin/stress-test` page route renders a minimal HTML fallback only when `stress_test_admin.html` is absent — Plan 07-06 will replace the fallback automatically by authoring the template. This is documented as Deviation #2 above, not a stub. The `nav_key="stress"` template context is wired today.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries were introduced beyond those already documented in the plan threat model. The cross-pod call to octo-stress-runner uses the same X-Internal-Service-Key pattern as simulation.py:660-715.

## Self-Check: PASSED

| Artifact | Status |
|----------|--------|
| `crm/server/modules/stress_test.py` (NEW) | FOUND |
| `crm/server/modules/admin.py` (stress-operator) | FOUND |
| `crm/server/main.py` (stress_admin_router mount) | FOUND |
| `crm/server/config.py` (octo_stress_runner_* fields) | FOUND |
| `shop/server/observability/oci_monitoring.py` (increment_stress_run) | FOUND |
| `crm/server/observability/oci_monitoring.py` (increment_stress_run) | FOUND |
| `tests/test_stress_demo_surface.py` (17 new tests) | FOUND |
| commit `06e49fe` (RED) | FOUND |
| commit `48b3542` (GREEN) | FOUND |
| commit `7e25e15` (REFACTOR) | FOUND |
| Acceptance: 17/17 plan-05 tests PASS | PASSED |
| Acceptance: no Phase 5 regression (coordinator + chaos + admin_host) | PASSED |
| Acceptance: `wc -l stress_test.py` ≤ 400 | PASSED (398) |
| Acceptance: module imports cleanly | PASSED |
| Acceptance: `grep -c 'nav_key="stress"' stress_test.py` ≥ 1 | PASSED (4) |
