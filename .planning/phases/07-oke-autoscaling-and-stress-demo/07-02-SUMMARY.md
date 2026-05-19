---
phase: 07-oke-autoscaling-and-stress-demo
plan: 02
subsystem: deploy/oke (Cluster Autoscaler) + deploy/helm/.../charts (prometheus-adapter values)
tags: [oke, cluster-autoscaler, prometheus-adapter, scripts, external-metrics, d-04, d-02]
dependency_graph:
  requires:
    - deploy/oke/install-oci-kubernetes-monitoring.sh (script pattern analog)
    - deploy/k8s/oke/shop/deployment.yaml (shop HPA External metric ref — Plan 07-01)
    - deploy/k8s/oke/apm-java-demo/deployment.yaml (java HPA External metric ref — Plan 07-01)
    - deploy/helm/octo-apm-demo/templates/shop-hpa.yaml (gated External block — Plan 07-01)
    - deploy/helm/octo-apm-demo/templates/java-gateway-hpa.yaml (gated External block — Plan 07-01)
  provides:
    - deploy/oke/configure-cluster-autoscaler.sh — idempotent dry-run-by-default
      operator wrapper around oci ce cluster install-addon|update-addon
    - deploy/oke/cluster-autoscaler-config.json — CA add-on config (nodes 2:4 +
      OKE_NODE_POOL_OCID envsubst placeholder, scale-down delays, balance flag)
    - deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml — values
      file that publishes shop_request_rate + java_request_rate to HPA via
      External Metrics API
  affects:
    - Plan 07-04+ (operator window apply: kubectl install of CA add-on +
      helm install of prometheus-adapter using these artifacts unchanged)
tech_stack:
  added:
    - OCI Cluster Autoscaler managed add-on (config-driven, envsubst-rendered)
    - prometheus-community/prometheus-adapter (External Metrics rules)
    - envsubst-based JSON config rendering (no live OCIDs committed)
  patterns:
    - dry-run-by-default operator script (APPLY=false opposite of monitoring analog)
    - read -p confirmation gate forcing operator to type cluster name
    - envsubst placeholder for OKE_NODE_POOL_OCID (SEC-04 / KB-456 compliance)
    - list-addons precheck → install-addon vs update-addon switch (idempotent)
key_files:
  created:
    - deploy/oke/configure-cluster-autoscaler.sh
    - deploy/oke/cluster-autoscaler-config.json
    - deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml
  modified:
    - tests/test_stress_demo_surface.py (appended 8 Plan 07-02 tests)
decisions:
  - "APPLY defaults to false (dry-run). Monitoring analog defaults to APPLY=true
    because the chart is non-destructive (helm upgrade is idempotent); the CA
    add-on, in contrast, mutates worker node pool autoscaling bounds and is
    safer when explicitly opted into."
  - "Idempotent install/update via `oci ce cluster list-addons` precheck —
    detect presence of ClusterAutoscaler addon-name and switch CLI verb."
  - "Required env COMPARTMENT_ID + OKE_NODE_POOL_OCID hard-fail at start so a
    misconfigured operator cannot accidentally render the JSON with literal
    envsubst placeholders pointing at the wrong pool."
  - "envsubst (not jq edits, not python templating) keeps the rendered config
    auditable as a plain JSON diff and ensures no live OCID is ever read from
    the committed file (SEC-04, KB-456)."
  - "prometheus-adapter rules use seriesQuery + name.matches/as pattern from
    the upstream chart docs; metricsQuery uses `sum(rate(...)) by (pod)` to
    match the HPA per-pod target (averageValue) shape from Plan 07-01."
  - "namespaceOverride: octo-autoscaling colocates the adapter with Cluster
    Autoscaler so the External Metrics path is administratively one namespace."
  - "rules.default=false; we only publish the two metrics HPA needs. Avoids
    polluting the External Metrics API with unused rule families."
metrics:
  duration_minutes: 4
  completed_date: "2026-05-18T17:27:00Z"
---

# Phase 7 Plan 02: Cluster Autoscaler + prometheus-adapter — Summary

Three new artifacts under `deploy/oke/` and `deploy/helm/octo-apm-demo/charts/`
that hand the operator a review-then-apply window: an idempotent
dry-run-by-default Cluster Autoscaler wrapper script, its JSON config (with
an envsubst placeholder for the node pool OCID — no live OCIDs committed),
and a prometheus-adapter Helm values file that exposes `shop_request_rate`
and `java_request_rate` as External Metrics that the HPAs already added in
Plan 07-01 consume when `.Values.shop.autoscaling.rps.enabled=true`.

## What landed

| Task | Outcome | Commit |
|------|---------|--------|
| 1. RED tests (8 assertions) | Appended 8 failing tests to `tests/test_stress_demo_surface.py`: script exists+executable, APPLY=false dry-run default, install-addon AND update-addon branches, read -p confirm, list-addons precheck, reads config JSON, CA config has min=2 max=4 + envsubst placeholder + parses as JSON, adapter values declare both External rules in octo_apm_demo namespace. | `fa0222f` |
| 2. configure-cluster-autoscaler.sh + cluster-autoscaler-config.json | New 192-line bash wrapper following the install-oci-kubernetes-monitoring.sh pattern (shebang, set -euo pipefail, usage HEREDOC, tool checks, context guard) with APPLY=false default, list-addons precheck, envsubst-rendered tmp JSON, dry-run echo of the resolved `oci ce cluster install-addon|update-addon ... --from-json file://...` command, and a read -p confirm gate before live apply. JSON config has nodes=2:4:${OKE_NODE_POOL_OCID} + scaleDownDelayAfterAdd=10m + scaleDownUnneededTime=10m + maxNodeProvisionTime=15m + balanceSimilarNodeGroups=true. | `076d2a2` |
| 3. prometheus-adapter-values.yaml | New 86-line Helm values file under `deploy/helm/octo-apm-demo/charts/`. Two `rules.external` entries — `shop_request_rate` and `java_request_rate` — each mapping a `sum(rate(http_server_requests_seconds_count{service=...,namespace="octo_apm_demo"}[1m])) by (pod)` query to the External Metrics API. namespaceOverride=octo-autoscaling colocates with CA. prometheus.url is a placeholder reviewed at apply time. | `0816897` |

## Verification

- `pytest tests/test_stress_demo_surface.py` — 22/22 PASS (8 new + 14 Plan 07-01)
- `pytest tests/test_stress_demo_surface.py -k "cluster_autoscaler or prometheus_adapter"` — 8/8 PASS
- `bash -n deploy/oke/configure-cluster-autoscaler.sh` — exits 0
- `deploy/oke/configure-cluster-autoscaler.sh --help` — exits 0, prints usage with required env vars
- `python -c "import json; json.load(open('deploy/oke/cluster-autoscaler-config.json'))"` — exits 0, addonName=ClusterAutoscaler
- `python -c "import yaml; list(yaml.safe_load_all(open('deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml')))"` — 1 doc, top keys = prometheus, namespaceOverride, resources, rules
- `grep -cE '([0-9]{1,3}\.){3}[0-9]{1,3}' deploy/oke/cluster-autoscaler-config.json deploy/oke/configure-cluster-autoscaler.sh deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml` — 0 / 0 / 0 (no leaked IPs)
- `os.access('deploy/oke/configure-cluster-autoscaler.sh', os.X_OK)` — True (chmod +x persisted)

## Threat Model Outcomes

| Threat ID | Disposition | Evidence |
|-----------|-------------|----------|
| T-07-05 (Tampering: accidental --apply) | mitigated | `: "${APPLY:=false}"` (verified by `test_configure_cluster_autoscaler_dry_run_default`); `read -p "Type the cluster name '${OKE_CLUSTER_NAME}' to confirm apply: " CONFIRM` blocks accidental writes |
| T-07-06 (Info disclosure: committed OCIDs) | mitigated | `${OKE_NODE_POOL_OCID}` envsubst placeholder; hard-fail at script start if env var unset; `grep -cE '([0-9]{1,3}\.){3}[0-9]{1,3}'` returns 0 across all committed files |
| T-07-07 (DoS: over-scale) | accepted | min=2 max=4 in JSON config matches D-04 explicit; OCI node pool quota enforces hard cap independently of CA config |
| T-07-08 (EoP: admin profile needed) | mitigated | `OCI_PROFILE:=emdemo` documented in usage; require_tool oci/jq/kubectl/envsubst at start; SKIP_CONTEXT_CHECK guard ensures correct cluster context unless explicitly bypassed |
| T-07-09 (Repudiation) | mitigated | `oci ce cluster install-addon|update-addon` events flow to OCI audit log natively; confirm prompt creates a per-apply tty record |

## Deviations from Plan

None — plan executed exactly as written.

### Auto-fixed Issues

None.

### Architectural Changes

None.

## TDD Gate Compliance

- RED gate commit (`test(07-02): ...`): `fa0222f` — 8 failing tests after RED scaffold.
- GREEN gate commits (`feat(07-02): ...`): `076d2a2` (CA script + JSON), `0816897` (adapter values) — drove all 8 failing tests to PASS.
- REFACTOR gate: not needed; edits were targeted and additive.

## Known Stubs

None. The prometheus-adapter `prometheus.url` is a placeholder commented as
"reviewed at apply time" — that is by design per CONTEXT.md `<deferred>`
(live helm install gated to the same operator window as
`configure-cluster-autoscaler.sh --apply`). The placeholder URL pattern
follows the upstream chart's documented values shape and is functional once
the operator confirms or substitutes the actual Prometheus service FQDN at
apply time.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries were
introduced beyond those already documented in the plan threat model.

## Self-Check: PASSED

| Artifact | Status |
|----------|--------|
| `deploy/oke/configure-cluster-autoscaler.sh` | FOUND (executable) |
| `deploy/oke/cluster-autoscaler-config.json` | FOUND (valid JSON, addonName=ClusterAutoscaler) |
| `deploy/helm/octo-apm-demo/charts/prometheus-adapter-values.yaml` | FOUND (valid YAML, 4 top-level keys) |
| `tests/test_stress_demo_surface.py` | MODIFIED (22 tests total, 8 new) |
| `.planning/phases/07-oke-autoscaling-and-stress-demo/07-02-SUMMARY.md` | FOUND |
| commit `fa0222f` (RED tests) | FOUND |
| commit `076d2a2` (CA script + JSON) | FOUND |
| commit `0816897` (adapter values) | FOUND |
