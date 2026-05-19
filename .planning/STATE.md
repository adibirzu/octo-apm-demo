---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: scaling-demo
status: verifying
stopped_at: "Phase 7 Plan 04 completed: _admin_host extracted, regression-green"
last_updated: "2026-05-18T19:19:11.519Z"
last_activity: 2026-05-18
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 28
  completed_plans: 28
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-14)

**Core value:** Every demo user action must produce inspectable, correlated OCI
observability evidence across browser, application, payment gateway, Java
sidecar, database, logs, traces, metrics, security, and GenAI where relevant.
**Current focus:** Phase 7 — OKE Autoscaling and Stress Demo

## Current Position

Phase: 7 (OKE Autoscaling and Stress Demo) — EXECUTING
Plan: 10 of 10
Status: Phase complete — ready for verification
Last activity: 2026-05-18

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 18
- Average duration: 6 min
- Total execution time: 76 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 4 | 22 min | 6 min |
| 2 | 3 | 18 min | 6 min |
| 3 | 2 | 8 min | 4 min |
| 4 | 3 | 18 min | 6 min |
| 5 | 3 | 18 min | 6 min |
| 6 | 3 | 18 min | 6 min |

**Recent Trend:**

- Last 5 plans: 6 min, 6 min, 6 min, 6 min, 6 min
- Trend: Stable targeted-plan execution

| Phase 07 P01 | 7 | 4 tasks | 9 files |
| Phase Phase 07 P02 P02 | 4 min | 3 tasks tasks | 3 files files |
| Phase 07 P03 | 11 | 4 tasks | 15 files |
| Phase 07 P04 | 8 min | 2 tasks | 5 files |
| Phase 7 P07 | 25min | - tasks | - files |
| Phase 07 P08 | 5m | 2 tasks | 5 files |
| Phase 07-oke-autoscaling-and-stress-demo P09 | 12min | 2 tasks | 6 files |
| Phase 07 P05 | 22 | 3 tasks | 6 files |
| Phase 7 P6 | 35 | 3 tasks | 3 files |
| Phase 07 P10 | ~14min | 3 tasks | 6 files |

## Accumulated Context

### Roadmap Evolution

- 2026-05-18: Phase 7 added — OKE Autoscaling and Stress Demo
  (HPA + Cluster Autoscaler, admin stress-test UI, APM + Monitoring +
  Log Analytics OKE Monitoring storyline). Reopens scope into a new
  milestone v1.1.

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Recent decisions
affecting current work:

- Use GSD in text mode with inherited Codex model behavior.
- Keep GSD worktree isolation disabled for this runtime.
- Treat VM and OKE as active peer runtimes behind the same public LB.
- Keep OCI Coordinator admin-only and scoped to octo-apm-demo.
- Maintain `.planning/codebase/` as the local brownfield map for future phases.
- Keep the signal contract inventory source-level and dependency-light so it can
  run without live OCI credentials.

- FastAPI `push_log` now pulls request IDs from app request context and avoids
  card-masking trace/span join keys.

- Java stdout events now emit dotted payment/service aliases; support services
  now include `service.instance.id` resource identity.

- APM, Log Analytics, dashboard, and Monitoring source assets now have local
  contract tests and documented validation commands.

- Payment gateway response payloads now expose token-safe component labels for
  wallet gateways, card networks, Java processor, and antifraud verification.

- Java payment sidecar calls propagate request/workflow headers in addition to
  W3C/B3 trace context.

- Login now emits success/failure spans, metrics, structured logs, and audit
  rows; authenticated order audit rows use the authenticated user id.

- Log Analytics saved-search/dashboard/detection-rule apply dry-run is now
  offline-safe and has local tests for rule metric/dimension consistency,
  dashboard payload compilation, and unsupported parameter rejection.

- Helm now deploys the same OKE observability/payment contract as the raw OKE
  manifests, including the Java payment gateway, pod identity,
  `OTEL_RESOURCE_ATTRIBUTES`, Select AI, and Langfuse hooks.

- `deploy/verify.sh` now initializes Terraform offline before validation,
  avoids Kubernetes API calls for Helm client dry-run, and treats provider
  registry/CDN outages as warnings rather than source failures.

- OCI Coordinator now exposes explicit admin-only OCTO scope guardrails and
  dynamic admin host metadata in responses, spans, and logs.

- Workflow Gateway admin labs now reject public storefront host calls from
  browser/admin-token callers while preserving internal service access.

- Customer login/shop copy avoids backend/internal wording and public docs
  avoid live tenancy labels.

- Shop pytest no longer deletes `server.*` modules during collection; the full
  Shop suite and `deploy/verify.sh` pass without warnings.

- Public DrawIO sources are layered by architecture domain and the diagrams
  README documents layer/flow movement conventions.

- Architecture docs now keep Coordinator, Query Lab, Select AI, and GenAI
  LLMetry on the Admin/CRM path.

- Deploy readiness records the zero-warning local verifier, and Log Analytics
  docs include connector, ONM, trace/log, payment, and GenAI troubleshooting
  pivots.

- [Phase ?]: Phase 7 Plan 01: HPA shop 2→10 + java 2→6 with gated RPS metric (D-05 default-off); OTel Java agent 2.27.0; Python OTel pins already current stable
- [Phase ?]: Phase 7 Plan 02: Cluster Autoscaler add-on (min=2 max=4, dry-run default) + prometheus-adapter External Metrics for shop_request_rate + java_request_rate; envsubst placeholder for OKE_NODE_POOL_OCID keeps live OCIDs out of repo
- [Phase ?]: Phase 7 Plan 03: octo-stress-runner Deployment + FastAPI control plane (4 endpoints, internal-key gated); concurrency=1 → HTTP 409; SIGTERM on clear; hard timeout duration+30s; 3 k6 scenarios with X-Octo-Stress-Target + X-Run-Id; multi-stage Dockerfile grafana/k6→python:3.12; Helm gated default-off; values.yaml untouched (07-01 single-writer).
- [Phase 7]: Plan 04: Extracted `_require_admin_host` + `_request_host` + `_configured_admin_hosts` from coordinator.py into shared `crm/server/modules/_admin_host.py` (verbatim, refactor-scope). Coordinator imports — drift impossible by construction. Structural anti-drift test guards against future copy-paste regression. Plan 07-05 stress-test surface now imports from same source. Phase 5 admin-host contract bit-identical (regression suite 7/7 green; full crm suite 97/97 green).
- [Phase ?]: Plan 07-07: mirrored tools/la-saved-searches/ structure for APM saved-query operator tooling; APPLY=false default + confirm-on-APPLY pattern; D-20 drilldown links embedded as external_drilldowns JSON metadata per query
- [Phase ?]: Plan 07-08: alarm thresholds hardcoded in JSON; cross-file invariant test guards drift vs values.yaml
- [Phase ?]: Plan 07-08: alarm upsert via list-by-display-name pattern (mirrors install-oci-kubernetes-monitoring.sh)
- [Phase ?]: Phase 7 plan 09: D-19 LA half — 4 saved searches + dashboard JSON, auto-discovered by existing apply.sh (zero script edits)
- [Phase ?]: Plan 07-05: increment_stress_run added to both shop AND crm oci_monitoring.py - CRM stress_test.py resolves to the CRM mirror, plan only listed shop
- [Phase ?]: Plan 07-05: Audit-before-side-effect ordering on /apply - three-channel MELTS audit lands BEFORE cross-pod POST so runner failures still attribute attempts
- [Phase ?]: Plan 07-06: stress_test_admin.html reuses style.css glass-dark tokens — no new CSS. Inline nonce-scoped style/script with prefers-reduced-motion guard and 2s/10s polling cadence flip.
- [Phase ?]: Plan 07-10: Lab 11 is the last lab in the workshop arc — no Next-arrow at bottom; closes Phase 7 narrative (D-22)
- [Phase ?]: Plan 07-10: LB-routing-rule expression uses case-insensitive header match (i 'X-Octo-Stress-Target') eq (i 'oke') per OCI LB grammar
- [Phase ?]: Plan 07-10: Two .planning/* cross-links dropped from runbook to satisfy mkdocs --strict; semantic refs preserved in prose

### Pending Todos

- None for the local source milestone.

### Blockers/Concerns

- Shared emdemo resources are live; deployment and OCI automation must avoid
  destructive or non-OCTO actions without explicit approval.

- The worktree has pre-existing changes outside `.planning/`; future GSD work
  must preserve unrelated edits.

- Secrets, OCIDs, IPs, wallet paths, and operator notes must stay out of public
  docs and GSD artifacts.

- Public VM+OKE load-balanced E2E was not run during Phase 2; keep it in Phase
  4 deployment parity validation with an approved live rollout window.

- `mvn test` could not be run locally because Maven is not installed.

- Live Log Analytics query execution against emdemo was not run during Phase 3;
  keep it as an operator validation after import/apply with approved OCI
  credentials.

- Live public VM+OKE round-robin validation was not run during Phase 4; keep it
  as an operator validation during an approved rollout window.

- Live OCI GenAI, Select AI, Langfuse, APM, and Log Analytics confirmation was
  not run during Phase 5; keep it as an operator validation during an approved
  live deployment window.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Future scope | Real payment provider integration | Deferred | GSD onboarding |
| Future scope | Full production multi-tenancy outside OCTO demo | Deferred | GSD onboarding |

## Session Continuity

Last session: 2026-05-18T19:19:04.500Z
Stopped at: Phase 7 Plan 04 completed: _admin_host extracted, regression-green
Resume file: None
