# Architecture

The OCTO Drone Shop uses a **modular, framework-based architecture** that enables new features to be added without breaking existing capabilities.

## Design Principles

1. **Module Independence** — Each of the 13 modules (shop, orders, auth, analytics, etc.) is a self-contained FastAPI router with its own spans, metrics, and error handling
2. **Observability by Default** — Every module automatically gets tracing, logging, and metrics through shared middleware and helpers
3. **Tenancy Portability** — Single `DNS_DOMAIN` variable derives all URLs, CORS origins, and SSO redirects
4. **Shared Data Layer** — All modules share Oracle ATP through SQLAlchemy with automatic instrumentation
5. **Cross-Service Isolation** — CRM integration uses circuit breakers to prevent cascading failures

## Component Overview

| Component | Tech | Routes | Purpose |
|---|---|---|---|
| Drone Shop | Python/FastAPI | 114 | Commerce, SSO, chaos, observability, CRM sync, payment webhooks, partner/public APIs, platform status |
| Workflow Gateway | Go | ~15 | Select AI, query lab, ATP sweeps, component health |
| Enterprise CRM | Python/FastAPI | 132 | CRM, simulation proxy, distributed traces, chaos admin, cross-service contract |
| OTel Gateway | OTel Collector | — | Central OTLP ingress → OCI APM + Prometheus + file |
| Async Worker | Python | — | Redis-Streams consumer for order fan-out + XCLAIM recovery |
| Remediator | Python | — | Alarm-driven playbooks (LOW/MEDIUM/HIGH tier gating) |
| Browser Runner | Playwright + TS | — | Synthetic journey executor |
| Load Control | Python | — | Named-profile traffic orchestrator |
| Cache | Redis + client | — | OTel-instrumented cache with span enrichment |
| Edge Gateway | TypeScript | — | Edge-fuzz + request shaping |
| Object Pipeline | Python | — | Object Storage drainer + upload |

## Diagrams

Drawio sources live in [`diagrams/`](diagrams/README.md) and open at
[app.diagrams.net](https://app.diagrams.net):

- **Platform Overview** — [`diagrams/platform-overview.drawio`](diagrams/platform-overview.drawio). Users → WAF → OKE → data + observability plane, every service + every OCI backend.
- **Observability Flow** — [`diagrams/observability-flow.drawio`](diagrams/observability-flow.drawio). MELTS signal flow: traces / logs / metrics / events / SQL-perf routed to OCI APM / Logging / Log Analytics / Stack Monitoring / Events.
- **Deploy Topology** — [`diagrams/deploy-topology.drawio`](diagrams/deploy-topology.drawio). Build path + OCIR + three deploy targets (OKE, single-VM, local-stack).

See the [diagrams README](diagrams/README.md) for the shape / colour legend and CLI re-render commands.

## Sections

- [System Design](system-design.md) — Runtime topology, cross-service flows, SSO architecture
- [Data Model](data-model.md) — Database schema, entity relationships, table organization
- [Framework Approach](framework.md) — How to add new modules without breaking existing ones
