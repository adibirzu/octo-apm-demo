# Codebase Integrations

Generated: 2026-05-14

## OCI Runtime Integrations

- OCI APM: primary trace, topology, RUM, saved-query, and Java App Servers
  destination for Shop, Admin/CRM, Java sidecar, OKE services, and scripts.
- OCI Logging: application JSON logs and selected security/OS events.
- OCI Log Analytics: parser/source mappings, saved searches, dashboards,
  detection rules, OKE monitoring logs, and APM trace pivots.
- OCI Monitoring: custom app and business metrics in `octo_apm_demo`.
- OCI Kubernetes Monitoring: OKE logs/metrics/tcpconnect collectors in
  `oci-onm`.
- Oracle ATP: shared database for orders, users, CRM sync, assistant state,
  LLMetry, and SQL evidence.
- OCI WAF/API Gateway/LB: public route policy, request IDs, threat fields, and
  backend routing across VM and OKE.
- OCI IAM Identity Domain: OIDC/PKCE SSO where enabled.
- OCIR: container image registry for VM/OKE images.
- OCI Vault/Secrets and ATP wallets: runtime secret and database access.

## GenAI and LLM Telemetry

- OCI Generative AI is accessed through OCI SDK with instance principal,
  resource principal, or local config depending on runtime configuration.
- Langfuse is optional and configured through environment variables and OTLP
  trace export settings.
- LLMetry fields are expected to correlate GenAI prompts, model responses,
  assistant sessions, APM spans, logs, and database rows without exposing
  secrets or sensitive prompt content.

## Payment Simulation

- Shop orchestrates checkout and simulated gateway workflows.
- Java sidecar provides App Servers evidence, antifraud/verification,
  authorization, processor response, and network-routing spans.
- Payment rail labels include Google Pay, Apple Pay, Visa, Mastercard, and
  gateway/processor components.
- All payment data must remain simulated and token-safe.

## Service Contracts

- Shop and CRM expose `GET /api/integrations/schema`.
- Internal service calls use `X-Internal-Service-Key`.
- Order idempotency uses `source_system`, `source_order_id`, and
  `idempotency_token`.
- Cross-service correlation uses `trace_id`, `span_id`, `oracleApmTraceId`,
  `oracleApmSpanId`, `request_id`, `workflow_id`, order IDs, payment gateway
  request IDs, and user/session pivots.

## External Repositories

- `shop/` tracks the upstream `octo-drone-shop` subtree.
- `crm/` tracks the upstream `enterprise-crm-portal` subtree.
- Log Analytics detection assets may also integrate with the sibling
  `oci-log-analytics-detections` repository during deployment and verification.
