# Phase 7 — OCI Monitoring Alarms

Two OCI Monitoring alarm specs that close the alarm path on the Phase 7
scale narrative. Both alarms query the `octo_apm_demo` metric namespace
exclusively (Phase 1 OBS-05) and reference the D-17 metrics published by
`shop/server/observability/oci_monitoring.py` (plan 07-05).

## Files

| File | Severity | Pending | Threshold | Purpose |
|------|----------|---------|-----------|---------|
| `octo-high-cpu-saturation.json` | WARNING | `PT2M` | `shop_cpu_saturation_pct > 80` | D-18 #1 — alarm-path validation; expected to fire on every stress run. |
| `octo-hpa-at-max-replicas.json` | CRITICAL | `PT5M` | `shop_pod_count >= 10` | D-18 #2 — HPA stuck at maxReplicas (capacity ceiling reached). |

The `10` threshold on the second alarm **MUST** match
`shop.autoscaling.maxReplicas` in `deploy/helm/octo-apm-demo/values.yaml`.
A cross-file invariant test
(`tests/test_stress_demo_surface.py::test_hpa_max_replicas_value_matches_helm_values`)
guards this.

## How `apply.sh` Works

`apply.sh` is dry-run by default. It iterates `*.json` in this
directory, runs each through `envsubst` to resolve placeholders, and
either prints what would be applied or calls
`oci monitoring alarm create-or-update`.

Even with `APPLY=true`, the script requires an interactive confirm
phrase before any mutation.

### Required environment

| Variable | When required | Purpose |
|----------|---------------|---------|
| `COMPARTMENT_ID` | always | OCTO compartment OCID (target compartment for the alarm) |
| `NOTIFICATION_TOPIC_OCID` | always | OCI Notifications topic OCID to route the alarm |
| `OCI_PROFILE` | optional (default `emdemo`) | OCI CLI profile |
| `APPLY` | optional (default `false`) | set to `true` to mutate |

### Dry-run

```bash
COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
NOTIFICATION_TOPIC_OCID="<NOTIFICATIONS_TOPIC_OCID>" \
  ./tools/monitoring-alarms/apply.sh
```

### Live apply (operator window)

```bash
APPLY=true \
COMPARTMENT_ID="<OCTO_COMPARTMENT_OCID>" \
NOTIFICATION_TOPIC_OCID="<NOTIFICATIONS_TOPIC_OCID>" \
  ./tools/monitoring-alarms/apply.sh
```

The script then prompts `Type 'APPLY' to confirm:` before each mutation.

## Verifying

After a live apply, check **OCI Console → Monitoring → Alarm
Definitions**. The two displayName values are:

- `OCTO — Shop CPU saturation high`
- `OCTO — Shop HPA at maxReplicas`

During Phase 7 stress runs, the CPU-saturation alarm is expected to
fire (alarm-path validation). The HPA-at-maxReplicas alarm should fire
only when stress pressure exceeds the Cluster Autoscaler's available
node capacity.

## Notes

- **No live OCIDs are committed.** All sensitive identifiers are
  `envsubst`-resolved at apply time. A test asserts no OCID-prefix
  substring leaks into this directory.
- The OCI CLI subcommand for alarm upsert is
  `oci monitoring alarm create` (the script detects existing alarms by
  display name and falls back to `update` when found).
