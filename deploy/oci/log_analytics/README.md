# Log Analytics artefacts (v2 enrichment)

Everything here is **additive** — existing parsers, sources, and dashboards are
untouched. First make sure OCI Logging can reach Log Analytics:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
OCI_LOG_GROUP_ID=<OCI_LOG_GROUP_OCID> \
LA_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
./deploy/oci/ensure_log_analytics_connectors.sh
```

The current private demo tenancy has no available `service-connector-count`
quota, so the helper dry-runs and does not mutate existing shared
connectors.

Folder layout:

```
fields/         Reuse-first field map for parsers and searches
parsers/        JSON parser definitions (one per log source)
sources/        Source definitions that bind parsers to OCI Logging groups
searches/       Saved searches (.sql + metadata.json)
dashboards/     Dashboard JSON descriptors
```

The reuse-first field map is
`fields/octo-apm-field-reuse-map.json`. Keep it aligned with parser display
names and saved-search fields before changing dashboards or scheduled rules.

## Local validation

Run the local asset gate before parser, saved-search, dashboard, or scheduled
rule import:

```bash
python3 -m pytest -q \
  tests/test_log_analytics_detection_reliability.py \
  tests/test_observability_asset_contract.py \
  tests/test_log_analytics_attack_assets.py
```

Required saved searches for the Phase 1 observability contract:

- `service-trace-log-coverage.sql`
- `checkout-payment-correlation.sql`
- `auth-login-correlation.sql`
- `genai-assistant-llmetry.sql`
- `service-error-triage.sql`
- `db-slowness-hotspots.sql`
- `melts-collection-completeness.sql`
- `oke-checkout-payment-correlation.sql`
- `oke-onm-ingestion-health.sql`

The local gate validates source files only. Live OCI import/deployment remains a
separate operator action and this phase does not run Terraform apply or create
OCI resources.

`apply_saved_searches_and_dashboards.py` is dry-run by default. Dry-run is
offline-safe: it compiles local saved-search, dashboard, and scheduled-rule
payloads without calling OCI lookup APIs. Use `--apply` only after reviewing
the generated actions and confirming the target namespace/compartment.

Verify the OCTO field map before parser/source import. The helper checks the
target namespace and reuses existing fields by display name or internal field
name. It only calls `upsert-field` for manifest entries explicitly marked
`createIfMissing: true`; the current emdemo map has no required creates.

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
LA_NAMESPACE=<LA_NAMESPACE> \
./deploy/oci/log_analytics/apply_fields.sh --dry-run
```

## Parsers shipped

| parser | log source | purpose |
| --- | --- | --- |
| `octo-shop-v2` | Shop app JSON stdout | app logs enriched with workflow + trace + chaos |
| `octo-crm-v2` | CRM app JSON stdout | same schema, separate tenancy tag |
| `octo-waf` | OCI WAF event logs | maps rule, client ip, request id |
| `octo-chaos-audit` | CRM `chaos_audit` logger | trail of apply / clear actions |
| `octo-db-audit` | DB `audit_logs` export | trace_id preserved for pivoting |

`octo-shop-v2` and `octo-crm-v2` also extract the private demo attack-lab
contract:

* `Attack ID`, `Attack Stage`, `MITRE Technique ID`, `MITRE Tactic`
* `Host IP Address (Client)`, `Source IP`, `Server Address`, `Destination IP`,
  `Destination Port`, `Network Protocol`
* `OSQuery Query`, `OSQuery Finding`, `OSQuery SQL`, `OSQuery Result Count`
* `Security Severity`, `LOTL Binary`, `Instance OCID`, `Host Name`

## Private Demo attack-lab assets

Saved searches:

* `melts-collection-completeness.sql` — one-page MELTS collection check
  across app logs, connector rows, trace/span fields, workflows, orders,
  payment gateway ids, promoted OKE stdout aliases, and OKE Kubernetes
  ingestion.
* `oke-checkout-payment-correlation.sql` — OKE-specific checkout timeline
  over `SOC Application Logs`, scoped to `octo-drone-shop-oke`,
  `enterprise-crm-portal-oke`, and `octo-java-app-server-oke`, with order,
  payment gateway, payment rail, Java sidecar, and CRM sync fields.
* `attack-lab-detections.sql` — MITRE detections grouped by attack id,
  tactic, technique, source, destination, and OSQuery finding.
* `attack-lab-trace-timeline.sql` — ordered trace/log timeline for one
  `Attack ID` or `Trace ID`.
* `osquery-attack-findings.sql` — Cloud Guard/OSQuery findings by host,
  instance OCID, query name, and severity.
* `checkout-security-checks.sql` — real add-to-cart guardrails from
  `ATTACK:MASS_ASSIGN`, `ATTACK:RATE_LIMIT`, and `ATTACK:IDOR` spans/logs.
* `payment-gateway-timeline.sql` — real checkout gateway steps keyed by
  `Payment Gateway Request ID`, trace id, and order id.
* `payment-risk-decisions.sql` — authorization outcomes, antifraud decisions,
  processor decisions, and risk-score pivots.
* `user-order-action-correlation.sql` — password-login, checkout, order,
  payment, and guardrail pivots by authenticated user id, order id, and trace.

Dashboard:

* `attack-lab-command-center.json` — attack detections, trace timeline,
  OSQuery findings, trace drilldown, and WAF/app-error widgets.
* `payment-security-command-center.json` — payment gateway timeline,
  antifraud decisions, checkout security checks, and trace drilldown.

## Apply local saved searches, dashboards, and scheduled rules

Use the local apply helper for the repo-owned Log Analytics searches and the
two command-center dashboards. It is dry-run by default, uses display-name
upserts, and does not create Service Connector Hub resources or run Terraform.

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
./deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py

OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
./deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py --apply
```

What the helper applies:

| asset | result |
| --- | --- |
| Saved searches | every `searches/*.sql` as `management-saved-search` content |
| Dashboards | `Workflow Command Center` and `Attack Lab Command Center` |
| Scheduled detection rules | seven `rule-*.sql` searches as Log Analytics `SAVED_SEARCH` rules: five workshop threat rules plus two OKE operations rules |
| Rule metrics | `octo_log_analytics_detections` namespace, `octo-apm-demo` resource group |

To refresh only the scheduled detection rules after saved searches already
exist:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
./deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py \
  --only-detection-rules --apply
```

## Scoped Octo APM workshop deployment

The OCI Log Analytics detection content remains owned by
`oci-log-analytics-detections`, but this repo can deploy the Octo-only workshop
slice directly. All tenancy-specific values must be supplied through variables;
do not commit resolved OCIDs, hostnames, IP addresses, or secret paths.

```bash
DETECTIONS_REPO=../oci-log-analytics-detections \
DETECTIONS_PYTHON=<PYTHON_WITH_OCI_SDK> \
OCI_PROFILE=<OCI_PROFILE> \
OCI_REGION=<OCI_REGION> \
OCI_COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
LOG_ANALYTICS_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --field-audit

DETECTIONS_REPO=../oci-log-analytics-detections \
DETECTIONS_PYTHON=<PYTHON_WITH_OCI_SDK> \
OCI_PROFILE=<OCI_PROFILE> \
OCI_REGION=<OCI_REGION> \
OCI_COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
LOG_ANALYTICS_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --dry-run

DETECTIONS_REPO=../oci-log-analytics-detections \
DETECTIONS_PYTHON=<PYTHON_WITH_OCI_SDK> \
OCI_PROFILE=<OCI_PROFILE> \
OCI_REGION=<OCI_REGION> \
OCI_COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
LOG_ANALYTICS_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
OCI_LOG_ANALYTICS_READ_TIMEOUT_SECONDS=<SECONDS> \
./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --deploy --generate-data --ingest-data --verify
```

The wrapper runs:

* `setup_log_sources.py --octo-apm-only --field-audit` as a read-only
  namespace preflight. Exact display-name matches are reused by the parser, and
  only missing Octo workshop fields are created by the deploy step.
* `setup_log_sources.py --octo-apm-only` for the reuse-first `SOC Application Logs` field/parser/source contract.
* `octo_apm_workshop.py --generate-data` for `octo_apm_workshop_application_logs.jsonl`.
* `ingest_test_data.py --file octo_apm_workshop_application_logs.jsonl`.
* `detection_rule_creator.py --write-default` for metadata-only scheduled-search specs.
* `deploy_dashboard.py --dashboard-name "OCI-DEMO: Octo APM Demo Dashboard"`.
* `verify_deployed_dashboards.py --dashboard-name "OCI-DEMO: Octo APM Demo Dashboard"`.
* `verify_octo_apm_detection_rules.py` for the five deployable rule queries.

`DETECTIONS_PYTHON` is optional when the default `python3` already has the OCI
SDK. Set it to an explicit runtime when invoking from shells that resolve to a
different Python. `OCI_LOG_ANALYTICS_READ_TIMEOUT_SECONDS` is optional and is
useful for large or slow Log Analytics namespaces during field inventory reads.

No OCI alarms are created by default. The workshop wrapper exports reviewable
specs; the local apply helper promotes seven scheduled-search-safe tasks into
Log Analytics: five workshop threat rules plus two OKE operations rules.

Local saved-search mirrors of the five deployable Octo threat rules are
versioned in `searches/rule-*.sql` together with the OKE operations rule
queries. `payment-threats.sql` mirrors the workshop payment threat-hunting
query. These queries use mapped Log Analytics display names, avoid `countif`,
keep scheduled-rule dimensions at three or fewer, and keep dashboard
`stats by` groups at four fields or fewer.
The local reliability test also checks that each `rule-*.sql` metric alias and
dimension list matches the scheduled-rule metadata used by the apply helper.

What this creates or refreshes:

| asset | result |
| --- | --- |
| Fields | exact existing namespace display names are reused; only missing Octo APM workshop fields are created |
| Parser/source | `SOC Application JSON Parser` and `SOC Application Logs` |
| Test data | 21 days of scoped Octo APM workshop JSONL by default |
| Saved searches | 17 dashboard-ready Octo APM searches pinned to the 21-day workshop evidence window, including the trace investigation Link/Tiles view |
| Dashboard | `OCI-DEMO: Octo APM Demo Dashboard` |
| Detection rule specs | five metadata-only specs in `queries/detection_rule_specs.json` |
| Evidence | dashboard health JSON plus detection-rule query health JSON |

Live Connector Hub note:

* A Service Connector Hub source of kind `logging` always lands in Log
  Analytics as `OCI Unified Schema Logs`; OCI rejects a non-null
  `logSourceIdentifier` on that connector type. Use the
  `connector-live-log-coverage.sql` saved search for live connector records.
* The app emitters keep the normal structured fields in OCI Logging and also
  put a compact JSON envelope in the `Message` field so Log Analytics
  `jsonextract` can recover `trace_id`, `span_id`, `service_name`,
  `workflow_id`, `order_id`, and DB/payment pivots from connector-fed logs.
* `SOC Application Logs` remains the parser/source contract for direct
  Log Analytics ingestion and workshop data. It is not the source name shown
  for live OCI Logging connector records.
* In emdemo, the approved live app-log route currently reuses an existing
  Connector Hub path from the OCTO OCI Logging group to the `octo-emdemo-logs`
  Log Analytics group. Service Connector quota is still full
  (`used=7`, `available=0`), so new connector creation remains blocked.
* OKE ONM logs do not use Connector Hub. The ONM Fluentd output writes
  directly to Log Analytics and stamps `Kubernetes Cluster Name =
  octo-apm-demo-oke`; OKE health searches and scheduled rules should filter on
  that cluster name, not only on `Namespace = oci-onm`.
* OKE app stdout is annotated into `SOC Application Logs`. The current Shop
  and CRM JSON formatters emit both dotted OpenTelemetry-style keys and
  parser-friendly aliases such as `order_id`,
  `payment_gateway_request_id`, `payment_gateway_step`,
  `payment_processor_response_code`, and `java_apm_service_name`. The scoped
  SOC parser/source refresh in emdemo promoted these through 138 field maps
  without creating new Log Analytics fields.

Cloud Guard OSQuery result ingestion:

```bash
DRY_RUN=false ATTACK_ID=<attack-id> ADHOC_QUERY_ID=<adhoc-query-ocid> \
OCI_LOG_ID=<custom-log-ocid> COMPARTMENT_ID=<compartment-ocid> \
./deploy/oci/export_osquery_results_to_logging.sh
```

## Correlation contract

Every record should expose at least one of:

* `Trace ID` (W3C traceparent) — preferred
* `Request ID` (`X-Request-Id`) — glue for WAF ↔ app
* `Workflow ID` + time window — business-level fallback

For the Octo APM workshop, the high-value pivots are:

| pivot | generated from | use |
| --- | --- | --- |
| `Trace ID` | `trace_id`, `traceId`, `oracleApmTraceId` | APM Trace Explorer to Log Analytics |
| `Span ID` / `Parent Span ID` | `span_id`, `spanId`, `oracleApmSpanId`, `parentSpanId` | span link analysis |
| `Attack ID` / `Run ID` | `security.attack.id`, `run_id` | complete attack storyline |
| `API Gateway Request ID` | `oci.api_gateway.request_id` | API Gateway edge-policy decision pivot |
| `Payment Redirect URL` / `Payment Interception` | `payment.redirect.url`, `payment.interception.detected` | payment attack rules |
| `Payment Gateway Request ID` / `Transaction ID` | `payment.gateway.request_id`, `payment.network.transaction_id` | payment-to-trace and network authorization pivots |
| `Response Code` / `Gateway ID` | `payment.processor.response_code`, `payment.processor.gateway_code` | authorization approval/decline/timeout rules |
| `Workflow Step` / `Process Phase` / `Event Status` / `Elapsed Time (Gateway)` | `payment.gateway.step`, `payment.gateway.phase`, `payment.gateway.step_status`, `payment.gateway.step_latency_ms` | gateway timeline and stuck/slow phase triage |
| `Method` / `ORDER_AMOUNT` / `BillingCurrency` | `payment.method`, `payment.amount_minor_units`, `payment.currency` | payment method, amount, and currency pivots |
| `Error Type` / `Latency` / `Flow` | `payment.verification.error_code`, `payment.processor.error_code`, `payment.processor.latency_ms`, `payment.network.route` | antifraud, processor, and rail failure hunting |
| `Result` / `Security Result` / `Program` / `Flow Code` | `payment.card.avs.result`, `payment.card.cvv.result`, `payment.3ds.program`, `payment.3ds.eci` | card security-control checks |
| `Order ID` / `Source Order ID` | `orders.order_id`, `order_id`, `source_order_id` | join checkout, CRM order sync, invoices, shipping, and payment events |
| `Session ID` / `Application Hash` / `Session` | `assistant.session_id`, `llm.prompt.hash`, `langfuse.session.id` | join APM assistant spans, Log Analytics rows, ATP LLMetry, and Langfuse |
| `Instance OCID` / `OSQuery Query` | `cloud.instance.id`, `osquery.query` | compromised host and OSQuery evidence |

Saved searches rely on this contract; keep it stable.

## APM and Log Analytics saved-query set

Trace Explorer saved-query descriptors live in
`deploy/oci/apm/saved-queries/` and pair with these Log Analytics searches:

| APM saved query | Log Analytics search | primary join |
| --- | --- | --- |
| `octo-apm-checkout-end-to-end` | `checkout-payment-correlation.sql` | `TraceId` -> `Trace ID`, then `Payment Gateway Request ID` / `Order ID` |
| `octo-apm-payment-java-sidecar` | `checkout-payment-correlation.sql`, `oke-checkout-payment-correlation.sql`, `service-error-triage.sql` | `TraceId`, Java sidecar fields, payment rail fields |
| `octo-apm-db-slow-spans` | `db-slowness-hotspots.sql`, `trace-drilldown.sql` | `TraceId`, `DB Statement`, `DbOracleSqlId` |
| `octo-apm-login-auth-flow` | `auth-login-correlation.sql` | `TraceId`, `Request ID`, `User ID` |
| `octo-apm-assistant-genai-llmetry` | `genai-assistant-llmetry.sql` | `TraceId`, `Session ID`, `Application Hash` |
| `octo-apm-service-errors` | `service-error-triage.sql` | `TraceId`, service, status/error fields |
| `octo-apm-platform-workflows` | `service-trace-log-coverage.sql` | service, run, trace, and span coverage |
| `octo-apm-trace-drilldown` | `trace-drilldown.sql` | one `TraceId` / `Trace ID` |

Apply APM saved queries only after confirming the target compartment has the
`manage management-saved-search` permission and the APM provider id expected
by the region:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
APM_DOMAIN_ID=<APM_DOMAIN_OCID> \
./deploy/oci/apm/apply_saved_queries.sh --dry-run
```

## OCI CLI mapping

The JSON files in this directory are versioned descriptors for the demo
contract. The current OCI CLI exposes Log Analytics creation through:

- `oci log-analytics parser upsert-parser`
- `oci log-analytics source upsert-source`
- `oci log-analytics content-import import-custom-content`
- `oci log-analytics query search`

Use these commands, or the Console, to bind the parser/source mapping
after the Service Connector is active.

## Detection rule promotion

By default, `deploy_octo_apm_workshop.sh --deploy` exports **metadata-only**
detection-rule specs. No scheduled searches or alarms are created automatically.

To review and validate detection rules:

```bash
# 1. Review exported rule specs
DETECTIONS_REPO=../oci-log-analytics-detections \
  python3 scripts/octo_apm_workshop.py --summary

# 2. Rebuild the metadata-only specs
DETECTIONS_REPO=../oci-log-analytics-detections \
OCI_PROFILE=<OCI_PROFILE> \
OCI_REGION=<OCI_REGION> \
OCI_COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
  python3 scripts/detection_rule_creator.py --write-default

# 3. Prove the five deployable Octo threat-rule queries against live data
OCI_PROFILE=<OCI_PROFILE> \
OCI_REGION=<OCI_REGION> \
OCI_COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
  python3 scripts/verify_octo_apm_detection_rules.py --lookback 21d
```

Detection rules cover:

- API Gateway threat signals by attack and trace
- Compromised VM evidence by attack, host role, and VM indicator
- Java payment errors by trace and response code
- Payment interception by attack, trace, and provider
- Payment redirect by attack, trace, and redirect target
- API Gateway edge-policy decisions and threat signals
- OKE ONM log-sample presence by log source and namespace
- OKE collector errors by pod and container

## OS-level log collection

The Service Connector created by `ensure_log_analytics_connectors.sh`
collects both application and OS-level logs by default:

| Log display name | Source | Purpose |
| --- | --- | --- |
| `octo-demo-os` | OCI Agent custom log | General OS events |
| `octo-demo-os-syslog` | OCI Agent syslog | System-level messages, service events |
| `octo-demo-os-audit` | OCI Agent audit | auditd events — privilege escalation, suspicious commands |
| `octo-security` | Application security logger | App-layer security events |
| `octo-demo-cloudguard-raw` | Cloud Guard events | OCI-native threat detection |
| `octo-demo-cloudguard-query-results` | OSQuery results export | Instance-level IOC findings |

OS logs are critical for detecting:

- Living-off-the-land (LOTL) binary execution
- Privilege escalation attempts
- Unauthorized SSH access
- File integrity monitoring violations
- Suspicious process spawning
