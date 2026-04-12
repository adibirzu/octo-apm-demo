# Architecture

FastAPI + Oracle ATP + OCI APM + OCI Logging + OCI Log Analytics, sharing
the same observability contract as the Shop.

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
