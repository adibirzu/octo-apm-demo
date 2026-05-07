# Introduction

The **OCTO Cloud-Native Platform** is a reference implementation of enterprise applications running on Oracle Cloud Infrastructure (OCI). The current unified deployment, Resource Manager stacks, and documentation live in [`example-org/octo-apm-demo`](https://github.com/example-org/octo-apm-demo), which combines the Drone Shop service, Enterprise CRM service, OCI deployment automation, and the production-demo Compute stack.

## Goals

1. **Showcase OCI observability services** — APM, Logging, Monitoring, Log Analytics, DB Management, Operations Insights — as modular add-ons that can be activated independently
2. **Demonstrate cloud-native patterns** — FastAPI + Go microservices, shared Oracle ATP database, IDCS SSO, distributed tracing, circuit breakers
3. **Provide a framework architecture** — add new features without breaking existing capabilities; each module is independent
4. **Enable AI-driven operations** — integration with OCI Coordinator's Remediation Agent v2 for automated detection → diagnosis → remediation
5. **Serve as a reference implementation** — tenancy-portable OKE manifests, a private two-instance Compute stack, security best practices, comprehensive test coverage, and a clear split between public storefront and internal operations control planes

## Architecture Summary

Two application services share a single Oracle ATP database:

| Service | Role | Tech | Routes |
|---|---|---|---|
| [**OCTO Drone Shop**](drone-shop/index.md) | Customer storefront, checkout, AI assistant, observability surfaces | Python/FastAPI + Go | 98 |
| [**Enterprise CRM Portal**](crm/index.md) | CRM operations console, catalog admin, storefront control, simulation lab | Python/FastAPI | ~80 |

Both services integrate with the full OCI observability stack through modular add-ons that activate via environment variables or console configuration — no code changes required.

## Current Runtime Model

- **Canonical deployment repo**: [`example-org/octo-apm-demo`](https://github.com/example-org/octo-apm-demo)
- **Canonical docs site**: <https://example-org.github.io/octo-apm-demo>
- **Default shared deployment hostnames**: `https://shop.example.test` and `https://crm.example.test`
- **Validated private Compute hostnames**: `http://shop.example.test` and `http://crm.example.test`
- **Shop frontend**: `https://shop.example.test`
- **CRM frontend**: `https://crm.example.test`
- **Shared database**: Oracle ATP
- **Catalog source of truth**: CRM
- **Browser-visible CRM links**: public URL only
- **Backend CRM calls from shop**: may use the internal cluster-local CRM service URL on OKE or the private CRM instance IP on the Compute stack

This split matters operationally: the shop renders customer-facing catalog and checkout experiences, while the CRM is where operators edit customers, orders, invoices, storefronts, and product inventory.

## Provisioning a New Tenancy

Use the unified `octo-apm-demo` repo for new tenancy work. It contains
the current `deploy/bootstrap.sh` flow, private Compute Resource Manager
package, Helm chart, cross-service E2E tests, and deployment runbooks.

```bash
git clone https://github.com/example-org/octo-apm-demo.git
cd octo-apm-demo
./deploy/verify.sh
```

Recommended production-demo path:

[![Deploy Full Compute Stack to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/example-org/octo-apm-demo/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip)

That stack can create the VCN, public LB subnet, private app subnet,
private DB subnet, NAT Gateway, Service Gateway, NSGs/security lists,
two private Podman Compute instances, dedicated private ATP, OCI
LB/WAF, APM, OCI Logging, Log Analytics pipelines, DB Management,
Operations Insights, and Stack Monitoring Standard.

If you prefer OKE, start with the unified
[new tenancy guide](https://example-org.github.io/octo-apm-demo/getting-started/new-tenancy/).
For the shared reference profile profile, the baked-in domain is
`example.test`; check the unified
[current status page](https://example-org.github.io/octo-apm-demo/operations/current-status/)
before treating that shared environment as E2E-ready.

## OCI Services

The platform integrates with the following OCI services. Each service is an **independent add-on** — the application runs with or without any given service.

### Core Compute & Networking

| Service | Purpose | Docs |
|---|---|---|
| **Container Engine for Kubernetes (OKE)** | Managed Kubernetes for application hosting | [OKE Documentation](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengoverview.htm) |
| **Compute** | Private Shop and CRM hosts for the non-Kubernetes production demo | [Compute Documentation](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm) |
| **Container Registry (OCIR)** | Private Docker registry for container images | [OCIR Documentation](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm) |
| **Load Balancer** | HTTP/HTTPS load balancing with TLS termination | [Load Balancer Documentation](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview.htm) |
| **Virtual Cloud Network (VCN)** | Network infrastructure with public LB, private app, and private DB subnets plus NAT and Service Gateway routes | [VCN Documentation](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) |

### Database

| Service | Purpose | Docs |
|---|---|---|
| **Autonomous Transaction Processing (ATP)** | Oracle Autonomous Database for OLTP workloads | [ATP Documentation](https://docs.oracle.com/en-us/iaas/Content/Database/Concepts/adboverview.htm) |
| **Database Management** | Performance Hub, SQL Monitor, AWR reports | [DB Management Documentation](https://docs.oracle.com/en-us/iaas/database-management/index.html) |
| **Operations Insights** | SQL Warehouse, capacity planning, fleet summary | [Ops Insights Documentation](https://docs.oracle.com/en-us/iaas/operations-insights/index.html) |
| **Select AI** | Natural language queries on ATP | [Select AI Documentation](https://docs.oracle.com/en/database/oracle/oracle-database/23/dbcai/index.html) |

### Observability

| Service | Purpose | Docs |
|---|---|---|
| **Application Performance Monitoring (APM)** | Distributed tracing, service topology, trace explorer | [APM Documentation](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/index.html) |
| **APM Real User Monitoring (RUM)** | Browser performance monitoring, session replay | [APM RUM Documentation](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/real-user-monitoring.html) |
| **Logging** | Structured log ingestion with trace correlation | [Logging Documentation](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm) |
| **Logging Analytics (Log Analytics)** | Full-text log search, saved queries, dashboards | [Log Analytics Documentation](https://docs.oracle.com/en-us/iaas/logging-analytics/index.html) |
| **Monitoring** | Custom metrics, alarms, MQL queries | [Monitoring Documentation](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm) |
| **Notifications** | Alarm delivery via email, SMS, webhooks | [Notifications Documentation](https://docs.oracle.com/en-us/iaas/Content/Notification/Concepts/notificationoverview.htm) |
| **Health Checks** | HTTP/HTTPS endpoint monitoring | [Health Checks Documentation](https://docs.oracle.com/en-us/iaas/Content/HealthChecks/Concepts/healthchecks.htm) |
| **Stack Monitoring** | Application topology and component health | [Stack Monitoring Documentation](https://docs.oracle.com/en-us/iaas/stack-monitoring/index.html) |

### Security

| Service | Purpose | Docs |
|---|---|---|
| **IAM Identity Domains** | OIDC SSO with PKCE, JWKS verification | [Identity Domains Documentation](https://docs.oracle.com/en-us/iaas/Content/Identity/home.htm) |
| **Web Application Firewall (WAF)** | SQLi/XSS/command injection protection, rate limiting | [WAF Documentation](https://docs.oracle.com/en-us/iaas/Content/WAF/Concepts/overview.htm) |
| **Cloud Guard** | Security posture monitoring, problem detection | [Cloud Guard Documentation](https://docs.oracle.com/en-us/iaas/cloud-guard/home.htm) |
| **Security Zones** | Compliance policy enforcement at compartment level | [Security Zones Documentation](https://docs.oracle.com/en-us/iaas/security-zone/home.htm) |
| **Vault** | HSM-backed secret management and encryption keys | [Vault Documentation](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/home.htm) |
| **Vulnerability Scanning (VSS)** | Host and container vulnerability scanning | [VSS Documentation](https://docs.oracle.com/en-us/iaas/scanning/home.htm) |
| **Audit** | API event audit trail | [Audit Documentation](https://docs.oracle.com/en-us/iaas/Content/Audit/home.htm) |
| **Bastion** | Secure access to private resources | [Bastion Documentation](https://docs.oracle.com/en-us/iaas/Content/Bastion/home.htm) |

### AI & GenAI

| Service | Purpose | Docs |
|---|---|---|
| **Generative AI** | LLM inference for the AI assistant | [Generative AI Documentation](https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm) |
| **Generative AI Agents** | Agent orchestration with RAG | [Gen AI Agents Documentation](https://docs.oracle.com/en-us/iaas/Content/generative-ai-agents/home.htm) |

### Integration & Automation

| Service | Purpose | Docs |
|---|---|---|
| **API Gateway** | API management and routing | [API Gateway Documentation](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Concepts/apigatewayoverview.htm) |
| **Resource Manager** | Terraform-based infrastructure-as-code | [Resource Manager Documentation](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm) |
| **Events** | Event-driven automation triggers | [Events Documentation](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm) |
| **Functions** | Serverless compute (FaaS) | [Functions Documentation](https://docs.oracle.com/en-us/iaas/Content/Functions/home.htm) |

## Platform Services Map

```mermaid
flowchart TD
    subgraph Apps ["Application Services"]
        Shop["OCTO Drone Shop"]
        CRM["Enterprise CRM Portal"]
    end

    subgraph Compute ["Compute & Networking"]
        OKE["OKE"]
        ComputeVM["Private Compute"]
        OCIR["OCIR"]
        LB["Load Balancer"]
    end

    subgraph Data ["Database"]
        ATP["ATP"]
        DBMgmt["DB Management"]
        OPSI["Ops Insights"]
    end

    subgraph Obs ["Observability"]
        APM["APM"]
        RUM["APM RUM"]
        Logging["Logging"]
        LogAn["Log Analytics"]
        Monitoring["Monitoring"]
        Stack["Stack Monitoring"]
    end

    subgraph Sec ["Security"]
        IDCS["Identity Domains"]
        WAF["WAF"]
        CG["Cloud Guard"]
        SZ["Security Zones"]
        Vault["Vault"]
        VSS["VSS"]
    end

    subgraph AI ["AI Services"]
        GenAI["Generative AI"]
    end

    LB --> WAF --> Shop
    LB --> CRM
    Shop --> OKE
    CRM --> OKE
    Shop --> ComputeVM
    CRM --> ComputeVM
    Shop --> ATP
    CRM --> ATP
    ATP --> DBMgmt
    ATP --> OPSI
    Shop -.-> APM
    CRM -.-> APM
    APM --> RUM
    Shop -.-> Logging
    CRM -.-> Logging
    Logging --> LogAn
    Shop -.-> Monitoring
    OKE -.-> Stack
    IDCS --> Shop
    IDCS --> CRM
    CG --> Shop
    CG --> CRM
    VSS --> OKE
    Shop --> GenAI
    Vault --> Shop
```

## Platform Components

| Component | Service | Cloud Services Used | Description |
|---|---|---|---|
| **Drone Shop** | Python/FastAPI | ATP, APM, RUM, Logging, Monitoring, WAF, Cloud Guard, Vault, IDCS, GenAI | E-commerce storefront with checkout flow, AI assistant, customer-facing catalog, and distributed trace integration into CRM |
| **Workflow Gateway** | Go | ATP, APM, Select AI | Scheduled ATP query sweeps, query lab, Select AI execution |
| **Enterprise CRM** | Python/FastAPI | ATP, APM, RUM, Logging, IDCS | Operational control plane with order sync, storefront management, catalog editing, simulation lab, and OIDC SSO |

## Deployment Options

| Option | Time | Best For |
|---|---|---|
| [Local Docker](getting-started/quickstart.md) | 5 min | Development and testing |
| [OKE Deployment](getting-started/oke-deployment.md) | 30 min | Production with full OCI observability |
| [Private Compute Deployment](https://example-org.github.io/octo-apm-demo/getting-started/compute-deployment/) | 60-90 min | Production demo without Kubernetes, with LB/WAF, private instances, private ATP, APM, Logging, Log Analytics, and Stack Monitoring |
| [Unified Deployment Options](https://example-org.github.io/octo-apm-demo/getting-started/deployment-options/) | varies | Choosing between OKE, private Compute, Resource Manager, and single-VM paths |

## Next Steps

- [Getting Started](getting-started/index.md) — Prerequisites and deployment guide
- [Architecture](architecture/index.md) — System design, data model, framework approach
- [OCI Observability Add-Ons](observability/addons.md) — 8-level progressive enablement guide
- [Cross-Service Integration](architecture/database-integration.md) — How Drone Shop and CRM share ATP

## Reference Implementations

| Repository | Component |
|---|---|
| [octo-apm-demo](https://github.com/example-org/octo-apm-demo) | Unified deployment, Resource Manager stacks, and current documentation source |
| [octo-drone-shop](https://github.com/example-org/octo-drone-shop) | Drone Shop + Workflow Gateway service source |
| [enterprise-crm-portal](https://github.com/example-org/enterprise-crm-portal) | Enterprise CRM Portal |
