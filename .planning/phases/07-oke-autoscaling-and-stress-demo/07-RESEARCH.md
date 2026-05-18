# Phase 7: OKE Autoscaling and Stress Demo - Research

**Researched:** 2026-05-18
**Domain:** Kubernetes elasticity (HPA + OKE Cluster Autoscaler add-on), in-cluster k6 load runner, admin-only operator surface, OCI APM/Monitoring/Log Analytics narrative.
**Confidence:** HIGH for OKE CA add-on contract, HPA v2 behavior, OTel/Java/Python versions, OCI LB routing-policy syntax. MEDIUM for prometheus-adapter vs kube-metrics-adapter selection. LOW only where explicitly flagged.

## Summary

Phase 7 sits on top of an already-mature codebase: HPA + Helm + PDB are in place for shop and crm; `chaos_admin` is a working pattern for an audited, host-bound, role-gated admin surface; `oci_monitoring.py` already publishes to the `octo_apm_demo` namespace with `post_metric_data` and the correct ingestion endpoint (KB-456); the Log Analytics parser already accepts `run_id` as a first-class field. There is also a small surprise — the repo already ships **k6 stress scripts under `shop/k6/` and `crm/k6/`** (`checkout-load.js`, `cross_service_stress.js`, `stress_test.js`). Phase 7 should treat these as reusable scenario libraries the new wrapper Deployment mounts/embeds rather than re-authoring k6 scenarios from scratch.

The phase has unusually thick locked decisions (D-01..D-22). The remaining technical work is therefore narrow: (1) pick prometheus-adapter as the External Metrics source for the RPS HPA metric (it is the dominant, battle-tested choice); (2) write the OKE CA add-on JSON config + idempotent install/update script using the documented `oci ce cluster install-addon` / `update-addon` contract; (3) build the FastAPI k6-wrapper Deployment with strict concurrency=1, SIGTERM-on-clear, OTLP enabled, `run_id` propagation; (4) clone the `chaos_admin` admin/template pattern verbatim into a `stress_test` module + template; (5) extend `oci_monitoring.py` with five new gauges/counter shapes and ship two MQL alarms; (6) wire the LB header-rule via documented OCI routing-policy syntax (operator-applied, not auto-applied); (7) bump OTel pins to current latest stable.

**Primary recommendation:** Use prometheus-adapter for the External Metrics path; install OKE Cluster Autoscaler as a managed add-on via a new `deploy/oke/configure-cluster-autoscaler.sh` that wraps `list-addons` → `install-addon` (or `update-addon`) with explicit operator confirmation; ship the k6 wrapper as `octo-stress-runner` Deployment under a new `octo-stress` namespace (or `octo-traffic` per the existing pattern). Keep all live OCI mutations behind the same operator-window gate that already covers Phase 4 LB changes.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HPA scale decision (CPU/mem/RPS) | OKE control plane (kube-controller-manager) | prometheus-adapter (External Metrics) | HPA controller owns reconciliation; the adapter only provides the metric source. |
| Custom RPS metric publish | Shop pod (`shop/server/observability/oci_monitoring.py`) | OCI Monitoring `octo_apm_demo` namespace | Application owns business metric emission; Monitoring is the sink. prometheus-adapter scrapes the in-cluster `/metrics` endpoint (Prometheus exposition), NOT OCI Monitoring directly — the OCI Monitoring publish is for the dashboard story, the in-cluster scrape is for the HPA decision. |
| Cluster Autoscaler decision | OKE managed add-on (kube-system) | OKE API (`oci ce cluster install-addon`) | Add-on runs in-cluster; install/update is an OCI control-plane API call. |
| k6 load execution | `octo-stress-runner` Deployment (shop or stress namespace) | OCI LB → ingress → shop service | Wrapper pod owns lifecycle; LB enforces header-based pinning to OKE backend set. |
| Admin stress-test UI | CRM/Admin FastAPI (`crm/server`) | `chaos_admin` template family | Same router family as `/api/admin/coordinator/*` and `/api/admin/chaos/*`; reuses `_authz.require_admin_user` + `coordinator._require_admin_host`. |
| Audit logging | CRM Admin module → `push_log` → Log Analytics parser | OCI Monitoring counter `stress_run_count` + OTel span | Three-channel emit (Log/Metric/Trace) for MELTS shape; `run_id` is already in the Log Analytics field whitelist. |
| OCI LB header pinning | OCI Flexible LB routing-policy (operator-applied) | Documented runbook only | LB config lives outside the cluster — manifests + runbook ship in repo, `oci lb routing-policy update` is operator action. |
| Workshop walkthrough | `site/workshop/lab-11-*.md` | Cross-links to Labs 1, 5, 9 | Pure docs; mkdocs nav update only. |

## User Constraints (from CONTEXT.md)

### Locked Decisions

Quoting verbatim from CONTEXT.md `<decisions>`:

**HPA + Cluster Autoscaler Scope (D-01..D-05):**
- **D-01:** HPA expanded for `octo-drone-shop` and `octo-apm-java-demo` only. CRM HPA stays at its current `min=2/max=4, CPU 70%/mem 75%` configuration.
- **D-02:** HPA metrics = CPU + memory + RPS. The RPS metric is published to the `octo_apm_demo` OCI Monitoring namespace and exposed to HPA via a Kubernetes Custom/External Metrics adapter (prometheus-adapter or kube-metrics-adapter). The adapter is a new in-cluster Deployment — it must be offline-validatable via `deploy/verify.sh`.
- **D-03:** HPA scale-out target = shop max 10 replicas, java-apm max 6 replicas. Opening targets are CPU 60%, memory 70%, RPS 30/pod (shop) and CPU 65%, RPS 20/pod (java-apm).
- **D-04:** Cluster Autoscaler = OKE managed add-on. Configured against the existing emdemo worker node pool with **min=2, max=4 nodes**. A new `deploy/oke/configure-cluster-autoscaler.sh` script wraps the `oci ce cluster install-addon` / `oci ce cluster update-addon` call. Must be idempotent, non-destructive, scoped to OCTO cluster only, and require explicit operator confirmation before applying.
- **D-05:** All scaling changes are additive. Existing manifests + Helm templates stay backward-compatible: bumping `maxReplicas` in HPA is safe; adding the RPS metric is gated behind a Helm value `autoscaling.rps.enabled` (default `false`).

**Load Generator Approach (D-06..D-10):**
- **D-06:** Engine = k6 (grafana/k6 image), pulled via OCIR mirror. Native OTLP output enabled.
- **D-07:** Lifecycle = long-lived k6 wrapper Deployment (`octo-stress-runner`), NOT ephemeral Jobs. FastAPI wrapper + k6 binary in the same pod. Concurrency=1. Each run tagged with UUID `run_id` propagated as OTel attribute and Monitoring metric dimension.
- **D-08:** Target URL = public LB hostname (`shop.${DNS_DOMAIN}`).
- **D-09:** k6 sends routing-hint header `X-Octo-Stress-Target: oke`. LB/ingress pins requests carrying that header to OKE backend set only. Header-based routing config documented in `site/operations/stress-demo-lb-routing.md`; LB rule applied in same operator window as CA enablement.
- **D-10:** Existing `tools/traffic-generator` is NOT replaced.

**Admin Stress-Test UI + Safety (D-11..D-15):**
- **D-11:** New page `/admin/stress-test` on `admin.${DNS_DOMAIN}`. Template `crm/server/templates/stress_test_admin.html` mirrors `chaos_admin.html`.
- **D-12:** New module `crm/server/modules/stress_test.py` exposes `/api/admin/stress/{presets,apply,clear,state}`. Auth = existing admin role gate + host-bound enforcement. Optional `stress-operator` role added to `_ALLOWED_ROLES` in `crm/server/modules/admin.py`.
- **D-13:** Hard caps: `rps` ∈ [1, 200] default 25; `duration_seconds` ∈ [10, 600] default 60; `scenario` ∈ {`checkout_journey`, `catalog_browse`, `login_burst`}; `target_service` ∈ {`shop`}.
- **D-14:** Concurrency=1 (second POST → HTTP 409 with active `run_id`); stop → SIGTERM to k6; auto-expire at declared duration; server-side hard timeout = `duration + 30s`.
- **D-15:** Audit fields (MELTS-shaped): `trace_id, span_id, run_id, admin_user, admin_role, timestamp_start, timestamp_end, rps_requested, duration_requested, scenario, target_service, target_host, source_pod, status, reason`. Emitted simultaneously to structured logs, OCI Monitoring counter `octo_apm_demo/stress_run_count`, and an OTel span.

**Observability Narrative Depth (D-16..D-21):**
- **D-16:** APM saved queries: (1) pod-count-over-time grouped by `k8s.pod.name`+`service.name`, 1m buckets; (2) latency percentiles p50/p95/p99 for `/api/shop/checkout` and java payment gateway, 30s buckets; (3) trace propagation to new pods; (4) error/saturation + slow-span top-N.
- **D-17:** OCI Monitoring custom metrics (`octo_apm_demo`): `shop_pod_count` gauge, `shop_request_rate` gauge, `shop_cpu_saturation_pct` gauge, `hpa_decision_event` counter (dim=action: scale_up|scale_down), `cluster_autoscaler_node_event` counter (dim=action: add|remove). All dimensions: `pod_name`, `namespace`, `run_id`.
- **D-18:** 2 alarms — High CPU saturation (`shop_cpu_saturation_pct > 80 for 2 min`), HPA at max replicas (`pod count = maxReplicas for > 5 min`).
- **D-19:** Log Analytics dashboard "OKE Autoscaling Timeline" with 4 saved searches: HPA scale events; CA events; kubelet pressure (NodeNotReady, ImagePullBackOff, OOMKilled); stress run audit log (filter where `run_id` is present).
- **D-20:** APM + dashboard drilldown links to `lm.octodemo.cloud`, `phoenix.octodemo.cloud`, `openlit.octodemo.cloud`, `grafana.octodemo.cloud`.
- **D-21:** OTel + LLMetry pinned to latest stable releases; verify against `OBS-01..05` contract.

**Workshop Lab 11 (D-22):** Single full walkthrough cross-linked to Labs 1, 5, 9.

### Claude's Discretion

- Exact HPA `stabilizationWindowSeconds` and `behavior` policies.
- File layout under `deploy/k8s/oke/` vs `deploy/helm/octo-apm-demo/`.
- FastAPI wrapper's internal API shape beyond the documented contract.
- Test layout — extend `tests/test_unified_deploy_surface.py` vs add `tests/test_stress_demo_surface.py`.

### Deferred Ideas (OUT OF SCOPE)

- `oci-coordinator-oke` as an external project.
- Lab 12 (split CA into its own lab).
- Power-user "upload custom k6 script" mode.
- Custom-metrics adapter live install (manifest ships, apply gated).
- LB header-based routing live apply.
- CRM and Workflow Gateway HPAs.
- RUM-side stress correlation tiles.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCALE-01 | HPA expansion (shop + java-apm) with CPU + memory + RPS targets | Standard Stack §HPA; Code Examples §HPA v2 manifest; Pattern §RPS via prometheus-adapter; Pitfall §HPA flapping |
| SCALE-02 | OKE Cluster Autoscaler managed add-on, idempotent script | Standard Stack §OKE CA; Code Examples §`configure-cluster-autoscaler.sh`; Pattern §`list-addons` precheck; Pitfall §missing IAM policies |
| SCALE-03 | Admin-only `/admin/stress-test` UI + k6 wrapper | Standard Stack §FastAPI wrapper; Pattern §chaos_admin mirror; Pitfall §concurrency races; Don't-Hand-Roll §audit log shape |
| SCALE-04 | APM saved queries + Monitoring alarms + Log Analytics dashboard | Pattern §Three-channel emit; Code Examples §MQL alarm; Pitfall §dimension cardinality |

## Project Constraints (no `CLAUDE.md` at repo root)

A repository-level `CLAUDE.md` was not found. The global `~/.claude/CLAUDE.md` rules that apply here:

- **No public IPs, secrets, OCIDs, wallet paths, or PII in any committed file** (already a project rule — SEC-04).
- **`deploy/verify.sh` is the offline validation gate** — every new artifact must be catchable by it (D-02 explicit requirement).
- **`oci ce cluster` and `oci lb` mutations are operator-gated** — repo ships scripts + runbooks; the actual apply happens in an approved operator window.
- **OCI Monitoring writes use `telemetry-ingestion.<region>.oraclecloud.com`** (KB-456). The existing `oci_monitoring.py` already does this correctly — new metrics inherit the same path.
- **Image builds for x86_64 happen on the control-plane VM, not locally** (ARM dev machine). The k6 wrapper image is built remotely or pulled directly from `grafana/k6` mirrored through OCIR — no local cross-compile needed.

## Runtime State Inventory

Phase 7 is additive — it does not rename, refactor, or migrate any existing artifact. Verified by reading CONTEXT.md `<decisions>` (every D-* is "new" or "added", none is "renamed"). No rename inventory needed.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — phase introduces new metric names and a new audit log shape; no existing keys/IDs are renamed | None |
| Live service config | New: OCI LB routing-policy rule (header pin), OKE CA add-on config, RPS adapter manifest | All deferred to operator window per CONTEXT.md `<deferred>`; repo only ships the scripts/manifests |
| OS-registered state | None | None |
| Secrets/env vars | New env var `OCTO_STRESS_RUNNER_INTERNAL_KEY` (recommended) for wrapper → CRM admin auth, mirroring `DRONE_SHOP_INTERNAL_KEY` pattern in `simulation.py`. No existing keys renamed | New SOPS entry; documented in runbook |
| Build artifacts | New: `octo-stress-runner` OCIR image (built on control-plane VM, tagged `<timestamp>` + `latest`) | Added to `deploy/oke/build-push-images.sh` if it ships; otherwise documented in operations docs |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `grafana/k6` Docker image | `0.55.x` (latest stable) | Stress engine, native OTLP output | `[CITED: grafana.com/docs/k6 OpenTelemetry]` Battle-tested load tool with native OTLP since the `xk6-output-opentelemetry` extension was upstreamed; pure Go binary, fast cold start (D-07 inline-shell pattern works because the binary is in the image) |
| `prometheus-adapter` (kubernetes-sigs) | Chart `v4.x` from `prometheus-community/helm-charts` | Expose Prometheus RPS metric to HPA via External Metrics API | `[VERIFIED: github.com/kubernetes-sigs/prometheus-adapter]` Dominant choice; serves both `custom.metrics.k8s.io/v1beta1` and `external.metrics.k8s.io/v1beta1`. Simpler than KEDA for this use case (no scale-to-zero needed). Chosen over kube-metrics-adapter (which is more Azure-leaning and less actively maintained). |
| OKE Cluster Autoscaler managed add-on | `ClusterAutoscaler` (Oracle-managed, current Kubernetes-compatible version) | Node pool elasticity | `[CITED: docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengusingclusterautoscaler_topic-Working_with_Cluster_Autoscaler_as_Cluster_Add-on.htm]` Official OKE-managed deployment of upstream `kubernetes/autoscaler`. Oracle owns version + patching when enrolled in auto-updates. |
| OpenTelemetry Python SDK | `1.41.1` (already pinned in `shop/requirements.txt` line 13-20) | App-side tracing | `[VERIFIED: pypi.org/project/opentelemetry-sdk]` Already at latest stable. D-21 verify: no bump needed unless a new stable lands before merge. |
| OpenTelemetry Python instrumentation | `0.62b1` (already pinned) | Auto-instrumentation | `[VERIFIED: shop/requirements.txt:16-20]` Aligns with SDK 1.41.x line. |
| OpenTelemetry Java agent | `2.27.0` (latest stable as of 2026-04) | Java sidecar tracing | `[CITED: github.com/open-telemetry/opentelemetry-java-instrumentation/releases]` Project currently uses OTel Java SDK `1.43.0` in `services/apm-java-demo/pom.xml` line 8 — the agent is a different artifact. D-21 bump: update agent reference to 2.27.0 (or whatever is current at merge time), keep SDK aligned with what the agent embeds. |
| Helm 3 (`>= 3.13`) | Operator's environment | Template rendering | Already required by `deploy/verify.sh` Helm path |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `oci` Python SDK | Current (pinned in `shop/requirements.txt`) | `MonitoringClient.post_metric_data` for new D-17 metrics | Reuse exact pattern in `shop/server/observability/oci_monitoring.py` lines 184-265 |
| `httpx` async client | Current (pinned) | Wrapper → k6 internal API (if split), CRM → wrapper internal API | Mirrors `simulation.py` drone-shop proxy pattern (lines 654-713) |
| `pydantic` v2 | Already pinned | Request validation (`ApplyRequest`-style models in `crm/server/chaos/admin.py:66-78`) | Enforce hard caps D-13 server-side |
| `uuid.uuid4` | stdlib | `run_id` generation | Already used across `simulation.py`, `chaos/admin.py` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `prometheus-adapter` | `kube-metrics-adapter` (Zalando) | More Azure-skewed; smaller community; no clear advantage for our External Metrics shape |
| `prometheus-adapter` | KEDA | Adds scale-to-zero and event-driven scaling we do not need; heavier install footprint; deferred per Don't-Hand-Roll guidance |
| FastAPI wrapper | Bare Python subprocess controller | FastAPI gives us the same admin-API ergonomics already in use, OpenAPI for free, easy health/readiness probes, async lifecycle |
| Long-lived wrapper | Kubernetes Jobs per run | D-07 explicitly chooses long-lived to avoid image-pull cold start. Job approach adds 5-15 s pull latency per run, breaks the "trigger and watch immediately" demo arc |
| OCI LB routing-policy | Nginx ingress header rule | Mixes concerns; the public LB is the demarcation point per DEPLOY-03 — keep ingress untouched, do header pinning at LB |

**Installation (operator-applied during the gated window):**

```bash
# Prometheus stack (skip if already present in cluster)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install prom prometheus-community/prometheus -n octo-autoscaling --create-namespace

# Prometheus adapter exposing RPS as an External Metric
helm upgrade --install prometheus-adapter prometheus-community/prometheus-adapter \
  -n octo-autoscaling \
  -f deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml

# OKE Cluster Autoscaler add-on
deploy/oke/configure-cluster-autoscaler.sh --apply
```

**Version verification status:**

| Package | Pinned in repo | Verified current (as of 2026-05-18) |
|---------|----------------|-------------------------------------|
| `opentelemetry-sdk` (Python) | `1.41.1` | `1.41.1` — already current `[VERIFIED]` |
| `opentelemetry-javaagent` | not yet pinned | `2.27.0` `[CITED: GH releases]` — D-21 bump target |
| OTel Java SDK in pom | `1.43.0` | Verify against agent 2.27.0's embedded version at PR time |
| Helm chart `prometheus-adapter` | not yet pinned | `4.x` line — pin exact at plan time `[ASSUMED — verify at plan]` |
| `grafana/k6` image | not yet pinned | `0.55.x` — pin exact at plan time `[ASSUMED — verify at plan]` |

## Architecture Patterns

### System Architecture Diagram

```
                              [Operator]
                                 │
                                 │ POST /api/admin/stress/apply
                                 ▼
   ┌───────────────────────── admin.${DNS_DOMAIN} ──────────────────────┐
   │  CRM/Admin FastAPI                                                  │
   │  └─ crm/server/modules/stress_test.py                              │
   │       require_admin_user + _require_admin_host + role guard       │
   │       validate caps (D-13) → emit audit (3-channel) → POST to      │
   │       octo-stress-runner /internal/run                             │
   └────────────────────────────────────────────────┬───────────────────┘
                                                    │ httpx (internal key)
                                                    ▼
   ┌─── octo-stress-runner Deployment (octo-stress ns, replicas=1) ────┐
   │  FastAPI wrapper (port 8080, ClusterIP, no Ingress)                │
   │  ├─ /internal/run     → spawn k6 (concurrency=1 guard)             │
   │  ├─ /internal/state   → returns active run_id or null              │
   │  ├─ /internal/clear   → SIGTERM to k6 subprocess                   │
   │  └─ /internal/healthz                                              │
   │      │                                                              │
   │      │ subprocess: k6 run scenarios/<preset>.js                    │
   │      ▼                                                              │
   │  k6 binary (grafana/k6 image)                                      │
   │  ├─ --out experimental-opentelemetry  → OTLP to APM                │
   │  ├─ headers: X-Octo-Stress-Target: oke, X-Run-Id: <uuid>           │
   │  └─ target: https://shop.${DNS_DOMAIN}                             │
   └───────────────────────────────────┬─────────────────────────────────┘
                                       │ HTTPS (header-pinned)
                                       ▼
   ┌── OCI Flexible LB (routing-policy: header eq 'oke' → OKE bset) ───┐
   └───────────────────────────────────┬─────────────────────────────────┘
                                       │
                                       ▼
   ┌── OKE Ingress → Shop Service → Shop Pods (HPA-managed) ───────────┐
   │  Shop pods scrape /metrics (Prometheus exposition)                 │
   │   └─→ prometheus → prometheus-adapter (External Metrics API)      │
   │           └─→ HPA External Metrics → kube-controller-manager       │
   │                  └─→ scale shop deployment (2..10)                 │
   │                          └─→ kubelet → schedule new pods           │
   │                                  └─→ if Pending: CA scales nodes  │
   │                                          (2..4 via OKE add-on)     │
   └────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
   APM ◄── OTel spans (shop, java-apm, stress-runner, CRM admin)
   Monitoring ◄── post_metric_data (octo_apm_demo: pod_count, rps, cpu_sat, hpa_event, ca_event, stress_run_count)
   Log Analytics ◄── push_log (HPA events, CA events, kubelet, stress audit with run_id)
```

### Recommended Project Structure

Following CONTEXT.md `<code_context>` Integration Points and Phase 4 parity rules:

```
deploy/
├── k8s/oke/
│   ├── shop/deployment.yaml                  # HPA edit: maxReplicas 4→10, add RPS metric (gated)
│   ├── apm-java-demo/deployment.yaml         # NEW: add HPA block (was missing)
│   └── stress-runner/                        # NEW DIR
│       ├── namespace.yaml                    # octo-stress
│       ├── deployment.yaml                   # octo-stress-runner FastAPI + k6
│       ├── service.yaml                      # ClusterIP, no Ingress
│       └── rbac.yaml                         # ServiceAccount + minimal role
├── helm/octo-apm-demo/
│   ├── values.yaml                           # add autoscaling.rps.enabled (default false), bump max
│   ├── templates/
│   │   ├── shop-hpa.yaml                     # conditional RPS metric block
│   │   ├── java-gateway-hpa.yaml             # NEW
│   │   ├── stress-runner-deployment.yaml     # NEW (gated by .Values.stressRunner.enabled, default false)
│   │   ├── stress-runner-service.yaml
│   │   └── stress-runner-rbac.yaml
│   └── charts/                               # NEW
│       └── prometheus-adapter-values.yaml    # RPS rule + namespace pin
├── oke/
│   ├── configure-cluster-autoscaler.sh       # NEW — idempotent install/update
│   └── cluster-autoscaler-config.json        # NEW — pinned node pool min/max
crm/server/
├── modules/
│   ├── admin.py                              # add 'stress-operator' to _ALLOWED_ROLES
│   └── stress_test.py                        # NEW — mirrors chaos/admin.py shape
└── templates/
    └── stress_test_admin.html                # NEW — clone of chaos_admin.html
shop/server/observability/
└── oci_monitoring.py                         # add 5 new metric publishers (D-17)
site/
├── workshop/lab-11-oke-autoscaling.md        # NEW
└── operations/stress-demo-lb-routing.md      # NEW — operator runbook
tests/
├── test_unified_deploy_surface.py            # extend with stress-runner manifest checks
└── test_stress_demo_surface.py               # NEW — admin module, audit shape, cap enforcement
```

### Pattern 1: HPA v2 with RPS External Metric

**What:** HPA reconciles against three metrics simultaneously (CPU, memory, RPS) using the documented `selectPolicy: Max` default that picks the largest replica recommendation.

**When to use:** Whenever the underlying CPU correlates poorly with user-perceived load (e.g., I/O-bound checkout that's mostly waiting on java payment + ATP), RPS gives a leading indicator.

**Example:**
```yaml
# Source: kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale + repo shop-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: octo-drone-shop
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: octo-drone-shop
  minReplicas: 2
  maxReplicas: 10                # D-03 raise from 4
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: { type: Utilization, averageUtilization: 60 }   # D-03
    - type: Resource
      resource:
        name: memory
        target: { type: Utilization, averageUtilization: 70 }   # D-03
    - type: External                                            # gated by autoscaling.rps.enabled
      external:
        metric:
          name: shop_request_rate
          selector:
            matchLabels:
              service: octo-drone-shop
        target:
          type: AverageValue
          averageValue: "30"                                    # D-03 RPS/pod
  behavior:                                                     # Claude's-discretion values
    scaleUp:
      stabilizationWindowSeconds: 30        # responsive: demo arc needs visible add within ~30 s
      policies:
        - type: Percent
          value: 100                        # double pods per step max
          periodSeconds: 30
        - type: Pods
          value: 2                          # or +2 pods per step
          periodSeconds: 30
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300       # conservative: hold during 5-min cool-down for Lab 11 narrative
      policies:
        - type: Percent
          value: 25                         # at most 25% of replicas removed per step
          periodSeconds: 60
      selectPolicy: Min
```

**Citation:** `[CITED: kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale]` (HPA v2 spec); behavior tuning rationale from `[CITED: nearform.com/digital-community/hidden-complexities-kubernetes-autoscaling]` and `[CITED: oneuptime.com/blog/2026-02-09-hpa-stabilization-window]`.

### Pattern 2: OKE Cluster Autoscaler Add-on JSON Config

**What:** A single JSON file describes the CA configuration; one `install-addon` call enables it; `update-addon` makes config changes idempotent.

**When to use:** D-04 mandates the managed add-on path for low maintenance and Oracle-driven version updates.

**Example:**
```json
// File: deploy/oke/cluster-autoscaler-config.json
// Source: docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengusingclusterautoscaler_topic-Working_with_Cluster_Autoscaler_as_Cluster_Add-on.htm
{
  "addonName": "ClusterAutoscaler",
  "configurations": [
    {
      "key": "nodes",
      "value": "2:4:${OKE_NODE_POOL_OCID}"
    },
    {
      "key": "authType",
      "value": "instance"
    },
    {
      "key": "numOfReplicas",
      "value": "1"
    },
    {
      "key": "scaleDownDelayAfterAdd",
      "value": "5m"
    },
    {
      "key": "scaleDownUnneededTime",
      "value": "5m"
    },
    {
      "key": "maxNodeProvisionTime",
      "value": "15m"
    }
  ]
}
```

```bash
# File: deploy/oke/configure-cluster-autoscaler.sh (skeleton)
# Source pattern: deploy/oke/install-oci-kubernetes-monitoring.sh
# Source CLI: oci.docs install-addon / update-addon
set -euo pipefail
: "${OCI_PROFILE:=emdemo}"
: "${OKE_CLUSTER_NAME:=octo-apm-demo-oke}"
APPLY=false
case "${1:-}" in
  --apply) APPLY=true ;;
  --dry-run|"") APPLY=false ;;
  -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
esac
CLUSTER_ID="$(oci ce cluster list --profile "$OCI_PROFILE" --compartment-id "$COMPARTMENT_ID" --all --output json \
  | jq -r --arg n "$OKE_CLUSTER_NAME" '.data[] | select(.name==$n and ."lifecycle-state"=="ACTIVE") | .id' | head -n1)"
[[ -z "$CLUSTER_ID" ]] && { echo "Cluster $OKE_CLUSTER_NAME not found in $COMPARTMENT_ID" >&2; exit 1; }

# Idempotency precheck (recommended by Oracle docs)
INSTALLED="$(oci ce cluster list-addons --profile "$OCI_PROFILE" --cluster-id "$CLUSTER_ID" --output json \
  | jq -r '.data.items[]? | select(.name=="ClusterAutoscaler") | .lifecycle-state // empty')"

if [[ "$APPLY" != "true" ]]; then
  echo "DRY RUN: would $( [[ -n "$INSTALLED" ]] && echo update || echo install ) ClusterAutoscaler on $CLUSTER_ID"; exit 0
fi
read -p "Type the cluster name to confirm apply: " CONFIRM
[[ "$CONFIRM" == "$OKE_CLUSTER_NAME" ]] || { echo "Confirmation mismatch — aborting"; exit 2; }

if [[ -n "$INSTALLED" ]]; then
  oci ce cluster update-addon --profile "$OCI_PROFILE" --cluster-id "$CLUSTER_ID" --addon-name ClusterAutoscaler \
    --from-json file://"$(dirname "$0")/cluster-autoscaler-config.json"
else
  oci ce cluster install-addon --profile "$OCI_PROFILE" --cluster-id "$CLUSTER_ID" --addon-name ClusterAutoscaler \
    --from-json file://"$(dirname "$0")/cluster-autoscaler-config.json"
fi
```

**Citation:** `[CITED: docs.oracle.com … Working_with_Cluster_Autoscaler_as_Cluster_Add-on.htm]` (full path in Sources). Idempotency pattern follows the documented `list-addons` precheck.

### Pattern 3: FastAPI k6 Wrapper with Concurrency=1

**What:** Long-lived FastAPI pod that owns a single subprocess slot, spawns `k6 run` inline on POST, terminates with SIGTERM on clear/timeout.

**When to use:** D-07 chose this over Jobs to avoid cold-start pull latency.

**Example skeleton:**
```python
# File: tools/stress-runner/octo_stress_runner/main.py
# Source pattern: shop/server/assistant_service.py for async lifecycle;
#                 grafana.com/docs/k6 for k6 run flags
from __future__ import annotations
import asyncio
import os
import signal
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# ── State (single-slot concurrency guard) ──────────────────────────────
@dataclass
class ActiveRun:
    run_id: str
    pid: int
    started_at: float
    scenario: str
    rps: int
    duration_seconds: int
    proc: asyncio.subprocess.Process = field(repr=False)

_active: ActiveRun | None = None
_lock = asyncio.Lock()

class RunRequest(BaseModel):
    run_id: str = Field(min_length=8, max_length=64)         # CRM generates the UUID
    scenario: str = Field(pattern=r"^(checkout_journey|catalog_browse|login_burst)$")
    rps: int = Field(ge=1, le=200)
    duration_seconds: int = Field(ge=10, le=600)
    target_host: str                                         # https://shop.example.com

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if _active is not None:
        _active.proc.send_signal(signal.SIGTERM)

app = FastAPI(lifespan=lifespan)
INTERNAL_KEY = os.environ["OCTO_STRESS_RUNNER_INTERNAL_KEY"]   # required, no default

def _check_key(provided: str | None) -> None:
    if provided != INTERNAL_KEY:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "internal_key_required")

@app.post("/internal/run", status_code=status.HTTP_202_ACCEPTED)
async def start_run(req: RunRequest, x_internal_key: str | None = None):
    global _active
    _check_key(x_internal_key)
    async with _lock:
        if _active is not None and _active.proc.returncode is None:
            raise HTTPException(status.HTTP_409_CONFLICT, {"active_run_id": _active.run_id})
        env = {
            **os.environ,
            "K6_OTEL_GRPC_EXPORTER_INSECURE": "true",
            "K6_OTEL_METRIC_PREFIX": "k6_",
            "K6_OTEL_EXPORTER_OTLP_ENDPOINT": os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            "K6_VUS": str(max(1, req.rps)),         # 1 VU per target RPS is the simplest mapping
            "K6_DURATION": f"{req.duration_seconds}s",
            "K6_TARGET_HOST": req.target_host,
            "K6_RUN_ID": req.run_id,
        }
        cmd = [
            "k6", "run",
            "--out", "experimental-opentelemetry",
            f"/scenarios/{req.scenario}.js",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _active = ActiveRun(
            run_id=req.run_id, pid=proc.pid, started_at=asyncio.get_event_loop().time(),
            scenario=req.scenario, rps=req.rps, duration_seconds=req.duration_seconds, proc=proc,
        )
        # Safety net: hard timeout = duration + 30s (D-14)
        asyncio.create_task(_hard_timeout(req.run_id, req.duration_seconds + 30))
    return {"run_id": req.run_id, "status": "started"}

@app.post("/internal/clear")
async def clear_run(x_internal_key: str | None = None):
    _check_key(x_internal_key)
    global _active
    async with _lock:
        if _active is None:
            return {"status": "idle"}
        _active.proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(_active.proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            _active.proc.kill()
        run_id = _active.run_id
        _active = None
        return {"status": "stopped", "run_id": run_id}

@app.get("/internal/state")
async def state(x_internal_key: str | None = None):
    _check_key(x_internal_key)
    if _active is None or _active.proc.returncode is not None:
        return {"active": False}
    return {"active": True, "run_id": _active.run_id, "scenario": _active.scenario,
            "rps": _active.rps, "duration_seconds": _active.duration_seconds}

async def _hard_timeout(run_id: str, seconds: int):
    await asyncio.sleep(seconds)
    global _active
    async with _lock:
        if _active is not None and _active.run_id == run_id and _active.proc.returncode is None:
            _active.proc.send_signal(signal.SIGTERM)
```

### Pattern 4: k6 Scenario Skeletons (3 presets)

The repo already ships `shop/k6/checkout-load.js` (close to `checkout_journey`), `shop/k6/cross_service_stress.js` (catalog + checkout), and `crm/k6/stress_test.js` (login flows). The Phase 7 wrapper image should embed scenario files keyed by the D-13 names. Skeleton for `login_burst` (the only one without an obvious existing parent):

```js
// File: tools/stress-runner/scenarios/login_burst.js
// Source: shop/k6/checkout-load.js for shape; D-13 for preset semantics
import http from 'k6/http';
import { check } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

const TARGET = __ENV.K6_TARGET_HOST || 'https://shop.example.test';
const RUN_ID = __ENV.K6_RUN_ID || uuidv4();

export const options = {
  vus: Number(__ENV.K6_VUS || 25),
  duration: __ENV.K6_DURATION || '60s',
  thresholds: { http_req_failed: ['rate<0.10'] },
  tags: { scenario: 'login_burst', run_id: RUN_ID },
};

export default function () {
  const params = {
    headers: {
      'X-Octo-Stress-Target': 'oke',                  // D-09 LB pin
      'X-Run-Id': RUN_ID,                             // propagates to APM via header → span attr
      'User-Agent': 'k6/octo-stress-runner',
      'Content-Type': 'application/json',
    },
    tags: { workflow: 'login_burst', run_id: RUN_ID },
  };
  const res = http.post(
    `${TARGET}/api/auth/login`,
    JSON.stringify({ email: `loadtest+${__VU}@example.test`, password: 'loadtest' }),
    params,
  );
  check(res, { 'login responded < 500': (r) => r.status < 500 });
}
```

### Pattern 5: Three-Channel Audit Emit

**What:** Every stress run produces a structured log + an OCI Monitoring counter increment + an OTel span — all carrying the same `run_id`. This makes the workshop pivot trivial.

**Example:**
```python
# File: crm/server/modules/stress_test.py (excerpt)
# Source pattern: crm/server/modules/coordinator.py for span + push_log shape
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
# Reuse shop/server/observability/oci_monitoring.py — see Don't-Hand-Roll

def _emit_audit(event: str, *, run_id: str, actor: dict, host: str, scenario: str,
                rps: int, duration_seconds: int, target_service: str, target_host: str,
                status_label: str, reason: str = "") -> None:
    fields = {
        "run_id": run_id,                                       # already whitelisted in logging_sdk._SPAN_EVENT_KEYS
        "admin_user": actor.get("email") or actor.get("sub"),
        "admin_role": actor.get("role"),
        "rps_requested": rps,
        "duration_requested": duration_seconds,
        "scenario": scenario,
        "target_service": target_service,
        "target_host": target_host,
        "source_pod": cfg.service_instance_id,
        "status": status_label,
        "reason": reason,
        "workflow.id": "stress-test",
        "workflow.step": event,
    }
    push_log("INFO", f"stress_test.{event}", **fields)
    # OTel span (within a tracer.start_as_current_span block at the caller)
    # OCI Monitoring counter: see oci_monitoring.increment_stress_run(run_id, status_label)
```

### Anti-Patterns to Avoid

- **Building a custom subprocess pool to allow concurrency=N.** D-14 explicitly mandates concurrency=1. Skip the abstraction.
- **Putting `run_id` into the OCI Monitoring dimension *value* of a top-level metric.** Each unique `run_id` creates a new metric stream — high-cardinality dimensions kill query performance. Use `run_id` as a span attribute and a log field; in Monitoring, scope it to the `stress_run_count` counter only (where cardinality is bounded by D-13's hard limits).
- **Letting k6 inherit the wrapper pod's OTLP credentials and emit as the wrapper service.** Set `OTEL_SERVICE_NAME=octo-stress-runner` for k6 so its spans land separately in APM and are filterable. k6's native OTLP output already accepts `OTEL_*` env vars.
- **Re-implementing host-bound checks in `stress_test.py`.** Import or copy `coordinator._require_admin_host` / `_request_host` — the host normalization (forwarded-host handling, port stripping, IPv6 bracket handling, lowercase) is non-trivial and already audited.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Custom RPS → HPA bridge | Webhook posting metrics to HPA via Kubernetes API | `prometheus-adapter` exposing External Metrics API | Adapter handles caching, label projection, RBAC, metric staleness — all hard to get right; HPA only consumes from the official APIs |
| Standalone Cluster Autoscaler deployment | Helm-installed upstream `cluster-autoscaler` chart against OKE | OKE managed add-on via `oci ce cluster install-addon` | D-04 mandates managed; Oracle owns version/upgrade; IAM via dynamic group is documented |
| Custom subprocess manager | `multiprocessing` / process pool / supervisor inside the wrapper | Plain `asyncio.create_subprocess_exec` with a single-slot lock | One run at a time per D-14; the lock is 10 lines, anything fancier hides the constraint |
| Custom span/log correlator | Self-rolled trace_id/span_id capture | `server.observability.otel_setup.get_tracer` + `push_log` | Already wired across shop + CRM; matches the Log Analytics parser whitelist (logging_sdk._SPAN_EVENT_KEYS) |
| Custom OCI metric publisher | Direct REST calls to telemetry-ingestion | `MonitoringClient.post_metric_data` via the existing `oci_monitoring.py` helper | KB-456 documents the ingestion-endpoint override; auth-mode handling is already correct |
| Custom LB header rule applier | API calls from Phase 7 deploy script | Documented runbook + manual `oci lb routing-policy create/update` in the operator window | DEPLOY-04 keeps live LB changes operator-only |
| Custom CSRF/nonce on the admin form | Hand-rolled token | Existing `csp_nonce` from `request.state` (see chaos_admin.html line 49) | Already wired in the base template |

**Key insight:** Phase 7 has more "use existing primitive X" than "build new thing Y." The CONTEXT.md decisions deliberately route every new artifact through an existing helper (oci_monitoring, push_log, get_tracer, require_admin_user, _require_admin_host, csp_nonce, chaos_admin pattern). Resist the temptation to introduce a new admin framework.

## Common Pitfalls

### Pitfall 1: HPA flapping during demo cool-down

**What goes wrong:** Without `scaleDown.stabilizationWindowSeconds`, replicas oscillate around the threshold and Lab 11 "watch scale-down" step shows confusing repeated up/down moves.

**Why it happens:** Default behavior is responsive in both directions; brief metric dips trigger immediate scale-down which then scales back up.

**How to avoid:** Set `scaleDown.stabilizationWindowSeconds: 300` and a conservative `scaleDown.policies.value: 25` per `Percent` per 60 s. Scale-up stays at 30 s window with 100% Percent / +2 Pods so the narrative moves visibly.

**Warning signs:** APM pod-count saved query (D-16.1) shows zig-zag instead of plateau-then-decline.

### Pitfall 2: prometheus-adapter returns no External Metric — HPA silently skips RPS

**What goes wrong:** HPA stays CPU-only and the "Lab 11 RPS-driven scale" demo is a lie.

**Why it happens:** prometheus-adapter Helm values misalign the Prometheus label set with the HPA's `metric.selector.matchLabels`; or the Prometheus scrape rule never sees the `/metrics` endpoint; or the External Metric is named differently than the HPA expects.

**How to avoid:** Three-step validation, all offline-feasible:
1. `kubectl get apiservice v1beta1.external.metrics.k8s.io` → `Available`.
2. `kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1/namespaces/<ns>/shop_request_rate?labelSelector=service=octo-drone-shop"` → returns a non-empty `items` array.
3. `kubectl describe hpa octo-drone-shop` → no `FailedGetExternalMetric` warning in Events.

Bake step 2 + 3 into a `deploy/oke/verify-rps-hpa.sh` smoke script the operator runs in the apply window.

**Warning signs:** `kubectl describe hpa` shows `unknown` for the RPS metric, or "the HPA was unable to compute the replica count".

### Pitfall 3: OKE Cluster Autoscaler add-on missing dynamic-group policies

**What goes wrong:** Add-on installs successfully but never scales because it cannot call `core.NodePool.update`. Symptom: pods stay `Pending` with `0/2 nodes available` even though the policy allows scaling.

**Why it happens:** Default dynamic group covers compute instances but not always `cluster-node-pools` manage rights.

**How to avoid:** Verify policy presence before apply — the documented six statements (manage cluster-node-pools, manage instance-family, use subnets, read virtual-network-family, use vnics, inspect compartments) must all exist. Document in the runbook + add a `oci iam policy list` check to the configure script's `--dry-run`.

**Warning signs:** `kubectl logs -n kube-system cluster-autoscaler-...` shows `403` on `UpdateNodePool` / `NotAuthorizedOrNotFound`.

### Pitfall 4: k6 spans tagged with stress runner's service name pollute APM dashboards

**What goes wrong:** k6's OTLP output uses the same `OTEL_SERVICE_NAME` as the wrapper, so the `service.name` filter in APM saved queries mixes wrapper health spans with synthetic load spans.

**How to avoid:** Set k6 subprocess env `OTEL_SERVICE_NAME=octo-stress-load` (separate from the wrapper's `octo-stress-runner`). APM saved queries can then exclude `service.name = 'octo-stress-load'` from latency-percentile panels where appropriate.

### Pitfall 5: LB header rule applied to wrong listener

**What goes wrong:** Routing-policy attached to the HTTP listener, not HTTPS — k6 traffic over HTTPS skips the pin and round-robins to VM, breaking DEPLOY-03 guarantee.

**How to avoid:** Runbook explicitly names the listener (`https-443` or whatever the existing `wire-existing-lb-backends.sh` uses) and the test command: `curl -k -H 'X-Octo-Stress-Target: oke' https://shop.${DNS_DOMAIN}/healthz -v` should show OKE backend response markers.

### Pitfall 6: Audit event without trace_id

**What goes wrong:** Stress audit log entry has every field except `trace_id` because the FastAPI handler does not start a span before calling `push_log`. The Logan→APM pivot in Lab 11 then fails.

**How to avoid:** Always wrap audit emit inside `with tracer.start_as_current_span("admin.stress.apply"): ...` — `push_log` reads the active span context automatically.

### Pitfall 7: `run_id` not flowing through `httpx` to the wrapper

**What goes wrong:** CRM emits a `run_id`, calls wrapper, wrapper k6 generates its own. Two `run_id`s in two systems — pivots break.

**How to avoid:** CRM generates the UUID, passes via request body to wrapper, wrapper passes via `K6_RUN_ID` env to k6, k6 tags every request with the header. Single value end-to-end. Add a test for this (`test_stress_demo_surface.py::test_run_id_is_caller_generated`).

## Code Examples

### MQL alarm: shop_cpu_saturation_pct > 80 for 2 min

```
# Source: docs.oracle.com/en-us/iaas/Content/Monitoring/Reference/mql.htm
# Phase 7 D-18.1
shop_cpu_saturation_pct[1m]{resourceDisplayName = "octo-drone-shop"}.mean() > 80
# Alarm: 2 consecutive triggers (interval 1m, pending duration 2m)
```

### MQL alarm: HPA at max replicas for > 5 min

```
# Phase 7 D-18.2 — relies on D-17 shop_pod_count gauge with dim=service:octo-drone-shop
shop_pod_count[1m]{service="octo-drone-shop"}.max() == 10
# Pending duration 5m
# Note: the threshold value `10` must match HPA maxReplicas (D-03). If maxReplicas changes,
# update the alarm. Document this coupling in the operator runbook.
```

### OCI LB routing-policy rule (header pin)

```json
// Source: docs.oracle.com/en-us/iaas/Content/Balance/Concepts/routing_policy_conditions.htm
{
  "name": "octo_stress_target_oke",
  "condition": "http.request.headers[(i 'X-Octo-Stress-Target')] eq 'oke'",
  "actions": [
    { "name": "FORWARD_TO_BACKENDSET", "backendSetName": "octo-oke-backend-set" }
  ]
}
```

### APM saved query: pod-count-over-time (D-16.1)

```
# Source: docs.oracle.com/en-us/iaas/application-performance-monitoring + apm query language
# Filter span.kind = SERVER, group by k8s.pod.name + service.name, 1m buckets, span count distinct
service.name in ("octo-drone-shop", "octo-apm-java-demo")
AND span.kind = "SERVER"
| timeseries count(distinct k8s.pod.name) every 1m by service.name
```

### Log Analytics saved search: HPA scale events

```
# Source: docs.oracle.com/en-us/iaas/logging-analytics + Phase 3 parser contract
'Log Source' = 'Kubernetes Logs' AND Subsystem = 'horizontal-pod-autoscaler'
| where Content matches /(?i)(scaled up|scaled down|new size)/
| timestats count() by 'k8s.deployment.name'
```

### OCI Monitoring publisher addition (D-17)

```python
# File: shop/server/observability/oci_monitoring.py — add to _build_metric_data()
# Mirror existing _point() pattern at line 146
_point("shop_pod_count", float(_current_pod_count()), "count"),
_point("shop_request_rate", float(snapshot["requests"]) / PUBLISH_INTERVAL, "count_per_second"),
_point("shop_cpu_saturation_pct", float(_read_cpu_saturation()), "percent"),
# Counters are emitted on event, not on the publish tick — see increment_hpa_decision() below
```

For event-driven counters (`hpa_decision_event`, `cluster_autoscaler_node_event`, `stress_run_count`): post on the event itself via a new helper that follows the same client/auth path. Do not roll into the publish loop because the events are sparse and need accurate timestamps.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Standalone `cluster-autoscaler` chart on OKE | OKE managed add-on (`oci ce cluster install-addon`) | GA throughout 2024-2025 | Oracle owns version/upgrade; IAM via dynamic group is documented; no Helm chart to manage |
| Custom OTLP shim for k6 | `k6 run --out experimental-opentelemetry` (native, env-driven via `K6_OTEL_*`) | k6 0.55+ in 2025 | Drop hand-rolled stats forwarding; correlate directly with APM |
| `autoscaling/v2beta2` HPA | `autoscaling/v2` (stable since Kubernetes 1.23) | Long stable; already used by repo | No migration risk — repo already on v2 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` only | `K6_OTEL_*` overrides preferred for k6 (precedence over SDK env) | k6 native OTLP doc | Wrapper must set `K6_OTEL_*` to avoid SDK-env confusion |

**Deprecated/outdated:**
- HPA v2beta2 — drop in favor of v2 (we are already on v2).
- `xk6-output-opentelemetry` external extension — upstreamed; use the built-in `experimental-opentelemetry` output via stock `grafana/k6` image.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `prometheus-adapter` chart `4.x` is current and stable for our K8s version (OKE v1.34) | Standard Stack | Wrong version → API service not Available; smoke test in Pitfall §2 catches it before merge |
| A2 | `grafana/k6` image `0.55.x` line includes native `experimental-opentelemetry` output | Standard Stack | If older image, OTLP correlation breaks; planner should pin a specific tested tag |
| A3 | OTel Java agent `2.27.0` is fully compatible with the existing payment java service's spring-boot 3.3.5 + Java 21 | Standard Stack §Java | Bump may force minor instrumentation config changes; test under Phase 7 validation |
| A4 | `K8S_NODE_POOL_OCID` is available from `credentials/emdemo/outputs.json` (existing convention in `create-emdemo-small-cluster.sh:42`) | Pattern §CA config | If the OCID is not exported there, the configure script needs an extra env var; verify at plan time |
| A5 | The existing `octo-oke-backend-set` name is correct for the routing-policy rule | Code Examples §LB rule | Wrong backend set name → operator command fails; check `deploy/oke/wire-existing-lb-backends.sh` at plan time |
| A6 | `cfg.service_instance_id` is set inside the wrapper pod (it is set for shop/crm); needs verification for a brand-new deployment | Code Examples §audit emit | If unset, `source_pod` field is blank in audit; set explicitly from `MY_POD_NAME` env (downward API) |

## Open Questions

1. **Should the RPS metric source be application-internal Prometheus exposition or OCI Monitoring read-back?**
   - What we know: prometheus-adapter expects Prometheus exposition (`/metrics`). The shop already runs `opentelemetry-exporter-prometheus==0.62b1` (in `requirements.txt`).
   - What's unclear: Whether `octo_apm_demo` namespace OCI Monitoring data can be read back into the cluster via an OCI-Monitoring-compatible adapter and used as an External Metric. There exists no widely-deployed OCI Monitoring → Custom Metrics adapter, so this would be a build, not a buy.
   - Recommendation: Use the in-cluster Prometheus path for HPA decision (fast, well-trodden). Continue to publish to `octo_apm_demo` for the dashboard/alarm story (decoupled concern). D-02 explicitly allows this split — re-read it: "The RPS metric is published to the `octo_apm_demo` OCI Monitoring namespace **and** exposed to HPA via a Kubernetes Custom/External Metrics adapter." Two channels, not one.

2. **Where does the `octo-stress-runner` Deployment live — `shop` namespace or new `octo-stress` namespace?**
   - What we know: CONTEXT.md `<code_context>` says "shop namespace so it can reach the in-cluster ingress and inherits the same imagePullSecret + RBAC posture." That is one option.
   - What's unclear: The existing `tools/traffic-generator/k8s/deployment.yaml` uses its own `octo-traffic` namespace deliberately for kill-switch isolation. Same logic might apply to the stress runner.
   - Recommendation: New `octo-stress` namespace, mirroring `octo-traffic`. Imagepull is per-namespace but `imagePullSecret` is easy to replicate. Isolation is more valuable than the namespace re-use saving.

3. **Does k6 actually need OTLP enabled for the demo to "tell the story," or does the OTLP add noise without value?**
   - What we know: k6's OTLP output emits k6-internal metrics (vu_count, http_req_duration, etc.) as OTel metrics — not spans.
   - What's unclear: Whether OTel metrics published from k6 land usefully in OCI APM (which is span-oriented) vs. cluttering it.
   - Recommendation: Enable OTLP for the run, but route k6's OTLP to a separate `OTEL_SERVICE_NAME=octo-stress-load`. If it adds noise, plan phase can disable it; the shop/java spans alone tell the scale-up story. Mark this LOW confidence in the plan and re-validate after first end-to-end run.

## Environment Availability

This phase touches several external tools. Audited from typical operator workstation + control-plane VM availability.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `oci` CLI | configure-cluster-autoscaler.sh, runbook | Yes (operator) | `>= 3.x` | None — required for live apply |
| `kubectl` | manifest validation, smoke tests | Yes (operator) | matching OKE 1.34 | None |
| `helm` | prometheus-adapter install, charts | Yes | `>= 3.13` | None |
| `jq` | scripts | Yes | any | None |
| `docker` (for image build) | k6-wrapper image build on control-plane VM | Yes (control-plane-oci) | 29.x | None — local build forbidden (ARM dev box) |
| `oci ce cluster install-addon` API permission | live CA install | Operator window only | n/a | None — defer to operator window |
| Prometheus already deployed in cluster | RPS adapter scrape source | Unknown — verify at plan time | n/a | Install prometheus-community/prometheus chart in same operator window |
| OCI Monitoring write permission | new D-17 metrics | Already proven (existing publisher works) | n/a | n/a |

**Missing dependencies with no fallback:** None — every required tool is part of the standard operator workstation that already runs the existing OCI scripts.

**Missing dependencies with fallback:** In-cluster Prometheus — if absent, ship the Helm install alongside prometheus-adapter under the same operator window.

## Validation Architecture

Required by `workflow.nyquist_validation: true` (config.json line 19).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest with markers (`unit`, `integration`); already in use per `tests/test_unified_deploy_surface.py` etc. |
| Config file | `pyproject.toml` per app, plus root-level `tests/` directory containing the deploy/observability surface tests |
| Quick run command | `pytest tests/test_unified_deploy_surface.py tests/test_stress_demo_surface.py -x -q` |
| Full suite command | `pytest tests/ -x` followed by `./deploy/verify.sh` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCALE-01 | shop HPA renders with `maxReplicas: 10` and RPS metric block when `autoscaling.rps.enabled=true` | unit (Helm template) | `pytest tests/test_unified_deploy_surface.py::test_shop_hpa_rps_metric_renders -x` | ❌ Wave 0 |
| SCALE-01 | java-apm HPA exists in both raw and Helm | unit (manifest) | `pytest tests/test_unified_deploy_surface.py::test_java_apm_hpa_present -x` | ❌ Wave 0 |
| SCALE-01 | RPS metric defaults to disabled (backward compat D-05) | unit | `pytest tests/test_unified_deploy_surface.py::test_autoscaling_rps_disabled_by_default -x` | ❌ Wave 0 |
| SCALE-02 | `configure-cluster-autoscaler.sh` passes `bash -n` and `--help` | unit (script) | already caught by `deploy/verify.sh` syntax + help sections | ✅ (auto via verify.sh) |
| SCALE-02 | `cluster-autoscaler-config.json` parses, has `min:max` matching D-04 | unit | `pytest tests/test_stress_demo_surface.py::test_ca_config_node_bounds -x` | ❌ Wave 0 |
| SCALE-02 | configure script requires confirmation token before applying | unit (subprocess) | `pytest tests/test_stress_demo_surface.py::test_ca_script_requires_confirmation -x` | ❌ Wave 0 |
| SCALE-03 | `/api/admin/stress/apply` rejects RPS > 200 with 422 | unit (FastAPI client) | `pytest tests/test_stress_demo_surface.py::test_stress_apply_caps -x` | ❌ Wave 0 |
| SCALE-03 | Concurrent POST returns 409 with active `run_id` | unit | `pytest tests/test_stress_demo_surface.py::test_stress_concurrency_guard -x` | ❌ Wave 0 |
| SCALE-03 | Audit event contains all 14 D-15 fields | unit | `pytest tests/test_stress_demo_surface.py::test_audit_event_shape -x` | ❌ Wave 0 |
| SCALE-03 | Non-admin role → 403 | unit | `pytest tests/test_stress_demo_surface.py::test_stress_requires_admin -x` | ❌ Wave 0 |
| SCALE-03 | Non-admin host → 403 | unit | `pytest tests/test_stress_demo_surface.py::test_stress_requires_admin_host -x` | ❌ Wave 0 |
| SCALE-03 | `stress-operator` added to `_ALLOWED_ROLES` | unit | `pytest tests/test_stress_demo_surface.py::test_stress_operator_role_registered -x` | ❌ Wave 0 |
| SCALE-04 | New OCI Monitoring metric names present in publisher | unit | `pytest tests/test_observability_asset_contract.py::test_stress_metrics_registered -x` (extend existing) | ⚠️ extend |
| SCALE-04 | 2 alarms render with correct MQL | unit | `pytest tests/test_observability_asset_contract.py::test_stress_alarms_mql -x` | ⚠️ extend |
| SCALE-04 | 4 Log Analytics saved searches present and parse | unit | `pytest tests/test_log_analytics_attack_assets.py` extension | ⚠️ extend |
| SCALE-04 | 4 APM saved queries shipped | unit | `pytest tests/test_observability_asset_contract.py::test_stress_apm_saved_queries -x` | ⚠️ extend |
| Phase | `deploy/verify.sh` catches a missing RPS adapter manifest | integration | `bash deploy/verify.sh` (extend Helm/YAML section) | ⚠️ extend |
| Phase | Lab 11 markdown builds in mkdocs | integration | `mkdocs build --strict` (already in verify.sh) | ✅ |

### Sampling Rate

- **Per task commit:** `pytest tests/test_stress_demo_surface.py -x -q` (~2 s)
- **Per wave merge:** `pytest tests/ -x` + `deploy/verify.sh`
- **Phase gate:** Full suite + `mkdocs build --strict` + manual Helm template render snapshot review

### Wave 0 Gaps

- [ ] `tests/test_stress_demo_surface.py` — NEW file, ~10 tests above (covers SCALE-02, SCALE-03, audit shape)
- [ ] Test fixtures: a `Request`-mock factory that sets `state.current_user` with admin/non-admin roles and a configurable `Host` header (matches the chaos_admin / coordinator pattern). Place under `tests/conftest.py` or `crm/tests/conftest.py` — check whether one exists.
- [ ] Extend `tests/test_unified_deploy_surface.py` with: `test_shop_hpa_max_replicas_raised`, `test_java_apm_hpa_present`, `test_stress_runner_deployment_referenced_in_helm`.
- [ ] Extend `tests/test_observability_asset_contract.py` with the 5 D-17 metric names + 2 D-18 alarms + 4 D-16 APM saved queries + 4 D-19 Log Analytics saved searches.
- [ ] Helm `prometheus-adapter` values YAML must lint as a real Helm subchart (already verified by `deploy/verify.sh` Helm section once the path is in scope).

**Decision on test file split (Claude's discretion under D):** Add a new `tests/test_stress_demo_surface.py` for the admin-module + audit-shape + cap-enforcement tests (logical cohesion); extend the existing `tests/test_unified_deploy_surface.py` only with manifest-presence tests (matches its existing role).

## Security Domain

Security enforcement is enabled (default). Phase 7 deliverables touch admin operations, load balancer routing, and managed-add-on installation — all security-sensitive.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Reuse `require_admin_user` from `crm/server/modules/_authz.py`; reuse `coordinator._require_admin_host` for host binding; wrapper internal API uses `X-Internal-Service-Key` matching the existing `simulation.py` proxy pattern |
| V3 Session Management | yes | Inherits existing CRM session middleware — no new tokens issued |
| V4 Access Control | yes | New `stress-operator` role added to `_ALLOWED_ROLES`; double-gate: admin role + host pinning to `admin.${DNS_DOMAIN}` |
| V5 Input Validation | yes | Pydantic models with explicit ranges (D-13: `rps` ge=1 le=200; `duration_seconds` ge=10 le=600; `scenario` regex; `target_service` enum) |
| V6 Cryptography | no | No new cryptographic surfaces; existing TLS via LB |
| V7 Error Handling | yes | Return generic 409/403/422 to client; full diagnostic to structured logs only (already the pattern) |
| V8 Data Protection | yes | Audit `admin_user` field may be a hashed user id (like `chaos/admin.py:_hash_user`) to avoid PII in logs — decide at plan time |
| V10 Malicious Code | yes | k6 scripts are repo-shipped, not operator-uploaded (deferred per CONTEXT.md `<deferred>`). No arbitrary-script execution path |
| V14 Configuration | yes | `autoscaling.rps.enabled` defaults false; `stress-runner` Helm gate defaults false; CA configure script requires interactive confirmation |

### Known Threat Patterns for {Python FastAPI + k6 + OKE}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Admin endpoint accessible from customer host | Elevation of Privilege | Host-binding via `_require_admin_host` (Phase 5 contract) |
| Stress run launched by unauthorized role | Elevation of Privilege | Role gate + audit log |
| Concurrent runs DoS the shop deployment | Denial of Service | Server-side concurrency=1 + hard caps (D-13/14) |
| Wrapper accepts requests from anyone in cluster | Tampering | `X-Internal-Service-Key` shared secret; Network Policy restricting ingress to CRM namespace |
| k6 scripts injected from operator UI | Tampering / RCE | Scripts shipped in image; no upload path (deferred) |
| Audit log leaks plaintext user identity | Information Disclosure | Hash admin user id before logging (chaos_admin pattern) |
| CA add-on policy too broad | Elevation of Privilege | Dynamic group scoped to OKE cluster compartment only — verify in runbook |
| LB header trivially spoofable by external clients | Spoofing | The header is a routing hint, not a security claim; it pins traffic to OKE, doesn't bypass auth. Document this distinction in the runbook |

## Sources

### Primary (HIGH confidence)

- `[CITED]` Oracle docs — Working with Cluster Autoscaler as a Cluster Add-on — https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengusingclusterautoscaler_topic-Working_with_Cluster_Autoscaler_as_Cluster_Add-on.htm — CLI, JSON config schema, IAM policies, idempotency precheck
- `[CITED]` Oracle docs — Installing a Cluster Add-on — https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/install-add-on.htm
- `[CITED]` Oracle docs — Updating a Cluster Add-on — https://docs.public.content.oci.oraclecloud.com/en-us/iaas/Content/ContEng/Tasks/update-add-on.htm
- `[CITED]` Oracle docs — Routing Policy Language for Load Balancers — https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/routing_policy_conditions.htm — header expression syntax `http.request.headers[(i 'name')] eq 'value'`
- `[CITED]` Oracle docs — Routing Policies for Load Balancers — https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/routing-policy_management.htm
- `[CITED]` Kubernetes docs — Horizontal Pod Autoscaling — https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/ — HPA v2 spec, `behavior` field, `stabilizationWindowSeconds`
- `[CITED]` Kubernetes enhancements KEP-853 — configurable HPA scale velocity — https://github.com/kubernetes/enhancements/blob/master/keps/sig-autoscaling/853-configurable-hpa-scale-velocity/README.md
- `[CITED]` prometheus-adapter repo — https://github.com/kubernetes-sigs/prometheus-adapter — custom + external metrics API
- `[CITED]` prometheus-adapter external metrics doc — https://github.com/kubernetes-sigs/prometheus-adapter/blob/master/docs/externalmetrics.md
- `[CITED]` Grafana k6 docs — OpenTelemetry output — https://grafana.com/docs/k6/latest/results-output/real-time/opentelemetry/ — `K6_OTEL_*` env vars
- `[CITED]` OpenTelemetry Python releases — https://github.com/open-telemetry/opentelemetry-python/releases — current 1.41.1
- `[CITED]` PyPI opentelemetry-sdk — https://pypi.org/project/opentelemetry-sdk/
- `[CITED]` OpenTelemetry Java Instrumentation releases — https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases — current 2.27.0 (Apr 21, 2026)
- `[VERIFIED]` Repo file `shop/server/observability/oci_monitoring.py` — `post_metric_data` pattern, KB-456 ingestion endpoint, namespace `octo_apm_demo`
- `[VERIFIED]` Repo file `crm/server/chaos/admin.py` — pattern for admin-only audited operator surface (router prefix, role guard, audit log shape, template page route)
- `[VERIFIED]` Repo file `crm/server/modules/coordinator.py` — host-binding helpers `_require_admin_host`, `_request_host`, configured admin host resolution
- `[VERIFIED]` Repo file `crm/server/modules/_authz.py` — `require_admin_user`
- `[VERIFIED]` Repo file `crm/server/modules/admin.py:20` — `_ALLOWED_ROLES = {"admin", "manager", "viewer", "user", "chaos-operator"}` — extension point
- `[VERIFIED]` Repo file `shop/requirements.txt` — `opentelemetry-sdk==1.41.1`, instrumentation 0.62b1
- `[VERIFIED]` Repo files `shop/k6/*.js` and `crm/k6/*.js` — existing scenario scripts reusable for the wrapper
- `[VERIFIED]` Repo file `deploy/oke/install-oci-kubernetes-monitoring.sh` — pattern for `oci ce cluster get/list` + cluster ID lookup
- `[VERIFIED]` Repo file `services/apm-java-demo/pom.xml` — Java OTel SDK 1.43.0 (D-21 verify vs agent 2.27.0)

### Secondary (MEDIUM confidence)

- Nearform — Hidden complexities of Kubernetes autoscaling — https://nearform.com/digital-community/the-hidden-complexities-of-kubernetes-autoscaling-beyond-the-basics/
- OneUptime — HPA stabilization window to prevent thrashing — https://oneuptime.com/blog/post/2026-02-09-hpa-stabilization-window-prevent-thrashing/view
- OneUptime — k6 with OpenTelemetry for load testing — https://oneuptime.com/blog/post/2026-02-06-k6-otel-load-testing-trace-correlation/view
- OneUptime — prometheus-adapter custom metrics HPA — https://oneuptime.com/blog/post/2026-02-09-prometheus-adapter-custom-metrics-hpa/view
- Timotej Kovacka — Scaling k6 in Kubernetes with OTLP — https://timotejkovacka.netlify.app/blog/k6-otlp-guide/
- DevOpsil — Kubernetes HPA with custom metrics — https://devopsil.com/articles/2026-03-21-kubernetes-hpa-custom-metrics-guide

### Tertiary (LOW confidence — flagged for validation)

- Brave Search result on `oci lb routing-policy update` operator runbook examples — not directly observed; the documented routing-policy syntax (Primary, above) is sufficient

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Oracle docs are authoritative for CA add-on, Kubernetes docs for HPA, GitHub releases for OTel versions, repo files confirm Python pins
- Architecture patterns: HIGH — every pattern grounded in either an Oracle doc or an existing repo file
- Pitfalls: MEDIUM-HIGH — drawn from documented k8s/HPA behavior plus repo-specific gotchas (KB-456 endpoint, host normalization)
- Security domain: HIGH — Phase 5 contract is already in code; this phase reuses it
- Validation architecture: HIGH — extends existing test files with verified patterns

**Research date:** 2026-05-18
**Valid until:** 2026-06-15 (30 days — stable area; refresh only if Oracle releases a major CA add-on revision or k6 ships a breaking OTLP change)

## RESEARCH COMPLETE
