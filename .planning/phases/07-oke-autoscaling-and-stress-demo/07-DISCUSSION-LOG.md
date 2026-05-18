# Phase 7: OKE Autoscaling and Stress Demo - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 07-oke-autoscaling-and-stress-demo
**Areas discussed:** HPA + Cluster Autoscaler scope, Load generator approach, Admin stress-test UI + safety, Observability narrative depth

**User-stated framing constraints (applied across all areas):**
- Showcase visibility into the backend through OCI Observability services.
- Demonstrate autoscaling and on-demand scaling based on usage.
- Service must work end-to-end, demo-ready and workshop-ready.
- Don't break anything (additive changes only; respect VM/OKE LB round-robin from DEPLOY-03).

---

## Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| HPA + Cluster Autoscaler scope | Which services get HPA expanded; managed vs upstream CA; node pool sizing | ✓ |
| Load generator approach | k6 vs traffic-generator vs Locust vs hey; Job vs Deployment lifecycle | ✓ |
| Admin stress-test UI + safety | Page layout; parameters; safe-stop; audit fields | ✓ |
| Observability narrative depth | APM queries, Monitoring metrics+alarms, Log Analytics dashboards, Workshop Lab 11 | ✓ |

**User's choice:** All four areas, plus framing constraints above.

---

## HPA + Cluster Autoscaler Scope

### Q1: Which services get expanded HPA?

| Option | Description | Selected |
|--------|-------------|----------|
| Shop only (Recommended) | Min=2 → max=10, CPU+memory targets; cleanest narrative | |
| Shop + CRM | Adds admin/orders surface to story | |
| Shop + CRM + Java APM sidecar | Most complete, most work | |
| Shop + Java APM sidecar | Focuses scale on checkout path; skips CRM | ✓ |

**User's choice:** Shop + Java APM sidecar.
**Notes:** Keeps CRM untouched to minimize blast radius while still scaling the customer checkout path end-to-end.

### Q2: HPA metrics

| Option | Description | Selected |
|--------|-------------|----------|
| CPU + memory only (Recommended) | Zero extra adapter dependency | |
| CPU + memory + RPS via OCI Monitoring adapter | More visceral demo; adds adapter Deployment | ✓ |
| CPU only, lower target | Simplest, loses memory signal | |

**User's choice:** CPU + memory + RPS via OCI Monitoring adapter.
**Notes:** User accepts the new in-cluster adapter dependency for a stronger demo.

### Q3: Cluster Autoscaler strategy

| Option | Description | Selected |
|--------|-------------|----------|
| OKE managed Cluster Autoscaler add-on (Recommended) | OCI-supported, less in-cluster YAML | ✓ |
| Upstream Cluster Autoscaler Deployment in-cluster | Full self-managed YAML | |
| Manual node-pool scaling (no CA) | Breaks "autoscaling" narrative | |

**User's choice:** OKE managed Cluster Autoscaler add-on.
**Notes:** Apply step is operator-gated (non-destructive guardrail).

### Q4: Node pool sizing

| Option | Description | Selected |
|--------|-------------|----------|
| min 2, max 4 (Recommended) | Visible +1 node event, cost-friendly | ✓ |
| min 2, max 6 | More dramatic; risks tenancy OCPU limits | |
| min 3, max 5 | Always 3 baseline; costs more at idle | |

**User's choice:** min 2, max 4.
**Notes:** Matches current emdemo small cluster baseline (2 nodes).

---

## Load Generator Approach

### Q1: Load engine

| Option | Description | Selected |
|--------|-------------|----------|
| k6 (Recommended) | Go binary, OTLP output, predictable RPS | ✓ |
| Extend tools/traffic-generator with burst mode | Reuse existing tool; not designed for sustained load | |
| Locust | Python, web UI clashes with admin UI | |
| hey | Tiny but only single-endpoint blast | |

**User's choice:** k6.
**Notes:** Native OTLP output ensures the load itself shows up in APM/Monitoring.

### Q2: k6 lifecycle (first answer)

| Option | Description | Selected |
|--------|-------------|----------|
| Ephemeral Job per stress run (Recommended) | Fresh Job per run, TTL cleanup | ✓ (initial) |
| Long-lived k6 Deployment toggled by admin | Faster start, risk of forgotten state | |
| k6 Operator (CRD) | Most native, more deps | |

**User's choice (initial):** Ephemeral Job per stress run.

### Q2-revised: k6 lifecycle (after user follow-up)

**User follow-up:** "We need to have the K6 up and running as the demos are usually short, and the data needs to be generated fast and the jobs quick."

| Option | Description | Selected |
|--------|-------------|----------|
| Long-lived k6 wrapper Deployment (Recommended) | Wrapper always running; admin POST shells `k6 run` inline | ✓ |
| Always-running k6 with HTTP control via k6 REST API | Uses k6's built-in API; awkward script swap | |
| Pre-warmed Job pool (DaemonSet image pre-pull) | Cleaner lifecycle, more k8s objects | |

**User's choice (final):** Long-lived k6 wrapper Deployment.
**Notes:** Optimized for fast demo turnaround. Concurrency=1 enforced in the wrapper.

### Q3: k6 target URL

| Option | Description | Selected |
|--------|-------------|----------|
| In-cluster ClusterIP (Recommended) | Deterministic, no public traffic | |
| Public LB hostname (shop.${DNS_DOMAIN}) | Realistic full path via LB+WAF+ingress | ✓ |
| Configurable per stress run | More flexibility, more audit surface | |

**User's choice:** Public LB hostname.
**Notes:** More realistic demo; triggers VM/OKE round-robin concern in next question.

### Q4: VM/OKE round-robin guard (DEPLOY-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Routing hint header LB pins to OKE (Recommended) | k6 sends `X-Octo-Stress-Target: oke`; LB rule pins to OKE backend | ✓ |
| Operator drains VM backend before stress run | Manual; no infra change | |
| OKE-specific public hostname | Would need new DNS/LB listener | |
| Accept VM also receives load | Violates "don't break anything" | |

**User's choice:** Routing hint header LB pins to OKE.
**Notes:** LB rule itself applied in same operator window as CA add-on enablement.

---

## Admin Stress-Test UI + Safety

### Q1: UI structure

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated /admin/stress-test page, chaos_admin.html pattern (Recommended) | Mirrors existing admin scenario UI | ✓ |
| Tab inside existing chaos_admin.html | Mixes chaos and stress concepts | |
| CLI-only (no UI) | Loses workshop click moment | |

**User's choice:** Dedicated /admin/stress-test page.

### Q2: Parameters and caps

| Option | Description | Selected |
|--------|-------------|----------|
| RPS + duration + scenario preset, capped (Recommended) | Server-side validation enforces caps | ✓ |
| RPS + duration + custom k6 script upload | Power-user mode; high risk surface | |
| Preset scenarios only (no numeric inputs) | Workshop-friendly; less flexible | |

**User's choice:** RPS + duration + scenario preset, with hard caps.

### Q3: Safe-stop and concurrency

| Option | Description | Selected |
|--------|-------------|----------|
| Concurrency=1 + idempotent stop + auto-expire (Recommended) | SIGTERM graceful drain + duration auto-expire | ✓ |
| Concurrency=1 + hard kill only | Faster stop, loses tail metrics | |
| Concurrency ≥2 + per-run cancel | Confusing parallel signal for workshop | |

**User's choice:** Concurrency=1 + idempotent stop + auto-expire.

### Q4: Audit fields

| Option | Description | Selected |
|--------|-------------|----------|
| Full MELTS-shaped audit event (Recommended) | trace_id, span_id, run_id, admin_user, role, RPS, duration, status, etc. | ✓ |
| Lightweight audit only | Breaks "every demo action is traceable" core value | |

**User's choice:** Full MELTS-shaped audit event.

---

## Observability Narrative Depth

### Q1: APM saved queries

| Option | Description | Selected |
|--------|-------------|----------|
| Pod-count-over-time (shop, java-apm) (Recommended) | Group by k8s.pod.name + service.name | ✓ |
| Latency percentiles during scale event (Recommended) | p50/p95/p99 bucketed by 30s | ✓ |
| Trace propagation to new pods (Recommended) | Filter spans where pod first appeared inside stress window | ✓ |
| Error / saturation spikes + slow-span distribution | Combined: top-N errors + histogram | ✓ |

**User's choice:** All four.
**Notes (verbatim from user):** "Make sure you use the latest OTEL telelmety and LLMtry. I plan to have added later oci-coordinator-oke as an external project, and I want to have the app metrics and traces in OCI APM, and use drill downs to redirect to lm.octodemo.cloud, phoenix.octodemo.cloud, openlit.octodemo,cloud and grafana.octodemo.cloud"

This added three things to scope:
1. Pin OTel + LLMetry to latest stable (D-21).
2. APM/dashboard drilldown links to lm/phoenix/openlit/grafana.octodemo.cloud (D-20).
3. Future-hook awareness for oci-coordinator-oke (deferred, not implemented here).

### Q2: OCI Monitoring metrics + alarms

| Option | Description | Selected |
|--------|-------------|----------|
| Scaling-narrative metrics + 2 alarms (Recommended) | New gauges + counters under octo_apm_demo; CPU saturation alarm + HPA-at-max alarm | ✓ |
| Metrics only, no alarms | Loses "alarm fired" moment | |
| Reuse existing metrics only | Weakest narrative | |

**User's choice:** Scaling-narrative metrics + 2 alarms.

### Q3: Log Analytics

| Option | Description | Selected |
|--------|-------------|----------|
| Scaling timeline dashboard + 4 saved searches (Recommended) | New dashboard "OKE Autoscaling Timeline" with HPA / CA / kubelet / stress audit | ✓ |
| Saved searches only (no dashboard) | Less polish, faster | |
| Single "scaling event" saved search | Minimum viable | |

**User's choice:** Scaling timeline dashboard + 4 saved searches.

### Q4: Workshop Lab 11

| Option | Description | Selected |
|--------|-------------|----------|
| Full walk-through, cross-links to Labs 1/5/9 (Recommended) | 7-step demo: baseline → trigger → HPA → CA → APM → Logan → cool-down | ✓ |
| Compact Lab 11 (trigger + observe APM only) | Skips Logan + alarms | |
| Two labs: 11 (HPA) + 12 (Cluster Autoscaler) | Splits node and pod scaling | |

**User's choice:** Full walk-through, cross-links to Labs 1/5/9.

---

## Claude's Discretion

- Exact HPA `stabilizationWindowSeconds` and `behavior` policies.
- Helm vs raw YAML split for the new k6 wrapper Deployment.
- Wrapper FastAPI internals beyond the public `/api/admin/stress/*` contract.
- Test layout (extend `tests/test_unified_deploy_surface.py` vs add `tests/test_stress_demo_surface.py`).

## Deferred Ideas

- `oci-coordinator-oke` as an external project — leave APM hooks only, no implementation.
- Lab 12 (split Cluster Autoscaler into its own lab).
- Power-user custom k6 script upload mode.
- Live `kubectl apply` of the custom-metrics adapter (operator-gated).
- Live LB header-based routing rule apply (operator-gated).
- CRM and Workflow Gateway HPAs (untouched in v1.1).
- Deeper RUM-side stress correlation tiles.
