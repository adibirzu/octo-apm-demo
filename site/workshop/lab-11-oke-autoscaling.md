# Lab 11 — OKE Autoscaling and Stress Demo

Walk the full Phase 7 elasticity demo end-to-end: baseline → trigger →
HPA → Cluster Autoscaler → alarm → APM / Log Analytics drilldown →
cool-down. One workshop attendee can reproduce solo in ~15 minutes.

## Objective

This lab is the closing chapter of the OCTO APM workshop. You will
drive a controlled stress run against `shop.${DNS_DOMAIN}` from the
admin-only `/admin/stress-test` page, watch OKE's HPA add shop pods,
watch the managed Cluster Autoscaler add a worker node, watch the
saturation alarm fire and clear, and drill into the resulting signals
across **three observability channels — APM, Monitoring,
Log Analytics — all keyed by the same `run_id`**. The same `run_id`
pivot you used in [Lab 09](lab-09-chaos-drill.md) for chaos
correlation is reused here for stress correlation; the contract is
identical (Phase 5 audit-event shape; OBS-02 parser).

You will also visit the four external operator-owned drilldown
surfaces (D-20): `lm.octodemo.cloud`, `phoenix.octodemo.cloud`,
`openlit.octodemo.cloud`, `grafana.octodemo.cloud`.

## Time budget

~15 minutes.

!!! warning "Live demo prerequisite"
    Steps 2 → 7 below mutate live OKE state — they trigger real load
    against `shop.${DNS_DOMAIN}` and rely on operator-applied
    prerequisites. **If you are reading this in workshop preview
    mode** (no operator window applied), treat steps 2 → 7 as a
    read-only walkthrough. The operator-gated prerequisites are
    flagged in the next section.

## Prerequisites

| Prerequisite | Where it lives | Operator-gated? |
|---|---|---|
| [Lab 01 — First trace](lab-01-first-trace.md) completed | workshop | no |
| [Lab 05 — Metric + alarm](lab-05-metric-and-alarm.md) completed | workshop | no |
| [Lab 09 — Chaos drill](lab-09-chaos-drill.md) completed | workshop | no |
| Cluster Autoscaler add-on applied | `deploy/oke/configure-cluster-autoscaler.sh` (plan 07-02) | **yes — operator window** |
| `prometheus-adapter` Helm release installed | `deploy/helm/prometheus-adapter/` (plan 07-02) | **yes — operator window** |
| LB header-routing rule for `X-Octo-Stress-Target: oke` | [stress-demo-lb-routing.md](../operations/stress-demo-lb-routing.md) | **yes — operator window** |
| `stress-runner` Helm release with `stressRunner.enabled=true` | Helm values (plan 07-03) | **yes — operator window** |
| Admin role: `stress-operator` on your workshop user | CRM admin module (plan 07-05) | yes (admin grant) |

If any of the four operator-gated rows is missing, the live run will
either return HTTP 409 (concurrency=1 enforcement before the
operator window opens) or the alarm path / drilldown queries will
return empty. Ask your workshop lead to confirm operator window
status before continuing.

## Steps

### 1. Verify baseline (60s)

Confirm the cluster is at rest before you start:

```bash
kubectl -n octo-drone-shop get deploy octo-drone-shop \
    -o jsonpath='{.status.replicas} replicas / {.status.readyReplicas} ready' \
    && echo
kubectl get nodes --selector='node.kubernetes.io/instance-type' \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | wc -l
```

Expected: `2 replicas / 2 ready`, and `2` worker nodes. Cross-check in
the OCI Console → Developer Services → Kubernetes Clusters →
`octo-apm-demo-oke` → Workloads → Pods.

### 2. Trigger the Medium preset (3 min)

Open the admin stress-test page on the admin host:

```text
https://admin.${DNS_DOMAIN}/admin/stress-test
```

You will see the audit banner (`Stress runs are audited end-to-end
via run_id`), a preset selector, the duration / RPS fields, the
scenario dropdown, and the `Apply stress run` button. The current
state panel shows `idle`.

Pick **Medium (50 RPS / 3 min, `checkout_journey`)**, leave the
target as `shop`, click **Apply stress run**. The page returns:

```json
{
  "status": "started",
  "run_id": "1f2e8a90-...",
  "rps_requested": 50,
  "duration_requested": 180,
  "scenario": "checkout_journey",
  "target_service": "shop"
}
```

**Save the `run_id`** — it's the cross-channel pivot for steps 4–6.

### 3. Watch HPA add pods (1–2 min)

The Phase 7 HPA on `octo-drone-shop` targets CPU 60 / memory 70 /
RPS 30 per pod with `maxReplicas: 10` (plan 07-01). The Medium preset
is calibrated to drive shop to ~6 replicas — leaving 10 as headroom
for the Heavy (120 RPS) preset.

```bash
kubectl -n octo-drone-shop get hpa octo-drone-shop -w
```

In parallel, run the APM saved query `octo-oke-pod-count`:

```text
attributes."run_id" = '<your_run_id>'
| stats distinct_count(attributes."k8s.pod.name") by bin(time, 60s)
```

Expected: 2 → ~6 pods within 60s. The OCI Console pod list updates
in real time.

### 4. Watch Cluster Autoscaler add a node + alarm fire (1–3 min)

While shop scales up, the new pods exceed the two-node CPU budget.
The OKE managed Cluster Autoscaler add-on (D-04, `min=2 max=4` per
plan 07-02) adds a worker node:

```bash
kubectl get nodes -w
```

The OCI Monitoring alarm **`OCTO — Shop CPU saturation high`**
(plan 07-08, `shop_cpu_saturation_pct > 80 for 2m`) will fire. This
is **expected** — the alarm doubles as alarm-path validation
(D-18, identical to the Lab 05 alarm pattern). You should also see
**`OCTO — HPA at max replicas`** stay `OK` (we are calibrated below
the ceiling).

### 5. Drill into APM (2 min)

Open APM Trace Explorer (and link out to
[`phoenix.octodemo.cloud`](https://phoenix.octodemo.cloud) for the
external trace-store view, if your tenancy has it configured).

Run the four Phase 7 APM saved queries (plan 07-07), all scoped to
your `run_id`:

| Saved query | What it shows |
|---|---|
| `octo-oke-pod-count` | shop replica count over time, bucketed 60s |
| `octo-oke-latency-percentiles` | `/api/shop/checkout` p50/p95/p99 across the stress window |
| `octo-oke-trace-to-new-pods` | traces whose `k8s.pod.name` first appears inside the window — proof HPA pods serve real traffic |
| `octo-oke-error-saturation` | top-N pods by `5xx` / `span.status=ERROR` + slow-span histogram (stress vs baseline) |

The "trace to new pods" query is the one workshop attendees
remember: it visually proves that the autoscaled-in pods accept
production traffic mid-run.

### 6. Drill into Log Analytics (2 min)

Open Log Analytics → Dashboards → **OKE Autoscaling Timeline**
(plan 07-09). The four saved searches are time-aligned with the
APM window:

1. **HPA scale events** — `Source = 'Kubernetes Logs' and
   Subsystem = 'hpa-controller'`
2. **Cluster Autoscaler events** — managed add-on logs + cluster-
   autoscaler events
3. **Kubelet pressure** — `NodeNotReady`, `ImagePullBackOff`,
   `OOMKilled` (should be empty under Medium preset; non-empty under
   Heavy)
4. **Stress run audit log** — `Source = 'octo-stress-audit'` filtered
   to your `run_id` — exactly the same shape as the chaos audit log
   you used in Lab 09

Filter the whole dashboard by `run_id = <your_run_id>` and the four
panels align on the same minute boundary.

### 7. Cool-down (5 min)

The Medium preset auto-expires after 3 minutes (server-side hard
timeout = `duration + 30s` per D-14). If you need to stop sooner,
click **Stop stress run** on the admin page — it idempotently sends
SIGTERM to the in-pod `k6` process and emits a `stopped` audit
event.

Watch the scale-down:

```bash
kubectl -n octo-drone-shop get hpa octo-drone-shop -w
kubectl get nodes -w
```

The HPA scale-down `stabilizationWindowSeconds` is 300 (5 min, plan
07-01) — that is intentional, so attendees see a steady, non-flappy
descent. Within 5 minutes you should be back at 2 shop pods and
2 nodes. The CPU-saturation alarm clears automatically.

## External drilldown surfaces (D-20)

While the live run is in flight, the same `run_id` is propagated to
four operator-owned external surfaces:

- **[lm.octodemo.cloud](https://lm.octodemo.cloud)** — Langfuse /
  LLMetry external view. Use when you want to see LLM/agent-side
  traces correlated with the stress window (the shop's AI assistant
  emits LLMetry spans).
- **[phoenix.octodemo.cloud](https://phoenix.octodemo.cloud)** —
  Arize Phoenix external trace store. Use when you want a second
  perspective on traces alongside APM Trace Explorer — Phoenix
  bucketing is different.
- **[openlit.octodemo.cloud](https://openlit.octodemo.cloud)** —
  OpenLIT external dashboard. Use when you want to inspect token /
  cost / model-side metrics for LLM calls inside the stress run.
- **[grafana.octodemo.cloud](https://grafana.octodemo.cloud)** —
  Grafana external dashboards. Use when you want to overlay the
  Phase 7 RPS / pod-count metrics on top of standard
  cluster-autoscaler Grafana panels (`cluster-autoscaler`
  dashboard, panel `nodes-added-removed`).

These hosts are external operator surfaces. Phase 7 only emits the
contextual `run_id` and saved-query / dashboard tile links; it does
not bundle the surfaces themselves.

## Verify

```bash
./tools/workshop/verify-11.sh "$RUN_ID"
```

Expected:

```text
✓ stress run 'checkout_journey' was applied (audit log row exists)
✓ APM has ≥ 5 traces tagged with run_id during the window
✓ HPA scaled shop above 2 replicas during the window
✓ CPU-saturation alarm transitioned OK→FIRING→OK during the window
✓ Cluster Autoscaler add-event observed during the window
✓ stress run cleared / expired within (duration + 30s)
PASS — Lab 11 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/admin/stress-test` returns HTTP 403 | Missing `stress-operator` role on your user | Ask workshop lead to grant the role (Phase 5 admin module) |
| `Apply stress run` returns HTTP 409 | Another stress run is already active (concurrency=1, D-14) | Wait for it to expire, or click **Stop stress run** first |
| HPA never scales beyond 2 | `prometheus-adapter` not installed → External `shop_request_rate` metric is unavailable | Confirm operator window applied the adapter (plan 07-02) |
| Cluster Autoscaler does not add a node | Add-on not enabled, or node pool already at `max=4` | Re-run `configure-cluster-autoscaler.sh --dry-run` to confirm config |
| Saturation alarm does not fire | OCI Monitoring custom-metrics emitter not publishing | Check `shop/server/observability/oci_monitoring.py` is wired (Phase 7 plan 07-08) |
| Stop button does nothing | `stress-runner` pod was rescheduled mid-run; the lock is gone | Re-issue **Stop stress run** — it is idempotent (D-14) |
| Pods stuck in `ImagePullBackOff` after scale-up | OCIR pull secret missing on the new namespace | Re-run `deploy/oke/bootstrap-emdemo-secrets.sh` |

## Read more

- [Lab 01 — First trace](lab-01-first-trace.md) — the trace primitive
  that every step here builds on.
- [Lab 05 — Custom metric + alarm](lab-05-metric-and-alarm.md) — the
  alarm pattern reused in step 4.
- [Lab 09 — Chaos drill](lab-09-chaos-drill.md) — the `run_id` pivot
  pattern (chaos → stress, identical contract).
- [Operations → Stress demo LB routing](../operations/stress-demo-lb-routing.md)
  — the operator runbook for the D-09 header-routing rule.
- [Observability → MELTS overview](../observability/melts.md)
- [Operations → Alarms & Health](../operations/alarms.md)

---

[← Lab 10](lab-10-failed-checkout.md)
