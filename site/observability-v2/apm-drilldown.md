# APM drill-down

Every span inherits `workflow.id`, `workflow.step`, and `service.name`
attributes. Chaos-injected faults register as span *events* — not
wrapping spans — so latency budgets still reflect reality.

## Provisioning the APM Domain + RUM Web Application

A new tenancy needs both an APM Domain and a RUM Web Application before
traces/RUM events can be fully demonstrated. The terraform module
`deploy/terraform/modules/apm_domain` creates the APM Domain and reads
the generated public/private data keys:

```hcl
module "apm_domain" {
  source                       = "./modules/apm_domain"
  compartment_id               = var.compartment_id
  display_name                 = "octo-apm"
  web_application_display_name = "octo-drone-shop-web"
}
```

Outputs include `apm_data_upload_endpoint`, `rum_endpoint`,
`apm_public_datakey`, and `apm_private_datakey` (sensitive). The
`rum_web_application_id` output remains empty until the operator
registers the RUM web application in the OCI Console. The helper script
`deploy/oci/ensure_apm.sh` wraps `terraform plan/apply/print` and emits
the matching `export OCI_APM_*` lines for secret population.

RUM web application registration is still a Console step in this repo.
The app can emit browser beacons with the RUM endpoint and public data
key, but the web application object should be registered after apply so
RUM dashboards and naming are operator-friendly.

## Compute Stack Collection

The private Compute stack sets the APM endpoint and data keys on both
apps. Current coverage:

- FastAPI server spans with route, status, request, workflow, and runtime
  attributes.
- HTTPX client spans with W3C `traceparent` propagation for Shop to CRM
  calls.
- SQLAlchemy spans for database calls.
- Shop and CRM SQL spans include `DbStatement` and `DbOracleSqlId` to
  bridge into DB Management and Operations Insights.
- Process/runtime metrics are exported through OTLP metrics when APM is
  configured.
- RUM JavaScript is injected in Shop and CRM HTML when the public RUM
  settings are present.
- The private demo shop host can run `octo-java-app-server`, a Spring Boot
  sidecar instrumented with the OCI APM Java agent. Checkout and admin
  simulations call it so traces include Python -> Java app-server spans
  and the App Servers view receives JVM/app-server metrics.
- Java simulations include external HTTP errors, Oracle JDBC SQL errors,
  and attack-lab spans so the APM trace contains downstream app-server,
  external-service, and ATP evidence from one admin action.
- Payment simulation spans include `payment.provider`, `payment.status`,
  `payment.risk_score`, `payment.amount_bucket`,
  `payment.decision_source`, and `payment.java_app_server.status`.
- Payment gateway traces include Python gateway spans and Java sidecar
  span events for Google Pay tokenization, Apple Pay merchant validation,
  Visa Secure, Mastercard Identity Check, AVS/CVV results, processor
  response codes, and synthetic card-network transaction ids. All payment
  telemetry uses token hashes and card last4 only.
- Assistant spans include `gen_ai.*`, `llm.*`, `assistant.*`, and
  `langfuse.*` attributes so OCI APM traces, OCI Logging rows, ATP
  `llmetry_events`, and optional Langfuse observations can be compared by
  the same trace/session/hash keys.
- The admin Demo Storyboard emits a shop-to-payment-to-support path; the
  Attack Lab emits `security.attack.kill_chain` plus MITRE stage spans
  and Log Analytics correlation fields.

Post-deploy synthetic coverage is now handled by
`shop/tools/apm/octo-apm-demo-synthetic.spec.ts`. The recurring monitor path
asserts browser checkout for 12 fictional buyers buying 2-3 drones each,
token-safe payment gateway metadata, antifraud decision fields,
support-ticket creation, admin login, Java health, and attack-lab traces
before demo handoff.

## Operator goals

Drilldowns should let an operator start from any one of these entry points and
keep context:

- APM trace
- APM dashboard widget
- Log Analytics row
- `/api/observability/360` response
- DB Management or OPSI investigation

## Recommended widgets

Build query-based APM dashboard widgets around the golden workflows:

- checkout latency and error rate
- CRM sync latency and failure count
- AI assistant latency and downstream query load
- traces containing SQL spans or chaos events

These widgets should be the top-level navigation surface before an operator
opens Trace Explorer.

## Saved Trace Explorer Queries

The project ships versioned Trace Explorer saved-query descriptors in
`deploy/oci/apm/saved-queries/`. Apply them with
`deploy/oci/apm/apply_saved_queries.sh --dry-run` first, then `--apply` after
confirming `management-saved-search` IAM permissions and the APM provider id in
the target region.

Before any live OCI import, run the local source gate:

```bash
python3 -m pytest -q tests/test_observability_asset_contract.py tests/test_log_analytics_attack_assets.py
```

That gate checks the eight required descriptors: `assistant-genai-llmetry`,
`checkout-end-to-end`, `db-slow-spans`, `login-auth-flow`,
`payment-java-sidecar`, `platform-workflows`, `service-errors`, and
`trace-drilldown`. It does not create OCI resources or run Terraform apply.

Updated on **May 12, 2026** for `<OCI_PROFILE>`: eight APM provider saved queries are
active. Each saved query stores its Log Analytics pivot targets in
`drilldownConfig` and `freeformTags.log_analytics_pivots`.

The `<OCI_PROFILE>` provider id/name is `APM`:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
APM_SAVED_QUERY_PROVIDER_ID=APM \
APM_SAVED_QUERY_PROVIDER_NAME=APM \
./deploy/oci/apm/apply_saved_queries.sh --apply
```

| saved query | use first when |
| --- | --- |
| `OCTO APM - checkout end-to-end` | an order, CRM sync, or checkout latency issue is reported |
| `OCTO APM - payment Java sidecar` | card, Google Pay, Apple Pay, or Java app-server payment spans are slow or failed |
| `OCTO APM - DB slow spans` | Trace Explorer shows SQL/connect spans above the latency threshold |
| `OCTO APM - login/auth flow` | a user cannot sign in or session persistence is suspect |
| `OCTO APM - assistant GenAI LLMetry` | assistant, Select AI, OCI GenAI, Langfuse, or token usage needs investigation |
| `OCTO APM - service errors` | the app has 5xx, Java, assistant, gateway, or attack-lab errors |
| `OCTO APM - platform workflows` | load-control, browser-runner, async-worker, cache, object-pipeline, or remediator behavior needs inspection |
| `OCTO APM - trace drilldown` | a `Trace ID` was copied from Log Analytics, RUM, or an app response |

Each saved query records its matching Log Analytics pivot. The standard flow is
APM `TraceId` -> Log Analytics `Trace ID` -> specialized field such as
`Payment Gateway Request ID`, `Order ID`, `Session ID`, `Application Hash`,
`Request ID`, or `Attack ID`.

## Copy-paste trace URL

```
https://cloud.oracle.com/apm-traces/trace-explorer?region=${OCI_REGION}&apmDomainId=${OCI_APM_DOMAIN_OCID}&traceId=<TRACE_ID>
```

## Suggested trace filters

Use repeatable filters for the main demo flows:

- `serviceName = "octo-drone-shop"` for storefront traces
- `serviceName = "enterprise-crm-portal"` for catalog and sync traces
- `workflow.id = "checkout"` for cart-to-order flow
- `workflow.id = "crm-sync"` for order and catalog sync
- `has(attribute.DbOracleSqlId)` for database drilldown candidates
- `security.attack.id exists` for attack-lab kill-chain traces
- `serviceName = "octo-java-app-server"` for JVM/app-server and Java SQL
  simulation traces
- `spanName = "shop.assistant.genai"` for OCI GenAI calls
- `llm.prompt.hash exists` for assistant LLMetry correlation pivots
- `payment.gateway.request_id exists` for card, Apple Pay, Google Pay, and
  simulated network authorization traces
- `spanName startsWith "ATTACK:"` or `security.check.name exists` for cart
  guardrail detections that should also appear in Log Analytics

## Payment gateway drilldown

For checkout investigations, use `payment.gateway.request_id` as the stable
payment join key and `trace_id` as the cross-signal join key. A complete
happy-path trace should include browser checkout, Shop order creation,
gateway receipt, wallet/card tokenization, internal antifraud screening,
Java antifraud verification, Java processor authorization, network routing,
merchant authorization result, CRM order sync, and ATP write spans.

The simulator's emitted gateway step names are:

| method | ordered method-specific steps |
| --- | --- |
| credit card | `gateway_payment_received`, `card_data_received`, `gateway_card_tokenization`, `internal_antifraud_screening`, `card_network_routing` |
| Apple Pay | `gateway_payment_received`, `apple_pay_merchant_validation`, `wallet_token_received`, `gateway_token_decryption`, `network_token_cryptogram_validation`, `internal_antifraud_screening` |
| Google Pay | `gateway_payment_received`, `wallet_token_received`, `gateway_token_decryption`, `network_token_cryptogram_validation`, `internal_antifraud_screening` |

All methods then emit `verification_antifraud_request`,
`verification_antifraud_response`, `processor_authorization_request`,
`processor_authorization_response`, `network_authorization_routing`, and
`merchant_authorization_result`.

The operator API returns the stored gateway step timeline:

```text
GET /api/observability/payment-gateway/events?gateway_request_id=<PGW_REQUEST_ID>
GET /api/observability/payment-gateway/events?trace_id=<TRACE_ID>
```

Use the returned `gateway_request_id`, `trace_id`, `order_id`, `method`,
`provider`, `network`, `status`, `risk_score`, and step names as pivots into
APM Trace Explorer, OCI Logging, Log Analytics, CRM Orders, and ATP payment
tables. Declines and synthetic gateway faults should keep the same
correlation fields even when `payment_status` is not `paid`.

## Linking from a log row

Log Analytics renders every record with a `Trace ID` column; click it to
open the APM trace viewer. Conversely, the Coordinator's
`drilldown_pivot` node returns both the APM URL and a saved-search URL
as `evidence_links` on the incident.

## Linking from an APM span to logs

Use `oracleApmTraceId` as the stable join key between APM, OCI Logging,
and Log Analytics. Every app log row should carry these fields:

| field | source | purpose |
| --- | --- | --- |
| `oracleApmTraceId` | current OTel trace id | APM trace to Log Analytics search |
| `oracleApmSpanId` | current OTel span id | narrows to the emitting span when available |
| `traceparent` | W3C propagation header | preserves browser, Python, Java, and CRM continuity |
| `service.name` / `app.service` | OTel resource and app config | filters Shop, CRM, and Java app-server logs |
| `workflow_id` / `workflow_step` | workflow middleware | groups checkout, storyboard, and attack-lab paths |
| `request_id` / `correlation.id` | middleware | fallback pivot when a trace is sampled out |
| `payment.*` | checkout simulator | payment gateway demo pivots |
| `oci.api_gateway.*` | OCI API Gateway / attack-lab simulator | edge route-policy pivots |
| `java_apm.*` | Java sidecar client | app-server call status and latency |
| `assistant.*` / `llm.*` / `gen_ai.*` | Drone assistant | GenAI, guardrail, token, and prompt/response hash pivots |
| `langfuse.*` | Optional Langfuse OTLP export | compare Langfuse observation view with OCI APM spans |
| `security.attack.*` / `mitre.*` | Attack Lab | full kill-chain timeline pivots |
| `osquery.*` | Cloud Guard export helper | host-side detection evidence |

When building app or dashboard links, generate both directions:

```text
APM trace:
https://cloud.oracle.com/apm-traces/trace-explorer?region=${OCI_REGION}&apmDomainId=${OCI_APM_DOMAIN_OCID}&traceId=${TRACE_ID}

Log Analytics search:
Log Explorer query where oracleApmTraceId = '${TRACE_ID}' over the OCTO Log Analytics log group
```

In private demo, APM span details can show `app.log` span events even before
the durable Logging -> Service Connector -> Log Analytics route is active.
If the span **Logs** count is zero, verify the app image no longer emits
`OCI Logging put_logs failed: Unrecognized keyword arguments:
defaultloglevel`, then pivot by `oracleApmTraceId` in OCI Logging or Log
Analytics.

## Linking from a SQL span

When a trace contains `DbOracleSqlId`, use that attribute as the bridge into:

- DB Management Performance Hub / SQL Monitor for statement detail
- Operations Insights SQL Warehouse for historical aggregation

This is the fastest way to move from application latency to database evidence.

## Acceptance criteria

- operators can pivot from APM into Log Analytics using the trace id
- at least one checkout and one CRM sync trace contain valid SQL drilldown data
- `/api/observability/360` exposes the console URLs needed for the pivots
- the same workflow can be followed across APM, logs, and DB tooling without
  manual guesswork
- A Java sidecar trace produces App Server metrics for
  `octo-java-app-server`, not only generic JVM metrics with
  `Appserver=false`

## RUM

RUM sessions carry workflow/request context where available and the shop
loads `static/js/rum-advanced.js` for sanitized custom browser actions.
Same-origin API calls can receive RUM trace headers so checkout, cart,
and simulation clicks can be paired with backend traces; cross-origin
header injection remains disabled.

Synthetic browser runs set OCI RUM `apmrum.username` before the browser
agent is loaded. This populates the APM **Users** page with fictional
corporate-style users from the configured synthetic domain. The tracked
default is `apex.example.test`; private deployments may override the
domain from ignored deployment files. The custom RUM dimensions emitted
by the app are `synthetic_user_enabled` and `synthetic_user_domain`; raw
e-mail addresses are not copied into custom action payloads or app logs.
