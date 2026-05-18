# Phase 5: Admin AI and Secure Operations - Research

## Surface Inventory

| Surface | Evidence | Notes |
|---|---|---|
| Admin Coordinator | `crm/server/modules/coordinator.py` | Admin-authenticated, host-scoped, deterministic OCTO APM Demo guidance. |
| Coordinator UI | `crm/server/templates/page.html` | Rendered only when `module == "admin"`. |
| Shop assistant | `shop/server/modules/admin.py`, `shop/server/assistant_service.py` | Admin/internal endpoint; uses OCI GenAI when configured and falls back to ATP-grounded local answer. |
| LLMetry | `shop/server/observability/llmetry.py` | Emits hashes, lengths, tokens, trace IDs, Langfuse attributes, and safe metadata. |
| Workflow Gateway | `shop/server/modules/workflow_gateway.py` | Proxies Query Lab and Select AI to private gateway with trace propagation. |
| Customer pages | `shop/server/templates/dashboard.html`, `shop/server/templates/shop.html`, `shop/server/templates/login.html` | Demo copy should avoid backend/internal terminology. |

## Gaps Found

- Coordinator host allow-list was static and could reject configured admin
  hostnames such as `admin.<DNS_DOMAIN>` in non-octodemo environments.
- Coordinator responses did not expose explicit guardrail metadata for
  observability dashboards and tests.
- Workflow Gateway Query Lab/Select AI proxy required admin auth but did not
  also reject public storefront hostnames for non-service callers.
- Customer login copy still mentioned backend APIs.
- Shop storefront used a backend-oriented DOM id for its visible APM status.

## Validation Strategy

- Add tests for configured admin host acceptance, public shop host rejection,
  guardrail metadata, and customer-safe copy.
- Run targeted CRM and Shop tests separately because both apps use a `server`
  Python package name and cannot safely share one interpreter import path in
  a mixed pytest invocation.
- Run source-contract, docs, and deployment gates after patching.

## Live Validation Deferred

- OCI GenAI model invocation with instance principal.
- Select AI execution through the private Workflow Gateway.
- Langfuse project ingestion for `drones.octodemo.cloud`.
- OCI APM Trace Explorer confirmation for admin assistant and Select AI spans.
