# Codebase Architecture

Generated: 2026-05-14

## System Shape

The repository is a unified wrapper around a customer-facing Shop, an
operator-facing CRM/Admin portal, a Java payment sidecar, support services, OCI
deployment assets, and public documentation. The core product is an
observability demo rather than a traditional shop: customer and admin actions
are valuable because they create correlated evidence across OCI services.

## Main Runtime Flow

1. Browser loads Shop or Admin with OCI RUM configured.
2. Customer logs in, browses, adds to cart, and starts checkout.
3. Shop records workflow/user/order context and calls the Java sidecar for
   simulated payment gateway and processor work.
4. Java emits payment rail spans and structured JSON events.
5. Shop writes order/database evidence and synchronizes with CRM/Admin.
6. APM, Logging, Log Analytics, Monitoring, and ATP carry linked identifiers
   for troubleshooting and threat hunting.

## Service Boundaries

- Shop owns customer storefront, cart, checkout, assistant, purchase journey,
  payment orchestration, RUM actions, and customer-facing evidence copy.
- CRM/Admin owns operator workflows, users, orders, catalog/admin pages,
  coordinator access, DB cleanup, simulation controls, and captured data views.
- Java sidecar owns app-server/JVM evidence and token-safe payment rail
  simulation details.
- Deployment assets own image build/push, VM/OKE/container wiring, OCI
  resource templates, Log Analytics assets, and docs.
- Supporting services add load, browser journeys, async work, cache, object
  pipeline, edge/security simulations, and remediation scenarios.

## Deployment Architecture

- VM/Compute and OKE are peer runtimes behind the same public LB route model.
- VM uses private Compute hosts, local sidecars, systemd, and container logs.
- OKE uses Deployments, Services, HPA/PDB, namespace annotations, and OCI
  Kubernetes Monitoring collectors.
- Both runtimes must use the same APM domain, compatible service names, same
  Log Analytics field contract, same ATP, and same demo data model.

## Observability Architecture

- APM is the trace/topology/RUM source of truth.
- Log Analytics is the troubleshooting, dashboard, and detection query layer.
- OCI Monitoring is the metric/alarm layer for app and OKE health.
- ATP/SQL spans provide database evidence and order/user relationship pivots.
- GenAI evidence flows through APM/LLMetry/Langfuse and Admin-scoped surfaces.

## Documentation Architecture

- `site/` is the published MkDocs source.
- Editable diagrams live under `site/architecture/diagrams/`.
- Public docs use placeholders and sanitized diagrams only.
- Local operator notes, credentials, resolved OCIDs, IPs, wallet paths, and
  allowlists must not move into public docs or GSD artifacts.
