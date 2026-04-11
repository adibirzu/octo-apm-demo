# OCTO Drone Shop

[:octicons-mark-github-16: Source](https://github.com/adibirzu/octo-drone-shop){ .md-button }

**ATP-backed drone commerce platform** with 98 API routes across 13 modules, full MELTS observability, IDCS SSO, and cross-service CRM integration.

## Key Features

- **E-commerce** — Product catalog (56 drones + accessories), shopping cart, checkout with shipment tracking
- **AI Assistant** — OCI GenAI-powered drone advisor with ATP conversation history
- **Workflow Gateway** — Go service for Select AI queries, query lab, scheduled ATP sweeps
- **RUM** — Custom browser events: add-to-cart, checkout funnel, search, page load
- **Security** — 19 MITRE ATT&CK security span types, WAF protection rules, Cloud Guard, Vault
- **Resilience** — Circuit breakers on CRM calls, chaos engineering controls, 5 OCI alarms

## Live Instance

| URL | Status |
|---|---|
| [shop.octodemo.cloud](https://shop.octodemo.cloud) | Production (OKE) |
| [shop.octodemo.cloud/api/observability/360](https://shop.octodemo.cloud/api/observability/360) | 360 Dashboard |

## Sections

- [Modules](modules.md) — All 13 modules and their endpoints
- [Checkout Flow](checkout.md) — Order lifecycle from cart to shipment
- [AI Assistant](assistant.md) — GenAI drone advisor with grounding documents
