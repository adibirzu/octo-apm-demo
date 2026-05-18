# Architecture

OCTO APM Demo is a modular demo platform for showcasing OCI Observability
capabilities. The current public documentation uses a private Compute reference
deployment, while the same services can also run on OKE, a single VM, or a
local-stack target for workshops.

## Design Principles

1. **Customer flow first** — the public storefront stays focused on browsing,
   cart, checkout, assistant, and order tracking; operational controls live in
   the CRM and admin surfaces.
2. **Observability by default** — browser, Shop, CRM, Java sidecar, workflow,
   payment, SQL, and assistant flows emit shared trace/log/metric fields.
3. **Tenancy portability** — docs and scripts use variables such as
   `<OCI_PROFILE>`, `<COMPARTMENT_OCID>`, `<APM_DOMAIN_OCID>`,
   `<LA_NAMESPACE>`, and `<DNS_DOMAIN>`.
4. **Sanitized public architecture** — published diagrams must not contain live
   public IP addresses, private IP addresses, OCIDs, credential paths, or
   operator allowlists.
5. **Independent deployment paths** — Compute is the current reference, OKE
   remains supported, and the deployment topology documents both.

## Current Component Overview

| Component | Tech | Purpose |
|---|---|---|
| Drone Shop | Python/FastAPI | Customer storefront, checkout, AI assistant, RUM/APM/log/metric emission, payment gateway telemetry, CRM sync. |
| Enterprise CRM | Python/FastAPI | Operations portal, catalog and storefront administration, order/customer workflows, simulation and security training surfaces. |
| Java payment/app-server sidecar | Spring Boot | Token-safe payment verification/authorization, Java APM App Servers visibility, JVM request/GC/CPU/error demo spans. |
| Workflow Gateway | Go | Select AI, query lab, ATP workflow checks, and component health surfaces. |
| Oracle ATP | OCI Autonomous Database | Shared persistence, SQL visibility, cross-service correlation, assistant/event storage. |
| OCI Load Balancer / WAF / API Gateway | OCI edge services | Public entry, route policy, threat controls, request ids, access logs, and trace-header preservation. |
| OCI Observability stack | OCI APM, RUM, Logging, Log Analytics, Monitoring, Stack Monitoring | End-to-end MELTS view, saved queries, dashboards, alarms, and drill-downs. |
| Optional platform services | OTel Collector, load-control, browser-runner, remediator, async worker, cache, object pipeline | Workshop expansion services for synthetic traffic, remediation, async flows, and broader OCI 360 demos. |

## Diagrams

Drawio sources live in [`diagrams/`](diagrams/README.md) and open at
[app.diagrams.net](https://app.diagrams.net). Use the rendered SVG previews for
the docs site and the `.drawio` files when editing.

| Diagram | Preview | Editable source |
|---|---|---|
| Private Demo Observability Reference | [`private-demo-observability-reference.svg`](diagrams/private-demo-observability-reference.svg?v=20260509-sanitized) | [`private-demo-observability-reference.drawio`](diagrams/private-demo-observability-reference.drawio) |
| Platform Overview | [`platform-overview.svg`](diagrams/platform-overview.svg?v=20260511-contrast) | [`platform-overview.drawio`](diagrams/platform-overview.drawio) |
| Observability Flow | drawio source only | [`observability-flow.drawio`](diagrams/observability-flow.drawio) |
| Deploy Topology | drawio source only | [`deploy-topology.drawio`](diagrams/deploy-topology.drawio) |

![Platform Overview OCTO APM Demo architecture](diagrams/platform-overview.svg?v=20260511-contrast)

![Private Demo OCTO APM Demo architecture](diagrams/private-demo-observability-reference.svg?v=20260509-sanitized)

See the [diagrams README](diagrams/README.md) for the shape and colour legend,
download links, sanitization rules, and CLI re-render commands.

## Sections

- [Platform Overview](platform-overview.md) — current Compute reference, OKE support path, and OCI service boundaries
- [System Design](system-design.md) — runtime topology, cross-service flows, SSO, assistant, and APM topology
- [Correlation Contract](correlation-contract.md) — field names used to pivot between APM, logs, Log Analytics, SQL, payment, and assistant telemetry
- [Service Inventory](service-inventory.md) — shipped services and the signals they emit
- [Data Model](data-model.md) — database schema, entity relationships, table organization
- [Framework Approach](framework.md) — how to add modules without breaking existing capabilities
