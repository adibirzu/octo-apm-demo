# OCTO Cloud-Native Platform

**Two-service cloud-native platform with shared Oracle ATP, full OCI observability (MELTS: Metrics, Events, Logs, Traces, SQL), IDCS SSO, cross-service distributed tracing, and automated remediation.**

[:octicons-mark-github-16: Drone Shop](https://github.com/adibirzu/octo-drone-shop){ .md-button .md-button--primary }
[:octicons-mark-github-16: CRM Portal](https://github.com/adibirzu/enterprise-crm-portal){ .md-button .md-button--primary }
[:material-rocket-launch: Shop URL Template](https://shop.example.cloud){ .md-button }
[:material-rocket-launch: CRM URL Template](https://crm.example.cloud){ .md-button }

---

## What is OCTO?

The OCTO Cloud-Native Platform is a **two-service architecture** built on Oracle Cloud Infrastructure, demonstrating how enterprise workloads integrate with OCI's observability, security, and AI services.

| Service | Purpose | Routes |
|---|---|---|
| **[OCTO Drone Shop](drone-shop/index.md)** | E-commerce with AI assistant, MELTS observability (Metrics, Events, Logs, Traces, SQL), security controls | 98 |
| **[Enterprise CRM Portal](crm/index.md)** | CRM with OWASP security training, simulation lab, order sync | ~80 |

Both services share a **single Oracle ATP database**, enabling cross-service data correlation and distributed tracing visible in OCI APM Topology.

## Recent Architecture Updates

- **CRM owns catalog and storefront administration** — products, stock, pricing, category changes, shop assignment, and storefront metadata are now managed from the CRM control plane.
- **Shop stays customer-facing** — the public storefront remains focused on browse, cart, checkout, and shipment flows; operational edits are intentionally removed from the customer frontend.
- **Public and private CRM URLs are split** — browser-visible links use `https://crm.example.cloud`, while backend service-to-service calls may continue to use a private service endpoint.
- **Frontend hardening is live** — CRM page rendering, observability beacon ingestion, CSP-safe scripts, and favicon handling were updated to remove recent runtime errors.
- **Enhancement roadmap is published** — the docs now define the rollout path for complex flows, OCI APM, OCI Logging, Log Analytics, drilldowns, and DB tooling.

<div class="grid cards" markdown>

-   :material-telescope:{ .lg .middle } **Modular OCI Observability**

    ---

    APM, RUM, Logging, Log Analytics, Stack Monitoring, DB Management, Ops Insights — each activatable independently as add-ons.

    [:octicons-arrow-right-24: Add-Ons Guide](observability/addons.md)

-   :material-map-search:{ .lg .middle } **Enhancement Roadmap**

    ---

    Sequential plan for complex-call demos, APM visibility, log routing, drilldowns, and database investigation tooling.

    [:octicons-arrow-right-24: Enhancement Plan](observability/enhancement-plan.md)

-   :material-shield-check:{ .lg .middle } **Security-First Design**

    ---

    19 MITRE ATT&CK security span types, WAF protection rules, OCI Cloud Guard, Vault integration, and PII masking.

    [:octicons-arrow-right-24: Security](observability/security.md)

-   :material-puzzle:{ .lg .middle } **Framework Architecture**

    ---

    Modular design with 13 independent modules. Add new features without breaking existing capabilities.

    [:octicons-arrow-right-24: Framework](architecture/framework.md)

-   :material-connection:{ .lg .middle } **Cross-Service Integration**

    ---

    W3C traceparent-propagated distributed traces between Drone Shop, CRM Portal, and shared Oracle ATP.

    [:octicons-arrow-right-24: Integrations](integrations/index.md)

-   :material-database:{ .lg .middle } **Shared Oracle ATP**

    ---

    Single database instance with session tagging, SQL_ID bridging to OPSI, and cross-service data correlation.

    [:octicons-arrow-right-24: Database Integration](architecture/database-integration.md)

-   :material-flask:{ .lg .middle } **Simulation Lab**

    ---

    15+ chaos injection endpoints, cross-service proxy, data generation. Optional security testing add-on for OWASP training.

    [:octicons-arrow-right-24: Simulation](crm/simulation.md)

</div>

## Architecture at a Glance

```mermaid
flowchart TD
    Customer(["Customer (Browser + RUM)"])
    IDCS["OCI IAM Identity Domain"]

    subgraph OKE ["OCI OKE Cluster"]
        subgraph NS1 ["octo-drone-shop"]
            DroneShop["OCTO Drone Shop<br/>FastAPI · 98 routes"]
            WGW["Workflow Gateway<br/>Go · Select AI"]
        end
        subgraph NS2 ["enterprise-crm"]
            CRM["Enterprise CRM Portal<br/>FastAPI · ~80 routes"]
        end
    end

    subgraph OCI ["OCI Observability"]
        APM["OCI APM"]
        Logging["OCI Logging"]
        Monitoring["OCI Monitoring"]
        WAF["OCI WAF"]
        CloudGuard["Cloud Guard"]
    end

    DB[(Oracle ATP<br/>shared)]

    Customer -->|HTTPS| WAF --> DroneShop
    Customer -->|HTTPS| CRM
    Customer -.->|SSO| IDCS
    DroneShop <-->|"W3C traceparent<br/>orders + customer enrichment"| CRM
    DroneShop --> WGW
    DroneShop --> DB
    CRM --> DB
    WGW --> DB
    DroneShop -.-> APM
    CRM -.-> APM
    DroneShop -.-> Logging
    CRM -.-> Logging
    DroneShop -.-> Monitoring
```

## Key Capabilities

| Capability | Drone Shop | CRM Portal |
|---|---|---|
| **Primary role** | Customer storefront + checkout | Operations console + catalog admin |
| **Database** | Oracle ATP (shared) | Oracle ATP (shared) |
| **Authentication** | IDCS OIDC + PKCE | IDCS OIDC + PKCE |
| **Traces** | 50+ custom spans | 8+ spans/request |
| **Security** | 19 MITRE ATT&CK types | 24 MITRE ATT&CK types |
| **Catalog ownership** | Reads synced catalog data | Source of truth for products + shops |
| **Operational edits** | Cart, checkout, order origination | Customers, orders, invoices, products, shops |
| **Special** | AI assistant, WAF, Vault | Storefront Operations, order sync, simulation lab |

## Tenancy Portability

Set **one variable** and everything derives:

```bash
export DNS_DOMAIN="<your-domain>"
# → shop.<your-domain> (shop URL, CORS, SSO callback)
# → crm.<your-domain> (CRM URL, customer sync)
# → All IDCS redirect URIs auto-derived
```

No tenancy OCIDs, regions, or hostnames are hardcoded in the codebase.

## Related Components

| ID | Component | Repository |
|---|---|---|
| **Shop service** | Drone Shop Portal (OKE) | [octo-drone-shop](https://github.com/adibirzu/octo-drone-shop) |
| **CRM service** | Enterprise CRM Portal (OKE) | [enterprise-crm-portal](https://github.com/adibirzu/enterprise-crm-portal) |

Often deployed alongside an ops portal and OCI Coordinator, but this repository remains standalone and tenancy-portable.
