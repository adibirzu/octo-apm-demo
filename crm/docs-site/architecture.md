# Architecture

FastAPI + Oracle ATP + OCI APM + OCI Logging + OCI Log Analytics, sharing
the same observability contract as the Shop.

## Cross-service integration

CRM pairs with the OCTO Drone Shop over HTTPS. The wire protocol is
pinned on both sides and published at `/api/integrations/schema`.

- Canonical env vars: `SERVICE_SHOP_URL`, `INTERNAL_SERVICE_KEY`.
  Legacy aliases (`OCTO_DRONE_SHOP_URL`, `MUSHOP_CLOUDNATIVE_URL`,
  `DRONE_SHOP_INTERNAL_KEY`) remain accepted and surface a startup
  deprecation warning.
- `POST /api/orders` requires `X-Internal-Service-Key` whenever the
  shared key is configured; anonymous traffic is allowed only when
  the key is empty (back-compat).
- `source_system`, `source_order_id`, and `idempotency_token` from the
  payload are stored verbatim so shop-side retries with the same
  stable UUID5 token deduplicate to the same CRM order.

See [integrations/cross-service-contract.md](integrations/cross-service-contract.md).

## Correlation contract

| key | origin | who joins on it |
| --- | --- | --- |
| `trace_id` / `oracleApmTraceId` | OTel | APM, Log Analytics, Coordinator |
| `request_id` (`X-Request-Id`) | middleware | WAF ↔ app |
| `workflow_id` | middleware | LA dashboards, playbooks |

## Chaos admin

- UI: `/admin/chaos` (role `chaos-operator`).
- API: `POST /api/admin/chaos/apply`, `POST /api/admin/chaos/clear`.
- State: `chaos_state` table; Shop polls it every
  `CHAOS_STATE_POLL_SECONDS`.
- Audit: every apply/clear lands in the `octo-chaos-audit` LA parser.

## Security

- `SecurityHeadersMiddleware` with CSP nonce; admin pages embeddable only
  from the Ops portal (`allow_framing_from=https://$OPS_DOMAIN`).
- IDCS OIDC roles; rate limits on admin + login.
- WAF in DETECTION mode (`WAF_MODE=DETECTION`).
