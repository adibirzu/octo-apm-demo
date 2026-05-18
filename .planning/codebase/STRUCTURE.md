# Codebase Structure

Generated: 2026-05-14

## Top-Level Layout

- `shop/` - Drone Shop FastAPI app, templates, checkout/payment modules,
  observability code, tests, Playwright package, docs, and shop-specific deploy
  helpers.
- `crm/` - Enterprise CRM/Admin FastAPI app, templates, coordinator/admin
  modules, observability code, order sync, tests, and CRM docs.
- `services/apm-java-demo/` - Java/Spring Boot sidecar for payment app-server
  evidence and Java APM spans/logs.
- `services/` - Additional demo services: async worker, load control, browser
  runner, cache, edge fuzz, object pipeline, remediator, OTel gateway, VM lab,
  and container lab.
- `deploy/` - Unified deployment surface for OCI, OKE, VM, Compute, Helm,
  Resource Manager, Terraform, local-stack, Log Analytics, and verification.
- `site/` - MkDocs content, architecture pages, diagrams, operations docs,
  observability docs, and workshop guides.
- `tests/` - Root-level deployment, integration, and E2E test surfaces.
- `tools/` - Traffic generator, rollout validators, workshop helpers, and
  saved-search tooling.
- `skills/` - Project-specific skills such as private demo observability triage.
- `.planning/` - GSD config, project context, requirements, roadmap, state, and
  codebase map.

## High-Value App Paths

- `shop/server/modules/payments/` - payment provider and gateway simulation.
- `shop/server/modules/java_app_server.py` - Java sidecar client and trace
  enrichment.
- `shop/server/observability/` - tracing, logging, monitoring, workflow, and
  purchase journey helpers.
- `crm/server/modules/admin.py` - Admin endpoints and operational workflows.
- `crm/server/modules/coordinator.py` - Admin-only OCI Coordinator surface.
- `crm/server/observability/` - CRM telemetry, logging, metrics, and security
  helpers.
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/` - Java payment and
  OTel support code.

## High-Value Deployment Paths

- `deploy/compute/` - private Compute stack, runtime env rendering, install,
  deployment, validation, and systemd units.
- `deploy/k8s/oke/` - raw OKE manifests for Shop, CRM, Java, and common
  resources.
- `deploy/oke/` - emdemo OKE helper scripts for cluster, images, secrets,
  monitoring, and load-balancer backends.
- `deploy/helm/octo-apm-demo/` - Helm chart for existing OKE clusters.
- `deploy/oci/log_analytics/` - fields, parsers, saved searches, dashboards,
  rule deployment, and verification helpers.
- `deploy/oci/apm/` - APM saved-query/drilldown assets.
- `deploy/terraform/` and `deploy/resource-manager/` - OCI resource modules and
  packaged stack flows.

## Generated or Sensitive Areas

- `build/`, `output/`, `.pytest_cache/`, Playwright reports, and local test
  output are generated.
- `credentials/`, wallets, env files, tfvars, resolved outputs, and local
  operator notes are sensitive and should not be included in public docs.
