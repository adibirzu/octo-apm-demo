# Correlation Contract

The authoritative specification for the identity fields that every
service, log line, span, and alarm must carry so an operator can pivot
across signals without manual correlation. This document is
**load-bearing** — the rest of OCI 360 depends on it.

## Why a contract

When a customer reports "checkout was slow at 14:03 yesterday", the
operator needs to pivot from:

- The browser complaint (RUM session)
- To the server request (APM trace)
- To the failing SQL (Log Analytics search)
- To the database wait event (OPSI)
- To the host alarm that fired (Monitoring)

…without re-keying identifiers or guessing at timestamps. The contract
below is what makes those pivots clickable.

## Required identity fields (every signal)

| Field | Scope | Shape | Source of truth |
|---|---|---|---|
| `trace_id` | span | 32 hex chars (W3C) | OTel SDK |
| `span_id` | span | 16 hex chars | OTel SDK |
| `oracleApmTraceId` | log record | same as `trace_id` | stamped by the app's logging SDK shim |
| `request_id` | span + log + LB/WAF log | `uuid4` | edge middleware (nginx/LB/API-GW) — **not** the app |
| `workflow_id` | span + log | human-readable slug (`checkout-v2`, `crm-catalog-sync`) | app — one per business flow |
| `run_id` | span + log + alarm annotation | `uuid4` | emitted by `octo-load-control` when a profile runs; otherwise absent |
| `assistant.session_id` | LLM span + log + ATP row | `uuid4` or caller-provided session ID | Drone Shop assistant |
| `llm.prompt.hash` | LLM span + log + ATP row | SHA-256 hex | LLMetry helper |
| `llm.response.hash` | LLM span + log + ATP row | SHA-256 hex | LLMetry helper |
| `service.name` | OTel resource | kebab-case short name | Deployment env |
| `service.namespace` | OTel resource | `octo` | fixed |
| `deployment.environment` | OTel resource | `production` \| `staging` \| `dev` | Deployment env |

### Why each field exists

- **`trace_id` + `span_id`** are the OTel primitives — every other
  column is a denormalization to make search fast.
- **`oracleApmTraceId`** is the column name OCI APM + Log Analytics
  join on. We stamp the current OTel `trace_id` into every log record
  under this name so the LA parser knows how to index it.
- **`request_id`** survives even when OTel is disabled (on the edge
  path it originates at the LB/WAF). It's the "one ID per customer
  click" you can dictate over the phone.
- **`workflow_id`** is the human-readable business flow. APM dashboards
  group by it — not by span name — so a checkout that spans 40 spans
  rolls up to one widget.
- **`run_id`** only exists when a load profile or operator action is
  running. It lets you filter "what happened while I was executing
  the `db-write-burst` profile" without contaminating normal traffic
  queries.
- **`assistant.session_id` + `llm.*.hash`** join OCI APM spans, OCI
  Logging rows, ATP `llmetry_events`, and Langfuse observations without
  logging raw prompts or responses.
## Payment field dictionary

Checkout, payment gateway, processor, CRM order, and payment log records
MUST include the following fields when a payment attempt exists:

| Field | Purpose |
|---|---|
| `payment.gateway.request_id` | Stable join key across Shop, gateway events, CRM, logs, and spans |
| `payment.method` | `card`, `apple_pay`, `google_pay`, or simulator-specific method |
| `payment.provider` | Gateway or wallet provider label, for example `visa`, `mastercard`, `apple_pay`, `google_pay` |
| `payment.network` | Simulated network route, for example `visa`, `mastercard`, `wallet_token_network` |
| `payment.status` | `pending`, `paid`, `declined`, `failed`, or `requires_payment` |
| `payment.verification.decision` | Antifraud decision such as `approved`, `review`, or `declined` |
| `payment.risk_score` | Synthetic normalized risk score used for demo filtering |
| `payment.wallet.token_hash` | Hash of the wallet token payload; never the raw token |
| `payment.card_brand` / `payment.card_last4` | Safe card identity fields for operator filtering |
| `payment.card.avs.result` / `payment.card.cvv.result` | Synthetic AVS/CVV authorization evidence |
| `payment.3ds.program` / `payment.3ds.eci` | Simulated Visa Secure or Mastercard Identity Check evidence |
| `payment.processor.response_code` | Synthetic processor response code, for example `00`, `05`, or `91` |
| `payment.network.transaction_id` | Synthetic network transaction id for trace/log joins |
| `orders.order_id` / `order_id` | Safe order identifier used by Shop, CRM, payment gateway events, invoices, and shipping joins |
| `source_order_id` | CRM-side upstream order id; preserves retry-safe relation to the Shop order |

Payment metadata MUST be tokenized or synthetic. Raw PAN, CVV, wallet
tokens, cryptograms, or customer secrets must not be stored in spans, logs,
CRM rows, or `payment_gateway_events`.

The Java sidecar MUST receive the same token-safe payment correlation
fields from the Python gateway. It MUST enrich the active Java span with
the gateway request id, method, network, wallet/card safe fields, processor
decision, and Java payment span events, while preserving the no-raw-token
rule above.

## Synthetic browser field dictionary

Recurring APM synthetic runs and workshop browser runs SHOULD include these
fields when present:

| Field | Purpose |
|---|---|
| `synthetic_user_enabled` | Distinguishes synthetic RUM sessions from normal browser sessions |
| `synthetic_user_domain` | Groups fictional synthetic users without exposing real operator identities |
| `payment.gateway.request_id` | Joins the synthetic checkout to payment gateway spans, logs, and persisted gateway events |
| `payment.gateway.verification.decision` | Confirms the antifraud app decision is visible in the buying trace |

OCI APM synthetic script parameters use `OCTO_APM_DEMO_MODE=monitor` for the
short recurring path and `OCTO_APM_DEMO_MODE=full` for workshop paths. Do not
commit live URLs, passwords, Vault OCIDs, or internal service keys with those
parameters.

## Field semantics

### `trace_id`
- Generated by the first service to receive the request, or propagated
  in the W3C `traceparent` header from upstream.
- Must be exactly 32 lowercase hex characters.
- MUST be stamped on every log record the request produces.

### `request_id`
- Generated at the edge (nginx, OCI LB, API Gateway).
- Format: `uuid4` (36 chars with dashes).
- App middleware reads the incoming `X-Request-Id` header; if absent,
  generates one and sends it downstream.

### `workflow_id`
- App-level classifier. Examples:
  - `checkout-v2`
  - `crm-catalog-sync`
  - `crm-order-sync`
  - `rum-session-start`
  - `admin-chaos-apply`
- Value is hardcoded in each business-flow handler. Not taken from
  user input.
- Dashboard widgets group latency/error rates by this field.

### `run_id`
- Optional. Present only when:
  - A load profile is executing (injected by `octo-load-control`).
  - An operator explicitly started a named action through the Simulation
    Lab.
- Format: `uuid4`.
- Stamped onto every span + log emitted during the run window.
- Alarms that fire during a run get the `run_id` as an annotation so
  the postmortem query can slice by run.

### `service.name`
- Current allocation:
  - `octo-drone-shop`
  - `enterprise-crm-portal`
  - `octo-workflow-gateway` (Go)
  - `octo-traffic-generator`
  - `octo-otel-gateway` (planned)
  - `octo-load-control` (planned)
  - `octo-browser-runner` (planned)
  - `octo-cache` (planned)
  - `octo-async-worker` (planned)

## Log field dictionary

Every JSON log record MUST include:

```json
{
  "timestamp": "2026-04-22T14:03:02.123Z",
  "level": "INFO|WARN|ERROR|DEBUG",
  "service": "octo-drone-shop",
  "trace_id": "1a2b3c...",
  "span_id": "4d5e6f...",
  "oracleApmTraceId": "1a2b3c...",
  "request_id": "a3b8...",
  "workflow_id": "checkout-v2",
  "message": "human-readable summary",
  "route": "/api/orders",
  "http_status": 201,
  "duration_ms": 87,

  "run_id": "optional-uuid-when-under-load-profile",

  "...": "arbitrary structured context"
}
```

Field names are case-sensitive. Log Analytics parsers should reuse existing
namespace fields when the display name matches exactly; otherwise create the
missing field or update every saved search, widget, dashboard, and detection
rule to the reused display name in the same change.

## Propagation headers

| Header | Direction | Set by | Read by |
|---|---|---|---|
| `traceparent` (W3C) | all hops | OTel SDK | OTel SDK |
| `tracestate` (W3C) | all hops | OTel SDK | OTel SDK |
| `X-Request-Id` | edge → app → downstream | nginx/LB/API-GW | app middleware, downstream services |
| `X-Workflow-Id` | app → downstream | app middleware | downstream services |
| `X-Run-Id` | load-control → app → downstream | `octo-load-control` | downstream services |

Downstream services MUST copy these four headers onto every outbound
HTTP call they make. `httpx.Client` auto-propagates `traceparent`
(via OTel instrumentation); the other three are propagated by the
app's outbound-headers helper (`server/observability/correlation.py`
on both shop + crm).

## LLMetry field dictionary

Assistant LLM spans and logs MUST include these fields when the
assistant path is executed:

| Field | Purpose |
|---|---|
| `assistant.session_id` | Conversation/session join key shared by browser, ATP, spans, logs, and Langfuse |
| `assistant.provider` | `oci_genai`, `local_grounded_fallback`, or `guardrail_scope_filter` |
| `assistant.model_id` | OCI GenAI model ID or fallback model label |
| `assistant.guardrail.allowed` | Boolean scope decision |
| `assistant.guardrail.reason` | `catalog_product`, `drone_domain_keyword`, `blocked_term`, `out_of_scope`, etc. |
| `assistant.documents_grounded` | Count of ATP product documents passed to the model |
| `llm.prompt.hash` | SHA-256 hash of the user prompt |
| `llm.response.hash` | SHA-256 hash of the assistant response |
| `llm.prompt.length` / `llm.response.length` | Character counts used for sizing without storing raw text |
| `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | OCI GenAI token usage when returned by the provider |
| `langfuse.trace.name` / `langfuse.session.id` | Optional Langfuse OTLP mapping fields |
| `llmetry.latency_ms` / `llmetry.error_type` | LLMetry health fields used by Log Analytics fast troubleshooting |

In Log Analytics, these raw fields are mapped through the reuse-first namespace
field map instead of creating new global fields. The main pivots are
`assistant.session_id` -> `Session ID`, `llm.prompt.hash` -> `Application Hash`,
`llm.response.hash` -> `Current Hash`, `gen_ai.usage.input_tokens` ->
`Content Size In`, `gen_ai.usage.output_tokens` -> `Content Size Out`, and
`langfuse.session.id` -> `Session`.

Raw prompt and response text MUST NOT be emitted to spans or logs unless
`LLMETRY_CAPTURE_CONTENT=true`, and even then only redacted previews are
allowed. The default path stores hashes, lengths, token counts, provider,
model, guardrail result, latency, trace ID, and span ID in the ATP
`llmetry_events` table.

## OCI Events envelope

Every OCI Event emitted by the platform MUST carry:

```json
{
  "eventType": "com.octodemo.<service>.<noun>.<verb>",
  "eventTypeVersion": "1.0",
  "source": "<service.name>",
  "eventTime": "<iso8601>",
  "data": {
    "run_id": "<uuid or empty>",
    "workflow_id": "<slug>",
    "oracleApmTraceId": "<trace_id>",
    "request_id": "<uuid>",
    "...": "event-specific payload"
  }
}
```

Consumers (Coordinator, alarms, notifications) filter on `source` +
`eventType` and join back to traces + logs via the four identity
fields in `data`.

## Alarm annotation contract

OCI Monitoring alarms MUST annotate the notification with:

```
annotation.run_id = <active run_id or "none">
annotation.workflow_id = <primary workflow impacted>
annotation.trace_exemplar = <latest matching trace_id>
```

This lets on-call paste a single URL into chat and get everyone onto
the same incident.

## Versioning

This contract is **v1.0**. Breaking changes (renaming a required field,
changing a format) require:

1. A new contract version (`v2.0`).
2. A migration plan with dual-writing for at least one release.
3. An update to the Log Analytics parsers AND the alarm annotation
   templates.

## Implementation checklist

When onboarding a new service to OCI 360:

- [ ] `service.name` registered above.
- [ ] OTel SDK exports to `octo-otel-gateway` (not direct to OCI APM).
- [ ] Log records include every field in the dictionary above.
- [ ] Reads `X-Request-Id`, `X-Workflow-Id`, `X-Run-Id` on inbound.
- [ ] Propagates all three + W3C headers on outbound HTTP.
- [ ] Emits OCI Events in the envelope above when relevant.
- [ ] Appears in the `/api/observability/360` inventory (once that
      endpoint is generalized — see OCI 360 Phase 0 deliverables).

## Signal contract enforcement

The source-level guard for this contract is:

```bash
python3 -m pytest -q tests/test_signal_contract_inventory.py
```

That test intentionally reads the application, Java sidecar, support-service,
APM saved-query, Log Analytics field-map, and Monitoring publisher sources. It
fails when a required join field or operator drilldown asset is removed without
an explicit contract update.

Enforcement points:

- `shop/server/observability/logging_sdk.py` and
  `crm/server/observability/logging_sdk.py` stamp `push_log` payloads with
  `trace_id`, `span_id`, `oracleApmTraceId`, `oracleApmSpanId`, `request_id`,
  `workflow_id`, `workflow_step`, and the service resource identity from
  `service_metadata()`.
- `services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java` emits stdout
  JSON for the Java payment gateway. Those events are parser input for Log
  Analytics and must keep the Java trace ids, service aliases, and
  `payment_gateway_request_id`.
- `services/*/src/*/telemetry.py` helpers must create OTel resources with
  `service.name`, `service.namespace`, `deployment.environment`,
  `cloud.provider`, and `oci.demo.stack`.
- `deploy/oci/apm/saved-queries/*.json` keeps Trace Explorer drilldowns aligned
  with the Log Analytics searches named in `logAnalyticsPivots`.
- `deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json` records the
  reuse-first field names that parsers and saved searches depend on.
- `shop/server/observability/oci_monitoring.py` and
  `crm/server/observability/oci_monitoring.py` publish custom metrics in the
  `octo_apm_demo` namespace through the `telemetry-ingestion` endpoint.
