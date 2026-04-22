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
| Drone Shop | Python/FastAPI | 98 | Commerce, SSO, chaos, observability, CRM sync |
| Workflow Gateway | Go | ~15 | Select AI, query lab, ATP sweeps, component health |
| Enterprise CRM | Python/FastAPI | ~80 | CRM, simulation proxy, distributed traces |

## Sections

- [System Design](system-design.md) — Runtime topology, cross-service flows, SSO architecture
- [Data Model](data-model.md) — Database schema, entity relationships, table organization
- [Framework Approach](framework.md) — How to add new modules without breaking existing ones
