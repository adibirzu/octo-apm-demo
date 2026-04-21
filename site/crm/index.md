# Enterprise CRM Portal

[:octicons-mark-github-16: Source](https://github.com/adibirzu/enterprise-crm-portal){ .md-button }

**Cloud-native CRM application** that now serves as the OCTO operations control plane for customer data, orders, invoices, product inventory, and storefront administration.

## Key Features

- **Full CRM** — Customers, orders, invoices, support tickets, campaigns, leads, shipping, reports
- **Storefront Operations** — Manage shops, public CRM/storefront URLs, storefront status, and full catalog sync to the shop
- **Catalog Control Plane** — Create and edit drones, batteries, accessories, stock, price, category, and image metadata directly in CRM
- **Modular Observability** — Each OCI service (APM, Logging, Monitoring, etc.) activates independently via env vars
- **Order Sync** — One-way sync from Drone Shop with audit trail and backlog detection
- **Simulation Lab** — 15+ chaos injection endpoints with cross-service proxy
- **IDCS SSO** — OIDC Authorization Code + PKCE with JWKS verification
- **ATP-Backed Sessions** — Session store in Oracle ATP for OKE replica sharing

## Live Instance

| URL | Status |
|---|---|
| [crm.example.cloud](https://crm.example.cloud) | Production (OKE) |

## Observability-First Design

The CRM Portal demonstrates how OCI Observability services integrate with cloud-native applications. Every service is an **independent add-on** — deploy the app first, enable observability later:

```
Minimal deploy: App + ATP (no observability)
     ↓ add OCI_APM_ENDPOINT
+APM: 8+ spans/request, distributed traces, topology
     ↓ add OCI_LOG_ID
+Logging: Structured logs with oracleApmTraceId correlation
     ↓ add OCI_COMPARTMENT_ID
+Monitoring: Custom metrics, alarms, health checks
     ↓ run ensure_db_observability.sh
+DB Management + Ops Insights: Performance Hub, SQL Warehouse
```

No code changes required at any step.

## Operational Scope

- Use the CRM when you need to edit **customers, orders, invoices, products, or shops**.
- Use the shop when you need to validate the **customer-facing storefront, cart, checkout, and shipment experience**.
- The CRM publishes catalog updates to the shop and writes the shared ATP source-of-record data that both services trace against.

## Sections

- [Modules](modules.md) — CRM routers, storefront operations, and catalog control surfaces
- [Order Sync](order-sync.md) — How orders flow from Drone Shop to CRM
- [Simulation Lab](simulation.md) — Chaos injection and cross-service controls
- [Security Testing](security-vulns.md) — Optional OWASP vulnerability add-on
