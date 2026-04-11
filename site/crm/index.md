# Enterprise CRM Portal

[:octicons-mark-github-16: Source](https://github.com/adibirzu/enterprise-crm-portal){ .md-button }

**Cloud-native CRM application** with 73 API routes across 12 modules, built for OCI Observability demonstration with modular add-on architecture.

## Key Features

- **Full CRM** — Customers, orders, invoices, support tickets, campaigns, leads, shipping, reports
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

## Sections

- [Modules](modules.md) — All 12 modules and their endpoints
- [Order Sync](order-sync.md) — How orders flow from Drone Shop to CRM
- [Simulation Lab](simulation.md) — Chaos injection and cross-service controls
- [Security Testing](security-vulns.md) — Optional OWASP vulnerability add-on
