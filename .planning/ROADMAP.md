# Roadmap: OCTO APM Demo

## Overview

This roadmap treats the existing OCTO APM Demo as a live brownfield platform.
The next GSD phases focus on making the implementation and emdemo deployment a
state-of-the-art observability demo: complete evidence per user action,
consistent VM/OKE/container deployment behavior, reliable dashboards and
detection rules, admin-only GenAI operations, and docs that match reality.

## Phases

- [x] **Phase 1: Signal Contract Hardening** - Audit and normalize MELTS fields,
  spans, logs, metrics, and APM/Log Analytics pivots across all services.
- [x] **Phase 2: Payment and User Journey Insight** - Make checkout, login,
  cart, payment, CRM sync, and DB evidence complete for successful and failed
  flows.
- [x] **Phase 3: Log Analytics Detection Reliability** - Verify saved searches,
  dashboards, parsers, and detection rules against real logs and traces.
- [x] **Phase 4: Deployment Parity and Release Gates** - Align VM, OKE,
  container, Helm, and local-stack deployments with repeatable validation.
- [x] **Phase 5: Admin AI and Secure Operations** - Keep OCI Coordinator and
  GenAI capabilities admin-only, scoped, observable, and safe.
- [x] **Phase 6: Documentation and Architecture Closure** - Update runbooks,
  diagrams, troubleshooting guides, and release documentation from evidence.

## Phase Details

### Phase 1: Signal Contract Hardening

**Goal**: Every service emits a consistent observability contract that can be
joined from APM to Log Analytics, Monitoring, and ATP.
**Depends on**: Existing live VM and OKE deployment snapshot.
**Requirements**: OBS-01, OBS-02, OBS-03, OBS-05
**Success Criteria**:
1. Trace IDs, span IDs, request IDs, workflow IDs, order IDs, payment gateway
   IDs, user/session IDs, and service names are present where required.
2. APM saved queries return relevant spans for Shop, Admin, Java, payment,
   GenAI, auth, DB, and service-error flows.
3. Log Analytics parsers use existing fields wherever available.
4. Custom OCI Monitoring metrics use the shared OCTO namespace.
**Plans**: 4 plans

Plans:
**Wave 1**
- [x] 01-01: Create signal contract inventory tests and enforcement docs.

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02: Harden Shop and CRM request/log enrichment.
- [x] 01-03: Harden Java sidecar and support-service telemetry.
- [x] 01-04: Validate APM, Log Analytics, and Monitoring assets.

### Phase 2: Payment and User Journey Insight

**Goal**: A successful or failed purchase can be followed from browser action
through Shop, Java sidecar, simulated payment rails, CRM/Admin, and ATP.
**Depends on**: Phase 1
**Requirements**: JOURNEY-01, JOURNEY-02, JOURNEY-04, PAY-01, PAY-02, PAY-03,
PAY-04
**Success Criteria**:
1. Google Pay, Apple Pay, Visa, and Mastercard simulations expose complete
   token-safe workflow steps.
2. Login, add-to-cart, checkout, gateway, CRM sync, and DB spans appear in a
   single trace or documented correlated traces.
3. Checkout success and Admin order views expose usable APM and Log Analytics
   pivots.
4. Decline, timeout, and controlled error flows generate detection-ready logs.
**Plans**: 3 plans

Plans:
- [x] 02-01: Verify and patch payment rail simulation and Java spans.
- [x] 02-02: Verify and patch user, cart, login, order, and CRM sync evidence.
- [x] 02-03: Run local validation gate and defer public VM+OKE route checks to
  Phase 4 deployment validation.

### Phase 3: Log Analytics Detection Reliability

**Goal**: Troubleshooting and threat-hunting assets work from real data, not
only synthetic examples.
**Depends on**: Phase 1 and Phase 2
**Requirements**: OBS-04, SEC-01
**Success Criteria**:
1. Saved searches execute without query-format errors.
2. Dashboards render real app, OKE, payment, security, and database samples.
3. Scheduled detection rules use fields emitted by current parsers.
4. Connector, ONM, and collector health failures have fast troubleshooting
   searches.
**Plans**: 2 plans

Plans:
- [x] 03-01: Harden source validation for detection rules, saved searches,
  dashboards, and offline dry-run payload generation.
- [x] 03-02: Run local Log Analytics source and docs validation gates; defer
  live real-log execution to operator validation after import.

### Phase 4: Deployment Parity and Release Gates

**Goal**: VM, OKE, container, Helm, and local-stack paths deploy the same app
contract and can be validated before promotion.
**Depends on**: Phase 1 through Phase 3
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04
**Success Criteria**:
1. Deployment templates expose the same required observability and secret
   variables.
2. VM and OKE can run behind the same LB without user-facing drift.
3. Release validation covers tests, build, docs, smoke, E2E, APM, and Log
   Analytics checks.
4. Scripts avoid destructive actions and stay scoped to OCTO resources.
**Plans**: 3 plans

Plans:
- [x] 04-01: Compare deployment manifests, scripts, Helm values, and VM envs.
- [x] 04-02: Harden release validation and rollback guidance.
- [x] 04-03: Validate current emdemo VM and OKE runtime after rollout.

### Phase 5: Admin AI and Secure Operations

**Goal**: Admin-only GenAI and operational features are scoped, observable, and
safe for demos.
**Depends on**: Phase 1 and Phase 4
**Requirements**: JOURNEY-03, SEC-02, SEC-03, SEC-04, AI-01, AI-02, AI-03
**Success Criteria**:
1. OCI Coordinator remains inaccessible from the customer shop surface.
2. Admin assistant answers stay scoped to octo-apm-demo resources.
3. LLMetry, Langfuse, APM, and Log Analytics correlate GenAI activity.
4. Customer pages clearly present a fake demo shop without backend internals.
**Plans**: 3 plans

Plans:
- [x] 05-01: Review Admin AI configuration, auth, scope, and telemetry.
- [x] 05-02: Review customer/admin UX boundaries and security logging.
- [x] 05-03: Validate assistant, DB cleanup, users, and order workflows.

### Phase 6: Documentation and Architecture Closure

**Goal**: Documentation, diagrams, and runbooks match the implementation and
current deployment.
**Depends on**: Phase 1 through Phase 5
**Requirements**: DOC-01, DOC-02, DOC-03
**Success Criteria**:
1. Architecture diagrams are layered, editable, sanitized, and current.
2. VM, OKE, container, and local-stack docs share the same validation story.
3. Troubleshooting docs include APM drilldowns, Log Analytics pivots,
   connector checks, ONM checks, and dashboard checks.
4. `mkdocs build --strict` passes after documentation updates.
**Plans**: 3 plans

Plans:
- [x] 06-01: Update architecture and deployment docs from verified evidence.
- [x] 06-02: Update troubleshooting and runbook content.
- [x] 06-03: Run docs and release-readiness validation.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Signal Contract Hardening | 4/4 | Complete | 2026-05-14 |
| 2. Payment and User Journey Insight | 3/3 | Complete | 2026-05-14 |
| 3. Log Analytics Detection Reliability | 2/2 | Complete | 2026-05-14 |
| 4. Deployment Parity and Release Gates | 3/3 | Complete | 2026-05-14 |
| 5. Admin AI and Secure Operations | 3/3 | Complete | 2026-05-14 |
| 6. Documentation and Architecture Closure | 3/3 | Complete | 2026-05-14 |

### Phase 7: OKE Autoscaling and Stress Demo

**Goal:** Demonstrate OCI-native cluster elasticity end-to-end. Wire up
Horizontal Pod Autoscaler (HPA) and Cluster Autoscaler so the OKE
deployment scales pods + nodes up under load and back down when traffic
returns to normal. Add a controlled stress-test entry point on the
admin surface (admin.${DNS_DOMAIN}) that ramps load against shop + CRM,
then showcase the scaling story through three OCI Observability
surfaces in parallel:

  - **OCI APM** — service throughput, latency percentiles, slow-span
    distribution as pods scale; cross-service trace propagation while
    new pods come online.
  - **OCI Monitoring** — custom metric `octo_apm_demo` namespace
    (pod count, request rate, CPU/memory saturation, autoscaler
    decisions); alarms that fire on the scaling thresholds.
  - **OCI Logging Analytics — OKE Monitoring** — node + pod + container
    log streams, autoscaler events, HPA decisions, kubelet pressure
    events, with saved searches that surface the scaling timeline.

The phase ships:
  1. HPA manifests (or Helm values) for shop, crm, java-apm with
     sensible CPU + memory + RPS targets.
  2. OKE Cluster Autoscaler configured against the worker node pool.
  3. An admin-only `/admin/stress-test` page that triggers
     parameterized load (RPS, duration, target service) via a
     synchronized load-generator pod, with safe-stop and audit logging.
  4. APM saved queries + Monitoring alarms + Log Analytics dashboards
     that capture the scale-up / scale-down narrative.
  5. Workshop Lab 11 walking through the full demo: trigger load,
     watch HPA scale shop pods, observe Cluster Autoscaler add a node,
     drill into APM + Logan + Monitoring evidence, then watch
     downscale.

**Requirements**: SCALE-01..04 (HPA, Cluster Autoscaler, stress-test
admin UI, observability dashboards). To be enumerated during
`/gsd-discuss-phase 7`.

**Depends on:** Phase 5 (admin surface boundary), Phase 4 (OKE Helm
deployment parity).

**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 7 to break down)
