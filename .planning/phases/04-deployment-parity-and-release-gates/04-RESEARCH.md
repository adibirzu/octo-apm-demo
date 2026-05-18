# Phase 4: Deployment Parity and Release Gates - Research

## Deployment Inventory

| Surface | Evidence | Notes |
|---|---|---|
| Raw OKE | `deploy/k8s/oke/shop/deployment.yaml`, `crm/deployment.yaml`, `apm-java-demo/deployment.yaml` | Defines OKE service names, pod identity, Java payment gateway, payment simulation, Select AI, Langfuse, APM, Logging, and Monitoring env vars. |
| OKE deploy script | `deploy/oke/deploy-oke.sh` | Rejects `IMAGE_TAG=latest`, validates context/secrets, server-side dry-runs by default, and avoids public LB changes. |
| OKE monitoring | `deploy/oke/install-oci-kubernetes-monitoring.sh` | Pinned ONM Helm chart, SHA256 validation, `APPLY=false` support, and service-log automation disabled unless explicitly enabled. |
| Compute/VM | `deploy/compute/runtime.env.template`, `app-compose.yml`, systemd units | Runs app containers with the same APM/Logging/Monitoring and sidecar variables. |
| Helm | `deploy/helm/octo-apm-demo/` | Operator drop-in for existing OKE clusters; needed Java payment gateway and MELTS parity work. |
| Release gates | `deploy/verify.sh`, `deploy/compute/validate.sh`, `site/operations/deploy-readiness.md` | Local/offline validation before live promotion. |

## Gaps Found

- Helm Shop/CRM templates lacked pod identity, `SERVICE_NAMESPACE`,
  `SERVICE_INSTANCE_ID`, `DEMO_STACK_NAME`, `OCI_MONITORING_NAMESPACE`, and
  OKE `OTEL_RESOURCE_ATTRIBUTES`.
- Helm did not deploy the Java payment gateway, so the Helm path could miss
  the full checkout payment workflow.
- Helm Shop did not expose `JAVA_APM_SERVICE_URL`, `JAVA_APM_SERVICE_NAME`,
  payment simulation toggles, `SELECTAI_PROFILE_NAME`, or the complete
  Langfuse hook set.
- The deploy readiness guide mentioned broad verification but did not spell
  out the safe `APPLY=false` / `SERVER_DRY_RUN=true` OKE and ONM checks or
  the round-robin rollback gate.

## Validation Strategy

- Add credential-free tests in `tests/test_deployment_parity_release_gates.py`.
- Render and lint the Helm chart locally when `helm` is available.
- Re-run existing deploy, signal-contract, Log Analytics, and docs gates.

## Live Validation Deferred

The following remain manual because they touch live shared state:

- Public VM + OKE round-robin smoke through the shared OCI LB.
- `wire-existing-lb-backends.sh --round-robin-active --apply`.
- APM Trace Explorer confirmation in the emdemo APM domain.
- Log Analytics saved-search execution against current emdemo logs.
