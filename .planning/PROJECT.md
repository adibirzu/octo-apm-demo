# OCTO APM Demo

## What This Is

OCTO APM Demo is a unified demo platform for the Drone Shop storefront, the
Enterprise CRM/Admin portal, the Java payment app-server sidecar, shared ATP,
and OCI observability assets. It is used to show how real user journeys produce
correlated browser actions, traces, logs, metrics, topology, security signals,
database evidence, and GenAI evidence across VM, container, and OKE deployments.

## Core Value

Every demo user action must produce inspectable, correlated OCI observability
evidence across browser, application, payment gateway, Java sidecar, database,
logs, traces, metrics, security, and GenAI where relevant.

## Requirements

### Validated

- Shop checkout, cart, login, and order workflows run against the shared ATP and
  emit trace IDs, order IDs, payment gateway IDs, and user/session pivots.
- Admin/CRM is the operator surface for orders, users, catalog management,
  payment/security simulation, DB cleanup, and OCI Coordinator questions.
- The Java payment sidecar simulates Google Pay, Apple Pay, card authorization,
  Visa/Mastercard processors, decline paths, network routing, and payment
  gateway details without storing real card data.
- VM and OKE deployments share the same image contract, service names,
  environment contract, APM domain, Log Analytics field contract, and public
  load-balancer routing model.
- OCI APM, RUM, Logging, Log Analytics, Monitoring, Kubernetes Monitoring,
  saved searches, dashboards, and detection-rule assets are versioned or
  documented from this repository.

### Active

- [ ] Tighten the MELTS evidence contract so every supported demo flow has
  complete spans, structured logs, metrics, topology labels, security fields,
  and database pivots.
- [ ] Keep VM, OKE, container, and local-stack deployment paths consistent and
  production-ready without breaking the current public load balancer surface.
- [ ] Harden payment-flow simulation so successful and failed purchases show
  complete customer, gateway, processor, Java, backend, and ATP timelines.
- [ ] Improve threat-hunting and Log Analytics rules so dashboards are backed
  by real app, OKE, payment, security, and database logs.
- [ ] Strengthen GenAI/LLMetry/Langfuse/APM instrumentation while keeping OCI
  Coordinator limited to the Admin surface and octo-apm-demo resources.
- [ ] Keep docs, diagrams, runbooks, and GSD planning artifacts aligned with the
  actual implementation and the current emdemo deployment.

### Out of Scope

- Real payment processing - all rails are simulated and must remain token-safe.
- Exposing backend or operator implementation details on customer-facing shop
  pages - the storefront should read as a fake demo shop.
- Publishing tenancy-specific IPs, OCIDs, wallet paths, credentials, secret
  keys, or operator allowlists in public docs or diagrams.
- Terraform apply, destructive OCI changes, or load-balancer route cutovers
  without explicit user approval.
- Non-OCTO resources in the emdemo tenancy - automation must stay scoped to the
  OCTO demo project and approved shared services.

## Context

The repository owns the unified deployment and documentation layer for the
project. App code lives under `shop/`, `crm/`, and
`services/apm-java-demo/`; deployment assets live under `deploy/`; published
docs and editable architecture diagrams live under `site/`.

The current shared runtime uses both private VM/Compute services and OKE
services behind the same public load balancer. Routing may round-robin across
VM and OKE backends, so changes must preserve both contracts until a deliberate
cutover happens.

The demo is observability-first. New features are incomplete unless they can be
followed through RUM/APM, structured logs, Log Analytics fields/searches,
Monitoring metrics, database evidence, and security or GenAI evidence when the
feature touches those domains.

## Constraints

- **Security**: Do not hardcode or print secrets. Use environment variables,
  OCI secrets, wallets, ignored operator notes, or existing deployment secret
  paths.
- **Deployment**: Do not break existing VM, OKE, or load-balancer behavior.
  Route and certificate changes require explicit approval.
- **Observability**: Prefer existing Log Analytics fields and parser contracts
  before creating new fields.
- **Payments**: Keep payment flows simulated, token-safe, and traceable through
  customer, gateway, processor, Java, backend, and ATP steps.
- **GenAI**: OCI Coordinator belongs only in Admin and must answer only
  octo-apm-demo resource questions.
- **Docs**: Public docs and diagrams must stay sanitized and editable.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use `inherit` GSD model profile | Codex should use the current session model instead of Claude-specific tiers. | Good |
| Disable GSD worktree isolation | Codex subagent worktrees are not automatic in this runtime. | Good |
| Commit `.planning/` docs | Project context should travel with the repo for future GSD phases. | Pending |
| Treat VM and OKE as peer runtimes | The public LB can hit either path, so signal contracts must be equivalent. | Good |
| Keep OCI Coordinator admin-only | Prevent customer-surface access and keep answers scoped to OCTO resources. | Good |

---
*Last updated: 2026-05-14 after GSD onboarding.*
