# Phase 4: Deployment Parity and Release Gates - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning
**Source:** GSD autonomous smart-discuss fallback, roadmap, deployment surfaces, and existing Phase 1-3 signal contracts

<domain>
## Phase Boundary

Phase 4 aligns VM/Compute, raw OKE, Helm, container, and local validation
paths so the same OCTO demo application contract can be promoted without
runtime drift. The work is source-level and offline-safe: no Terraform apply,
no Kubernetes apply, no Load Balancer rewiring, and no OCI mutations.

This phase covers `DEPLOY-01`, `DEPLOY-02`, `DEPLOY-03`, and `DEPLOY-04`.
</domain>

<decisions>
## Implementation Decisions

### Source Parity First
- Treat raw OKE manifests, Compute runtime templates, Helm templates, and
  release readiness docs as deployment source of truth.
- Encode parity as local tests so drift is caught before a live rollout.

### Helm Must Match Raw OKE
- The Helm path is an operator-supported deployment path, so it must expose
  the same observability, payment simulation, Java sidecar, GenAI, and
  Langfuse hooks as the raw OKE manifests.
- Java payment gateway stays internal and uses the OKE-specific service name
  `octo-java-app-server-oke`.

### Non-Destructive Validation
- Shared emdemo resources remain live. Validation can render, lint, dry-run,
  and document promotion gates, but live LB route changes and OCI updates stay
  manual operator actions.

### the agent's Discretion
- The executor may add focused tests, Helm template updates, and docs where
  they prevent VM/OKE/Helm deployment drift.
</decisions>

<code_context>
## Existing Code Insights

### Deployment Surfaces
- Raw OKE manifests under `deploy/k8s/oke/` already define Shop, CRM, and Java
  payment gateway runtime contracts with `SERVICE_NAMESPACE`, pod identity,
  `OTEL_RESOURCE_ATTRIBUTES`, APM, Logging, Monitoring, Select AI, Langfuse,
  and payment simulation variables.
- Compute uses `deploy/compute/runtime.env.template`, `app-compose.yml`, and
  systemd units to run Shop/CRM plus optional Java and Workflow Gateway
  sidecars.
- Helm under `deploy/helm/octo-apm-demo/` was behind the raw OKE manifests and
  needed contract parity hardening.

### Validation Surfaces
- `tests/test_unified_deploy_surface.py` already covers broad deployment
  safety, DNS defaults, OKE helper safety, Resource Manager packaging, and
  Compute offline validation.
- `deploy/verify.sh` is the canonical broad offline deploy validator.
- `site/operations/deploy-readiness.md` is the operator-facing release gate.
</code_context>

<specifics>
## Specific Ideas

- Add deployment parity tests for Helm observability variables, Java payment
  gateway rendering, and release readiness documentation.
- Add Java payment gateway support to the Helm chart.
- Update Helm Shop/CRM templates with the OKE MELTS resource contract.
- Document non-destructive OKE/ONM dry-run checks and round-robin rollback
  gates.
</specifics>

<deferred>
## Deferred Ideas

- Live emdemo VM/OKE smoke, APM Trace Explorer checks, Log Analytics real-log
  checks, and public LB round-robin validation require an approved operator
  window and current OCI credentials.
</deferred>
