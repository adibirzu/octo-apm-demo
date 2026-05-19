# OCI APM saved queries — Phase 7 OKE Autoscaling Narrative

Reproducible, version-controlled APM saved queries that an operator
imports during the Phase 7 stress-demo window. Together these queries
tell the scale-up / scale-down story for the `octo-drone-shop` and
`octo-apm-java-demo` workloads — pod count, latency percentiles, trace
propagation into newly-added pods, and error/saturation top-N.

Every query is scoped to the `octo_apm_demo` service namespace per the
Phase 1 OBS-05 contract.

## Files

| File | D-16 # | Widget | Purpose |
|---|---|---|---|
| `oke-pod-count-over-time.json` | 1 | LINE_CHART | Distinct pod count per service, bucketed 1min — visual of HPA scale-out/in. |
| `oke-latency-percentiles-during-scale.json` | 2 | LINE_CHART | p50/p95/p99 for `/api/shop/checkout` + Java payment gateway, bucketed 30s. |
| `oke-trace-propagation-new-pods.json` | 3 | TABLE | Traces hitting `k8s.pod.name` values not in the operator-supplied baseline set. |
| `oke-error-saturation-slow-spans.json` | 4 | BAR_CHART | Top-N pods by errored / slow spans during the stress window. |
| `apply.sh` | — | — | Operator-gated apply script — dry-run by default. |

## Drilldown links (D-20)

Every saved-query JSON carries an `external_drilldowns` array pointing
to the operator-owned external observability surfaces:

| Host | Tool |
|---|---|
| `lm.octodemo.cloud` | Langfuse / LLMetry |
| `phoenix.octodemo.cloud` | Arize Phoenix |
| `openlit.octodemo.cloud` | OpenLIT |
| `grafana.octodemo.cloud` | Grafana |

When importing these queries into APM, configure the widget drilldown
to surface the matching `external_drilldowns[*].url` from the saved
query metadata. Phase 7 only ships the link metadata — wiring the APM
widget drilldown UI happens during the operator apply window.

## Apply

`apply.sh` is **dry-run by default**. The default flow lists what would
be applied, scoped to the OCTO compartment, with no mutation:

```bash
COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
  ./tools/apm-saved-queries/apply.sh
```

To actually mutate APM, set `APPLY=true` AND answer the confirm prompt:

```bash
APPLY=true \
COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
APM_DOMAIN_ID="<OCTO_APM_DOMAIN_OCID>" \
  ./tools/apm-saved-queries/apply.sh
```

Environment variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `COMPARTMENT_ID` | yes | — | OCTO compartment OCID. |
| `APM_DOMAIN_ID` | yes when `APPLY=true` | — | Target APM domain OCID. |
| `OCI_PROFILE` | no | `emdemo` | OCI CLI profile name. |
| `APPLY` | no | `false` | Set to `true` to actually mutate. |

### `oci apm-traces` subcommand caveat

The exact OCI CLI subcommand for APM saved-query mutation (e.g.
`oci apm-traces saved-search create-or-update`) varies across CLI
versions. If `apply.sh` reports an unknown subcommand, fall back to
manual import via the OCI Console:

1. Open **OCI Console → Observability & Management → APM → Traces**.
2. Open **Trace Explorer**.
3. For each `*.json` file: copy the `queryString` into the query bar,
   run it, then click **Save** and set the name + description to match
   the JSON.
4. In each widget, add a drilldown action for each
   `external_drilldowns[*]` entry.

## First-appearance window logic (trace-to-new-pods)

The `oke-trace-propagation-new-pods.json` query takes a parameter
`baseline_pod_set` — a comma-separated list of pod names that existed
**before** the stress run starts. The operator fills this at apply
time, e.g.:

```bash
kubectl get pods -n shop -l app=octo-drone-shop \
  -o jsonpath='{.items[*].metadata.name}' | tr ' ' ','
```

After the stress run starts and HPA scales out, the query returns
traces touching any pod NOT in that baseline list — i.e. the
newly-scheduled HPA pods. The `first_appear` column shows the earliest
timestamp the trace touched the new pod.

## Notes on APM query syntax

The exact OCI APM filter-language syntax may evolve across APM
versions. The query strings in these JSON files are illustrative of the
shape; the operator tunes exact tokenization (e.g. `bucket(1min)` vs
`bin(1min)`, `head limit = 50` vs `head 50`) during the live apply
window. The structural fields (`name`, `displayName`, `queryString`,
`widgetType`, `external_drilldowns`) are stable.

## Phase 7 cross-links

- Plan 07-01 — HPA expansion for shop + java-apm (D-01..D-05).
- Plan 07-02 — Cluster Autoscaler + prometheus-adapter.
- Plan 07-03 — `octo-stress-runner` Deployment.
- Plan 07-04 — `_admin_host` extraction.
- Plan 07-05 — admin `/admin/stress-test` UI + API.
- Plan 07-06 — OCI Monitoring metrics + alarms (D-17, D-18).
- **Plan 07-07 (this) — APM saved queries (D-16, D-20).**
