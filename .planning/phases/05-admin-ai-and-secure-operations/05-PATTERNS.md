# Phase 5: Admin AI and Secure Operations - Patterns

## Admin Boundary Pattern

Admin AI, Query Lab, Select AI, and Coordinator routes need both:

- admin or internal-service authentication
- admin host/surface checks for browser callers

Local tests may use `localhost`, `127.0.0.1`, `::1`, and `testserver`.
Service callers may bypass host checks only when authenticated as the internal
service role.

## Coordinator Scope Pattern

Coordinator answers must include:

- `scope = octo-apm-demo`
- `admin_only = true`
- `scope_enforced = true`
- no raw prompt logging
- scoped source endpoints only

Unrelated domains, all-compartment/all-tenancy requests, and unrelated project
questions are refused with a useful next action.

## LLMetry Pattern

LLM telemetry should emit:

- prompt and response hashes
- lengths and token counts
- provider/model labels
- session ID and trace/span IDs
- guardrail outcome
- Langfuse-compatible trace/session/observation attributes

Raw content remains disabled by default and redacted when explicitly enabled.

## Customer Copy Pattern

Customer pages may describe fake data, simulated orders, APM, logs, RUM, and
OCI observability. They should avoid backend/internal wording, service secrets,
private hostnames, OCIDs, private data keys, and operator-only controls.
