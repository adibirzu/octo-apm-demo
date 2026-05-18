# Phase 1: Signal Contract Hardening - Patterns

## Existing Patterns to Follow

### FastAPI OTel Instrumentation

- `shop/server/observability/otel_setup.py` and
  `crm/server/observability/otel_setup.py` use `instrument_fastapi_app(app)`
  before custom middleware.
- Header capture is explicit and sanitized. Preserve
  `OTEL_CAPTURE_REQUEST_HEADERS`, `OTEL_SANITIZE_HEADERS`, and
  `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` behavior.
- Request hooks set low-cardinality resource and route attributes.

### Request Middleware

- Shop middleware is the richer model for business-flow enrichment:
  `resolve_workflow`, `purchase_context_from_request`,
  `purchase_span_attributes`, `runtime_snapshot`, and `set_db_context`.
- CRM middleware adds auth, validation, WAF, and finalization spans. Add missing
  correlation fields without removing these spans.

### Structured Logging

- `push_log` is the application logging entry point for both Shop and CRM.
- It already adds active trace/span IDs and service metadata.
- Log payloads use dotted fields plus underscore aliases through
  `_LOGAN_ALIAS_FIELDS`.
- PII masking returns new dictionaries and must not mutate caller input.
- `app.log` span events are attached to both active and request-root spans.

### Payment Evidence

- Payment gateway events use `payment.gateway.request_id` as the primary join
  key.
- Java sidecar and Shop payment modules use token-safe hashes and safe card
  fields only.
- Span/log/event names should be explicit: gateway, verification, processor,
  network, wallet, and card evidence are separate steps.

### Support-Service Telemetry

- Each support service has a local `telemetry.py` with `_parse_kv`,
  `_otlp_trace_endpoint`, `_exporter_config`, `init_otel`, optional
  `instrument_fastapi_app`, and `script_span`.
- Keep changes small and consistent across these files unless a shared package
  already exists for the target services.

### OCI Asset Tests

- Root tests under `tests/` validate deployment and Log Analytics assets.
- Prefer source assertions on JSON/SQL assets over live OCI calls for local
  test coverage.

## Patterns to Avoid

- Do not create new Log Analytics fields until the reuse map has been checked.
- Do not log raw PAN, CVV, wallet tokens, cryptograms, API keys, data keys, or
  prompt/response contents.
- Do not use unbounded path/user/input values as metric dimensions.
- Do not change public LB routing, DNS, certs, or Terraform state in Phase 1.
- Do not collapse Java stdout JSON into text-only SLF4J logs; OKE parsing
  depends on JSON payloads.
