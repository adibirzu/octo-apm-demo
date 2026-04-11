# Enterprise CRM Portal

[:octicons-mark-github-16: Source](https://github.com/adibirzu/enterprise-crm-portal){ .md-button }

**Deliberately vulnerable CRM application** with 73 API routes across 12 modules, designed for security training and observability demonstration.

## Key Features

- **Full CRM** — Customers, orders, invoices, support tickets, campaigns, leads, shipping, reports
- **OWASP Top 10** — Intentional vulnerabilities for security training (SQLi, XSS, SSRF, IDOR, etc.)
- **Order Sync** — One-way sync from Drone Shop with audit trail and backlog detection
- **Simulation Lab** — 15+ chaos injection endpoints with cross-service proxy
- **Security Spans** — 24 MITRE ATT&CK vulnerability types with OWASP classification
- **Session Management** — ATP-backed sessions for OKE replica sharing

## Live Instance

| URL | Status |
|---|---|
| [crm.octodemo.cloud](https://crm.octodemo.cloud) | Production (OKE) |

## Dual Purpose

The CRM Portal serves two roles:

1. **Security Training** — Intentional OWASP vulnerabilities with security span detection. Every attack attempt generates an APM trace with MITRE ATT&CK classification.

2. **Integration Demo** — Cross-service distributed tracing with Drone Shop, shared ATP database, simulation proxy for chaos engineering.

## Sections

- [Modules](modules.md) — All 12 modules and their endpoints
- [Order Sync](order-sync.md) — How orders flow from Drone Shop to CRM
- [Security Vulnerabilities](security-vulns.md) — OWASP Top 10 coverage and detection
- [Simulation Lab](simulation.md) — Chaos injection and cross-service controls
