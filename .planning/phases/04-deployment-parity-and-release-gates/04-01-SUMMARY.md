---
phase: 04-deployment-parity-and-release-gates
plan: "01"
subsystem: deployment
tags: [helm, oke, compute, observability, payment-gateway]

requires:
  - Phase 1 signal contract
  - Phase 2 payment journey
provides:
  - Helm OKE observability contract parity
  - Helm Java payment gateway deployment
  - Helm payment and GenAI env parity
affects: [helm, oke, tests, docs]

requirements-completed: [DEPLOY-01, DEPLOY-02]
completed: 2026-05-14
---

# Phase 4 Plan 01: Deployment Surface Parity Summary

## Accomplishments

- Added `tests/test_deployment_parity_release_gates.py`.
- Extended the Helm chart with global OKE observability values:
  `serviceNamespace`, `stackName`, `monitoringNamespace`, `okeClusterName`,
  `ociRegion`, and `environment`.
- Updated Helm Shop and CRM deployments to emit the OKE MELTS resource
  contract with pod identity and `OTEL_RESOURCE_ATTRIBUTES`.
- Added Helm Java payment gateway support through
  `templates/java-gateway-deployment.yaml` and `javaGateway` values.
- Added Helm Shop envs for Java sidecar routing, payment simulation,
  Select AI, OCI GenAI, and Langfuse/LLMetry.
- Updated Helm secret rendering and README coverage for `octo-llmetry` and
  `selectai-profile-name`.

## Files Modified

- `deploy/helm/octo-apm-demo/values.yaml`
- `deploy/helm/octo-apm-demo/templates/_helpers.tpl`
- `deploy/helm/octo-apm-demo/templates/shop-deployment.yaml`
- `deploy/helm/octo-apm-demo/templates/crm-deployment.yaml`
- `deploy/helm/octo-apm-demo/templates/java-gateway-deployment.yaml`
- `deploy/helm/octo-apm-demo/templates/secrets.yaml`
- `deploy/helm/octo-apm-demo/README.md`
- `tests/test_deployment_parity_release_gates.py`

## Verification

- `python3 -m pytest -q tests/test_deployment_parity_release_gates.py` - passed.
- Helm template render, chart-managed secret render, and `helm lint` - passed.

## Notes

No live OKE, OCI, Terraform apply, or Load Balancer changes were made.
