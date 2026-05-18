# Phase 6: Documentation and Architecture Closure - Patterns

## Diagram Layer Pattern

Every public `.drawio` architecture file should have:

- a notes/flow layer for arrows and presenter movement
- one layer per major architectural domain
- sanitized labels only
- no live hostnames, IPs, OCIDs, wallet paths, profile names, or credentials

Rendered SVG previews should be kept aligned with visible label changes when a
DrawIO export tool is available; otherwise patch only the changed visible text.

## Admin AI Documentation Pattern

Documentation should show:

- OCI Coordinator only on the Admin/CRM surface
- Query Lab and Select AI through the Admin Workflow Gateway path
- customer pages as fake demo shop experiences, not backend consoles
- guardrail fields as pivots: `coordinator.scope.enforced`,
  `coordinator.auth.mode`, `oci.auth.mode`, `raw_prompt_logged=false`

## Troubleshooting Pattern

Operator docs should map symptoms to saved searches:

- connector rows missing -> `connector-live-log-coverage.sql`
- OKE ONM missing -> `oke-onm-ingestion-health.sql`
- OKE checkout correlation -> `oke-checkout-payment-correlation.sql`
- trace/log coverage -> `service-trace-log-coverage.sql`
- admin AI/Select AI -> `genai-assistant-llmetry.sql`

## Release Evidence Pattern

Public release docs can record source-level gate outcomes, but live deployment
evidence remains time-bound. Keep exact live tenancy values out of public docs.
