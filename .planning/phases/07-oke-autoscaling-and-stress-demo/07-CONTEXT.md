# Phase 7: OKE Autoscaling and Stress Demo - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning
**Source:** /gsd-discuss-phase 7 — interactive discuss mode; prior CONTEXT files for Phases 4 & 5; codebase scout of deploy/k8s/oke, deploy/helm, tools/traffic-generator, crm/server.

<domain>
## Phase Boundary

Phase 7 ships an end-to-end OKE elasticity demo against the existing
octo-apm-demo deployment. It must work for live demo + workshop delivery
without breaking VM/OKE deployment parity, admin-AI boundaries, or the
observability contracts hardened in Phases 1–6.

Concretely the phase delivers:

1. Expanded HPA for `octo-drone-shop` and `octo-apm-java-demo` driven by
   CPU + memory + a custom RPS metric published to the `octo_apm_demo`
   OCI Monitoring namespace.
2. OKE managed Cluster Autoscaler add-on configured for the existing
   worker node pool (min=2, max=4) via a non-destructive, operator-gated
   configuration script + docs.
3. A long-lived in-cluster k6 wrapper Deployment that exposes an HTTP
   control plane and runs short, high-RPS stress scenarios inline (no
   cold start; fast demo turnaround).
4. An admin-only `/admin/stress-test` page on `admin.${DNS_DOMAIN}` that
   triggers parameterized stress runs (RPS + duration + scenario preset)
   with concurrency=1, hard caps, idempotent stop, and full MELTS-shaped
   audit logging.
5. APM saved queries (4), OCI Monitoring custom metrics + 2 alarms, and
   a Log Analytics "OKE Autoscaling Timeline" dashboard with 4 saved
   searches that together tell the scale-up / scale-down narrative.
6. Workshop Lab 11 walking through the full demo, cross-linked to
   Labs 1, 5, and 9.

The phase covers SCALE-01..04 (to be enumerated in REQUIREMENTS.md
during `/gsd-plan-phase 7`).

**Out of scope:** Live OCI apply of the Cluster Autoscaler add-on, real
LB routing changes, anything outside the OCTO demo project, and
oci-coordinator-oke (external future project — leave APM hooks only).

</domain>

<decisions>
## Implementation Decisions

### HPA + Cluster Autoscaler Scope

- **D-01: HPA expanded for `octo-drone-shop` and `octo-apm-java-demo`
  only.** CRM HPA stays at its current `min=2/max=4, CPU 70%/mem 75%`
  configuration to keep blast radius narrow.
- **D-02: HPA metrics = CPU + memory + RPS.** The RPS metric is
  published to the `octo_apm_demo` OCI Monitoring namespace and exposed
  to HPA via a Kubernetes Custom/External Metrics adapter
  (prometheus-adapter or kube-metrics-adapter). The adapter is a new
  in-cluster Deployment — it must be offline-validatable via
  `deploy/verify.sh`.
- **D-03: HPA scale-out target = shop max 10 replicas, java-apm max 6
  replicas.** Exact CPU/memory/RPS thresholds finalized during plan
  phase; opening targets are CPU 60%, memory 70%, RPS 30/pod (shop) and
  CPU 65%, RPS 20/pod (java-apm).
- **D-04: Cluster Autoscaler = OKE managed add-on.** Configured against
  the existing emdemo worker node pool with **min=2, max=4 nodes**. A
  new `deploy/oke/configure-cluster-autoscaler.sh` script wraps the
  `oci ce cluster install-addon` / `oci ce cluster update-addon` call.
  The script must be idempotent, non-destructive, scoped to the OCTO
  cluster only, and require explicit operator confirmation before
  applying.
- **D-05: All scaling changes are additive.** Existing manifests +
  Helm templates stay backward-compatible: bumping `maxReplicas` in
  HPA is safe; adding the RPS metric is gated behind a Helm value
  `autoscaling.rps.enabled` (default `false`) so the legacy code path
  keeps working.

### Load Generator Approach

- **D-06: Engine = k6 (grafana/k6 image), pulled via OCIR mirror.**
  Native OTLP output enabled so the load itself produces APM spans
  correlated with shop/java spans during the run.
- **D-07: Lifecycle = long-lived k6 wrapper Deployment, NOT ephemeral
  Jobs.** A small FastAPI wrapper Deployment (`octo-stress-runner`)
  runs always, with the `k6` binary in the same pod. Admin POST →
  wrapper shells `k6 run <scenario>` inline. Image already pulled, no
  cold start. Concurrency=1 enforced inside the wrapper. Each run is
  tagged with a UUID `run_id` propagated as an OTel attribute and
  Monitoring metric dimension.
- **D-08: Target URL = public LB hostname (`shop.${DNS_DOMAIN}`).**
  Traffic flows through the production LB → ingress → OKE backend so
  RUM + edge logs + APM all see the run.
- **D-09: VM/OKE round-robin guard (DEPLOY-03).** k6 sends a routing
  hint header `X-Octo-Stress-Target: oke`. The LB/ingress is
  configured to pin requests carrying that header to the OKE backend
  set only, leaving the VM backend untouched. Header-based routing
  config is documented in a new operator runbook
  (`site/operations/stress-demo-lb-routing.md`); the LB rule itself is
  applied during the same operator window as the Cluster Autoscaler
  add-on enablement.
- **D-10: Existing `tools/traffic-generator` is NOT replaced.** It
  keeps providing behavioral baseline traffic (~2 RPS). k6 is the
  separate stress engine — both can run in parallel during a demo.

### Admin Stress-Test UI + Safety

- **D-11: New page `/admin/stress-test` on `admin.${DNS_DOMAIN}`.**
  Template `crm/server/templates/stress_test_admin.html` mirrors the
  existing `chaos_admin.html` pattern (audit banner, preset selector,
  TTL/duration field, target selector, current-state pane, clear
  button).
- **D-12: New module `crm/server/modules/stress_test.py`** exposes
  `/api/admin/stress/{presets,apply,clear,state}`. Auth = existing
  admin role gate + host-bound enforcement (Phase 5 contract). An
  optional `stress-operator` role is added to `_ALLOWED_ROLES` in
  `crm/server/modules/admin.py` for finer scoping (alongside the
  existing `chaos-operator`).
- **D-13: Parameters and hard caps (server-side enforced):**
  - `rps` ∈ [1, 200], default 25
  - `duration_seconds` ∈ [10, 600], default 60
  - `scenario` ∈ {`checkout_journey`, `catalog_browse`, `login_burst`}
  - `target_service` ∈ {`shop`} (allow-list, hard-coded for v1.1)
- **D-14: Guardrails:** concurrency=1 (second POST returns HTTP 409
  with active `run_id`); stop button → `/api/admin/stress/clear` →
  SIGTERM to k6 (graceful drain); auto-expire at declared duration;
  server-side hard timeout = `duration + 30s` as a safety net.
- **D-15: Audit fields (full MELTS-shaped event):** `trace_id`,
  `span_id`, `run_id` (UUID), `admin_user`, `admin_role`,
  `timestamp_start`, `timestamp_end`, `rps_requested`,
  `duration_requested`, `scenario`, `target_service`, `target_host`,
  `source_pod`, `status` ∈ {started, running, stopped, expired,
  error}, `reason`. Emitted simultaneously to structured logs (Log
  Analytics parser contract), an OCI Monitoring counter
  `octo_apm_demo/stress_run_count`, and an OTel span that correlates
  with shop + java spans during the run window.

### Observability Narrative Depth

- **D-16: APM saved queries (4 ship in this phase):**
  1. Pod-count-over-time (shop, java-apm) grouped by `k8s.pod.name` +
     `service.name`, bucketed 1min — direct visual of HPA adding pods.
  2. Latency percentiles during scale event (p50/p95/p99 for
     `/api/shop/checkout` and java payment gateway, bucketed 30s).
  3. Trace propagation to new pods — filter traces where
     `k8s.pod.name` first appears inside the active stress window.
  4. Error/saturation spikes + slow-span distribution — top-N pods by
     `5xx` / `span.status=ERROR` + slow-span histogram (stress vs
     baseline).
- **D-17: OCI Monitoring custom metrics (new, under `octo_apm_demo`
  namespace):** `shop_pod_count` (gauge), `shop_request_rate` (gauge),
  `shop_cpu_saturation_pct` (gauge), `hpa_decision_event` (counter,
  dim=`action: scale_up|scale_down`), `cluster_autoscaler_node_event`
  (counter, dim=`action: add|remove`). Dimensions on all:
  `pod_name`, `namespace`, `run_id`.
- **D-18: 2 OCI Monitoring alarms:**
  1. **High CPU saturation** — fires when `shop_cpu_saturation_pct` >
     80 for 2 min. Expected to fire during every stress run; doubles
     as alarm-path validation.
  2. **HPA at max replicas** — fires when pod count = `maxReplicas`
     for > 5 min. Capacity-needed signal that survives downscale.
- **D-19: Log Analytics — new dashboard "OKE Autoscaling Timeline"** in
  the `octo-apm-demo` workspace with 4 saved searches:
  1. HPA scale events (Source=`Kubernetes Logs`, Subsystem=
     `hpa-controller`).
  2. Cluster Autoscaler events (managed add-on logs / cluster-
     autoscaler events).
  3. Kubelet pressure (`NodeNotReady`, `ImagePullBackOff`,
     `OOMKilled`).
  4. Stress run audit log (filter where `run_id` is present).
  All time-aligned for the Lab 11 walkthrough.
- **D-20: APM + dashboard drilldown links to external observability
  surfaces.** Saved query metadata and dashboard tiles include
  outbound links to `lm.octodemo.cloud`, `phoenix.octodemo.cloud`,
  `openlit.octodemo.cloud`, and `grafana.octodemo.cloud`. These hosts
  are operator-owned external surfaces; Phase 7 only adds the
  contextual links, not the surfaces themselves.
- **D-21: OTel + LLMetry pinned to latest stable releases.** Bump
  Python OTel SDK/instrumentation, Java OTel agent, and the in-repo
  LLMetry instrumentation to the latest stable versions during this
  phase (verify against the existing `OBS-01..05` contract — no
  field-shape regressions). Required by user direction so that future
  `oci-coordinator-oke` integration lands cleanly.

### Workshop Lab 11

- **D-22: Lab 11 = single full walkthrough, cross-linked to Labs 1, 5,
  9.** Steps: (1) verify baseline (2 shop pods, 2 nodes); (2) trigger
  Medium preset (50 RPS / 3 min) from `/admin/stress-test`; (3) watch
  HPA add pods in OCI Console + APM pod-count query; (4) watch
  Cluster Autoscaler add a node + High-CPU-saturation alarm fire;
  (5) drill into APM latency p95 + trace-to-new-pod; (6) drill into
  Log Analytics scaling timeline; (7) cool-down 5 min, watch
  scale-down to baseline. Cross-links: Lab 1 (first trace), Lab 5
  (metric + alarm), Lab 9 (chaos drill).

### Claude's Discretion

- Exact HPA `stabilizationWindowSeconds` and `behavior` policies (the
  research/plan phase picks values that produce a visible-but-stable
  scale narrative).
- File layout under `deploy/k8s/oke/` vs `deploy/helm/octo-apm-demo/`
  for the new k6 wrapper Deployment and stress-test wiring — the
  planner can split Helm vs raw YAML to match the existing pattern.
- The FastAPI wrapper's internal API shape beyond the
  `/api/admin/stress/{presets,apply,clear,state}` contract.
- Test layout — extending `tests/test_unified_deploy_surface.py` vs
  adding `tests/test_stress_demo_surface.py`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning + prior phase context
- `.planning/PROJECT.md` — core value, constraints, OCI Coordinator
  admin-only rule.
- `.planning/REQUIREMENTS.md` — observability + deployment contracts;
  Phase 7 requirement IDs `SCALE-01..04` to be added during plan phase.
- `.planning/ROADMAP.md` §Phase 7 — phase goal, deliverables list.
- `.planning/STATE.md` — milestone v1.1 / scaling-demo.
- `.planning/phases/04-deployment-parity-and-release-gates/04-CONTEXT.md`
  — **DEPLOY-03** round-robin VM/OKE LB constraint (drives D-09).
- `.planning/phases/05-admin-ai-and-secure-operations/05-CONTEXT.md`
  — admin-only + host-bound + audit pattern (drives D-11..D-15).
- `.planning/phases/06-documentation-and-architecture-closure/06-CONTEXT.md`
  — diagrams + docs sanitization rules.

### Existing autoscaling surfaces (to be extended, not replaced)
- `deploy/k8s/oke/shop/deployment.yaml` — current shop HPA
  (`min=2/max=4`, CPU 70 / mem 75).
- `deploy/k8s/oke/crm/deployment.yaml` — current crm HPA
  (unchanged in this phase).
- `deploy/k8s/oke/apm-java-demo/` — java sidecar deployment manifests
  (HPA to be added by D-01).
- `deploy/helm/octo-apm-demo/templates/shop-hpa.yaml` and
  `crm-hpa.yaml` — Helm versions; must stay parity-aligned (D-05).
- `deploy/helm/octo-apm-demo/values.yaml` — new
  `autoscaling.rps.enabled` flag lives here (D-05).
- `deploy/oke/deploy-oke.sh` — existing OKE deploy orchestrator.
- `deploy/oke/create-emdemo-small-cluster.sh` — node-pool creation;
  reference for the new `configure-cluster-autoscaler.sh` script
  (D-04).

### Admin surface pattern (to copy, not break)
- `crm/server/templates/chaos_admin.html` — template pattern for
  D-11.
- `crm/server/modules/simulation.py` — service-side scenario
  pattern.
- `crm/server/modules/admin.py` — `_ALLOWED_ROLES` extension point
  for the optional `stress-operator` role (D-12).
- `crm/server/modules/coordinator.py` — host-bound + audit logging
  primitives that the new stress module must reuse.

### Observability contract (must not regress)
- `shop/server/observability/oci_monitoring.py` — `octo_apm_demo`
  namespace publisher; D-17 metrics land here.
- `shop/server/observability/llmetry.py` — LLMetry contract;
  D-21 pin happens against this surface.
- `tools/traffic-generator/README.md` — existing behavioral driver;
  stays in place per D-10.

### Workshop labs (cross-link targets)
- `site/workshop/lab-01-first-trace.md`
- `site/workshop/lab-05-metric-and-alarm.md`
- `site/workshop/lab-09-chaos-drill.md`

### External operator-owned drilldown hosts (link out, do not bundle)
- `lm.octodemo.cloud` — Langfuse / LLMetry external surface.
- `phoenix.octodemo.cloud` — Arize Phoenix.
- `openlit.octodemo.cloud` — OpenLIT.
- `grafana.octodemo.cloud` — Grafana.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **HPA + Helm chart** already in place for shop + crm; D-01 / D-03
  extend the YAML and Helm value surface rather than introducing new
  abstractions.
- **`chaos_admin.html` + `simulation.py`** give a working template for
  an audited, admin-only, host-bound, TTL-driven operator surface;
  D-11 / D-12 mirror this pattern.
- **`octo_apm_demo` Monitoring namespace publisher** in
  `shop/server/observability/oci_monitoring.py` already abstracts
  metric publish; D-17 adds new gauges/counters through the same
  helper.
- **`tools/traffic-generator/k8s/deployment.yaml`** is the closest
  analog for the new k6 wrapper Deployment manifest.
- **`deploy/verify.sh`** is the canonical offline validation gate;
  Phase 7 must extend it (or its callees) so the new stress runner +
  CA configuration script + RPS adapter are caught when missing or
  drifted.

### Established Patterns
- **Admin-only, host-bound, audited:** every operator-facing endpoint
  proves it's on `admin.${DNS_DOMAIN}`, checks the admin role, and
  emits a structured audit event (Phase 5).
- **VM/OKE parity (DEPLOY-03):** anything that touches the public LB
  must respect round-robin between VM and OKE backends — hence the
  `X-Octo-Stress-Target: oke` header pinning (D-09).
- **`octo_apm_demo` is the only Monitoring namespace** — new metrics
  reuse it (D-17).
- **Helm templates mirror raw YAML** — every manifest change has a
  Helm counterpart (Phase 4 contract).

### Integration Points
- New k6 wrapper Deployment lives in the **shop namespace** so it can
  reach the in-cluster ingress and inherits the same imagePullSecret
  + RBAC posture as the application.
- Stress test API mounts inside the **CRM/Admin FastAPI app** under
  `/api/admin/stress/*` (same router family as
  `/api/admin/coordinator/*` and `/api/admin/chaos/*`).
- Custom-metrics adapter (HPA RPS source) deploys to `kube-system` or
  a dedicated `octo-autoscaling` namespace (planner's choice).
- Cluster Autoscaler add-on enablement script lives next to existing
  OKE bootstrap scripts under `deploy/oke/`.
- New audit log records flow through the existing Log Analytics
  parser contract — no new parser fields needed (OBS-02).

</code_context>

<specifics>
## Specific Ideas

- Use the **latest stable OTel SDKs/instrumentation** for Python and
  Java, and the **latest LLMetry** release (D-21).
- The four external observability surfaces (`lm.octodemo.cloud`,
  `phoenix.octodemo.cloud`, `openlit.octodemo.cloud`,
  `grafana.octodemo.cloud`) should appear as **drilldown links from
  APM saved query metadata + Log Analytics dashboard tiles + Lab 11
  prose** — not as bundled services.
- Workshop Lab 11 narrative arc: baseline → trigger → HPA fires →
  Cluster Autoscaler fires → alarms fire → APM/Logan drilldown →
  cool-down → back to baseline. Two-screen walkthrough (admin UI +
  OCI Console / APM / Logan) — written so a workshop attendee can
  reproduce solo in under 15 minutes.
- Audit events must carry `run_id` end-to-end so a workshop attendee
  can pivot APM → Logan → Monitoring around a single run.

</specifics>

<deferred>
## Deferred Ideas

- **`oci-coordinator-oke` as an external project** — out of scope for
  Phase 7. Leave APM resource attributes / drilldown link slots
  available so a future phase can wire it in without changing the
  contract.
- **Lab 12 (split Cluster Autoscaler into its own lab)** — single
  Lab 11 first; consider splitting after workshop feedback.
- **Power-user "upload custom k6 script"** mode — too much script-
  execution surface for v1.1; deferred behind a future ADR.
- **Custom-metrics adapter (RPS) live install** — Helm manifest will
  ship in this phase, but the actual `kubectl apply` against emdemo
  is gated behind the same operator window as the Cluster Autoscaler
  add-on apply.
- **LB header-based routing rule live apply** — manifest + runbook
  ship here; the LB listener config change is an operator action.
- **CRM and Workflow Gateway HPAs** — left untouched in v1.1 per
  D-01. Revisit once Phase 7 is shipped and measured.
- **RUM-side stress correlation tiles** — Lab 11 mentions RUM in
  prose only; deeper RUM dashboard hook deferred.

</deferred>

---

*Phase: 07-oke-autoscaling-and-stress-demo*
*Context gathered: 2026-05-18*
