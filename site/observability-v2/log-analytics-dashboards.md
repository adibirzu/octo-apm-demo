# Log Analytics dashboards

Artifacts live in `deploy/oci/log_analytics/`.

The private Compute stack can create the OCI Logging log group, app/OS/
container/WAF logs, Log Analytics log group, and Service Connector Hub
routes when the required IAM, agent, and connector toggles are enabled.
Parser, source, saved-search, and dashboard asset upload remains an
operator step after the connectors are active.

Run the local asset gate before live OCI import or refresh:

```bash
python3 -m pytest -q tests/test_observability_asset_contract.py tests/test_log_analytics_attack_assets.py
```

The gate checks the reuse-first field map
`deploy/oci/log_analytics/fields/octo-apm-field-reuse-map.json`, the required
APM saved-query descriptors, dashboard widget references, Monitoring namespace
assumptions, and key saved searches including `service-trace-log-coverage`,
`checkout-payment-correlation`, `auth-login-correlation`,
`genai-assistant-llmetry`, `service-error-triage`, `db-slowness-hotspots`,
`melts-collection-completeness`, `oke-checkout-payment-correlation`, and
`oke-onm-ingestion-health`.

This validation is local-only. Live OCI import/deployment remains a separate
operator action and this phase does not run Terraform apply or create OCI
resources.

## Compute log feeds

| feed | source |
| --- | --- |
| App SDK logs | `octo-app`, with `oracleApmTraceId` and service metadata |
| Security events | `octo-security` |
| Chaos audit | `octo-chaos-audit` |
| Host logs | Oracle Cloud Agent Custom Logs Monitoring for OS, cloud-init, and install logs |
| Container logs | Podman/Docker stdout and stderr via unified agent log tailing |
| API Gateway events | OCI API Gateway access logs plus app-simulated route-policy events |
| WAF events | OCI WAF service log when WAF logging is enabled |
| Cloud Guard raw events | `<DEPLOYMENT_PREFIX>-cloudguard-raw` service log |
| Cloud Guard OSQuery results | `<DEPLOYMENT_PREFIX>-cloudguard-query-results`, plus normalized exports into `<DEPLOYMENT_PREFIX>-os` |

## Parsers (v2)

| name | feeds | key fields |
| --- | --- | --- |
| `octo-shop-v2` | Shop JSON stdout | Trace ID, Request ID, Workflow ID, DB Elapsed ms, Event Status |
| `octo-crm-v2` | CRM JSON stdout | same contract |
| `octo-waf` | OCI WAF event logs | Security Rule, Host IP Address (Client), Request ID, Trace ID |
| `octo-chaos-audit` | CRM chaos admin logger | Event, Event Types, Target, User ID |

Additional private demo fields to extract from app/container logs:

| field | source | purpose |
| --- | --- | --- |
| `java_apm.path` | Shop sidecar client logs | Java app-server endpoint called |
| `java_apm.status_code` | Shop sidecar client logs | HTTP status from the Java sidecar |
| `java_apm.latency_ms` | Shop sidecar client logs | Downstream app-server latency |
| `payment.provider` | Checkout/payment simulation logs | Active gateway simulator |
| `payment.status` | Checkout/payment simulation logs | authorized, declined, timeout |
| `payment.risk_score` | Checkout/payment simulation logs | demo fraud/risk score |
| `payment.amount_bucket` | Checkout/payment simulation logs | low-cardinality amount range |
| `payment.decision_source` | Checkout/payment simulation logs | python-simulator or java-app-server |
| `payment.java_app_server.status` | Checkout/payment simulation logs | sidecar ok/disabled/unreachable |
| `oci.api_gateway.request_id` | Attack lab/API Gateway logs | edge request pivot for route-policy decisions |
| `oci.api_gateway.route` | Attack lab/API Gateway logs | public or private route that handled the request |
| `oci.api_gateway.action` | Attack lab/API Gateway logs | allow, deny, throttle, or backend_error |
| `oci.api_gateway.policy.decision` | Attack lab/API Gateway logs | auth, quota, route, or backend policy outcome |
| `oci.api_gateway.latency_ms` | Attack lab/API Gateway logs | edge-to-backend decision latency |
| `security.attack.id` | Attack lab logs | groups one full attack run |
| `security.attack.stage` | Attack lab logs | kill-chain stage for timeline widgets |
| `mitre.technique_id` | Attack lab and OSQuery logs | MITRE ATT&CK technique pivot |
| `mitre.tactic` | Attack lab and OSQuery logs | tactic-level grouping |
| `client.address` / `source.ip` | Attack lab logs | entry source address |
| `server.address` | Attack lab logs | app server, LB, or host reached |
| `destination.ip` / `destination.port` | Attack lab logs | server-hop evidence |
| `attack.lotl_binary` | Attack lab logs | living-off-the-land binary candidate |
| `osquery.query` | OSQuery logs | saved/ad-hoc query name |
| `osquery.finding` | OSQuery logs | normalized detection summary |
| `osquery.sql` | OSQuery logs | OSQuery SQL used for the finding |

## Saved searches

| file | purpose |
| --- | --- |
| `trace-drilldown.sql` | Full cross-service story for one Trace ID |
| `workflow-health.sql` | Requests, errors, p95 by workflow |
| `db-slowness-hotspots.sql` | Top slow SQL by workflow |
| `waf-vs-app-errors.sql` | Join WAF detections with app 5xx |
| `chaos-vs-organic.sql` | Split errors by `Event Status` |
| `api-gateway-edge-detections.sql` | API Gateway route-policy detections by attack id and trace id |
| `attack-lab-detections.sql` | MITRE detections by attack id, tactic, technique, and source |
| `attack-lab-trace-timeline.sql` | Full attack timeline by `Attack ID` or `Trace ID` |
| `osquery-attack-findings.sql` | OSQuery findings by host, instance, query, and severity |
| `checkout-payment-correlation.sql` | Checkout, order, Java sidecar, and payment rail timeline by trace/order/gateway request |
| `oke-checkout-payment-correlation.sql` | OKE stdout checkout, wallet/card, gateway, Java sidecar, and CRM sync timeline over `SOC Application Logs` |
| `payment-gateway-security-triage.sql` | Token-safe gateway step, antifraud, processor, network, and Java sidecar triage |
| `payment-threats.sql` | Payment abuse detections aligned with the Octo workshop payment-threat query |
| `rule-api-gateway-threat-count.sql` | Local mirror of the deployable API Gateway threat detection rule |
| `rule-compromised-vm-count.sql` | Local mirror of the deployable compromised VM detection rule |
| `rule-java-payment-error-count.sql` | Local mirror of the deployable Java payment error detection rule |
| `rule-payment-interception-count.sql` | Local mirror of the deployable payment interception detection rule |
| `rule-payment-redirect-count.sql` | Local mirror of the deployable payment redirect detection rule |
| `rule-oke-onm-log-samples.sql` | OKE ONM ingestion-volume metric scoped to `octo-apm-demo-oke` |
| `rule-oke-collector-error-count.sql` | OKE collector error metric for `oci-onm` collector pods |
| `auth-login-correlation.sql` | Login/session traces mapped to user action and DB evidence |
| `genai-assistant-llmetry.sql` | Assistant, Select AI, OCI GenAI, Langfuse, and LLMetry troubleshooting |
| `oke-onm-ingestion-health.sql` | OKE ONM container, tcpconnect, and SOC app-log ingestion health scoped to `octo-apm-demo-oke` |
| `oke-kubernetes-trace-correlation.sql` | OKE Kubernetes log rows joined to service/trace/span fields for app pods |
| `service-trace-log-coverage.sql` | Per-service check that Log Analytics rows carry trace/span fields |
| `service-error-triage.sql` | Fast error search across app, Java, assistant, gateway, WAF, attack, and host evidence |

## Dashboards

- `workflow-command-center.json` — latency heat-map × workflows, chaos
  overlay, WAF correlation, parameterised trace drill-down widget.
- `attack-lab-command-center.json` — attack-lab command center with
  API Gateway route-policy evidence, MITRE detections, APM trace timeline,
  OSQuery findings, and WAF/app error correlation.
- `OCI-DEMO: Octo APM Demo Dashboard` — deployed from
  `oci-log-analytics-detections` for the full workshop view: RED metrics,
  trace/log/span correlation, DB spans, Java payment errors, API Gateway edge
  decisions, payment threats, OSQuery host evidence, and compromised VM pivots.

## Live private-demo status

Updated on **May 13, 2026** in the `<OCI_PROFILE>` profile:

| surface | live state |
| --- | --- |
| App readiness | `<SHOP_HOST>` and `<ADMIN_HOST>` return `ready=true`, ATP connected, APM configured, RUM configured, and logging configured through the preserved HTTPS load balancer |
| Saved searches | Octo APM Log Analytics searches are active, including checkout/payment correlation, login/auth correlation, GenAI LLMetry, service error triage, trace/log coverage, OKE ONM ingestion health, OKE Kubernetes trace correlation, and the deployable rule mirrors |
| Dashboards | `Workflow Command Center`, `Attack Lab Command Center`, and `OCI-DEMO: Octo APM Demo Dashboard` are active |
| Workshop verification | scoped Octo APM deployment verified `17/17` dashboard widget HITs and `5/5` detection-rule query HITs |
| Detection rules | seven Log Analytics `SAVED_SEARCH` rules are active: API Gateway threat, compromised VM, Java payment error, payment interception, payment redirect, OKE ONM log samples, and OKE collector errors |
| Rule metrics | scheduled rules stream to `octo_log_analytics_detections` with resource group `octo-apm-demo`; no OCI alarms are created by this repo helper |
| OKE scoping | OKE ONM searches and `OkeOnmLogSamples` require `Kubernetes Cluster Name = octo-apm-demo-oke`; namespace-only `oci-onm` filters are intentionally avoided because older clusters can share the same namespace name |
| OKE app stdout | Shop and CRM stdout now emits Log Analytics aliases for order, payment gateway, workflow, Java sidecar, and payment rail fields; the private demo SOC parser/source refresh promotes them through 138 field maps without adding duplicate fields |

Use the idempotent helper for refreshes:

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
LA_NAMESPACE=<LA_NAMESPACE> \
./deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py --apply
```

## Scoped workshop deployment

Use the wrapper when the workshop needs only the Octo fields, data, saved
searches, dashboard, and detection-rule specs. Keep every tenancy-specific
value in variables:

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
OCI_LOG_ANALYTICS_READ_TIMEOUT_SECONDS=<SECONDS> \
./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --deploy --generate-data --ingest-data --verify
```

`DETECTIONS_PYTHON` is optional when the default shell `python3` already has the
OCI SDK. Use `OCI_LOG_ANALYTICS_READ_TIMEOUT_SECONDS` only when a large target
namespace needs a longer Log Analytics field inventory read.

The scoped deploy creates or refreshes only the Octo workshop surface:

| asset | created or refreshed |
| --- | --- |
| Log Analytics fields | reuse-first dashboard/detection fields; exact existing namespace display names are reused before any field creation |
| Parser | `SOC Application JSON Parser`, scoped to the Octo field mappings used by Shop, CRM, Java payment, assistant, and OKE stdout logs |
| Source | `SOC Application Logs` bound to the parser |
| Synthetic evidence | `octo_apm_workshop_application_logs.jsonl` uploaded to the supplied LA log group |
| Saved searches/widgets | 17 Octo APM saved searches and dashboard widgets pinned to the 21-day workshop evidence window, including the trace investigation Link/Tiles view |
| Dashboard | `OCI-DEMO: Octo APM Demo Dashboard` |
| Detection rules | `queries/detection_rule_specs.json` metadata for the five deployable Octo rules |
| Live evidence | dashboard health JSON and detection-rule query health JSON |

For the live `test` Service Connector path, records from OCI Logging appear as
`OCI Unified Schema Logs`, not `SOC Application Logs`. The connector source is
kind `logging`, so OCI requires the target `logSourceIdentifier` to stay empty.
Use `connector-live-log-coverage.sql` to validate fresh records; it extracts
the trace, span, service, workflow, order, and DB pivots from the JSON envelope
that the apps place in the Log Analytics `Message` field. Use
`oke-checkout-payment-correlation.sql` when the entry point is an OKE checkout
trace and the desired join is order -> payment gateway -> Java sidecar -> CRM.

The workshop wrapper's detection-rule output is metadata-only. OCI alarm
activation is deliberately not part of the default workshop deploy. Scheduled
Log Analytics rule creation for the five deployable Octo threat rules plus
the two OKE operations rules is handled by
`deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py`.

The field audit is read-only. It does not substitute semantic aliases such as
`Service` for `Service Name`, because saved searches and dashboards reference
Log Analytics display names. Reusing differently named fields requires a
coordinated query/dashboard rewrite.

## Octo workshop field contract

The app logs must emit OpenTelemetry-compatible trace fields and normalized
attack evidence. The parser maps those raw JSON paths into dashboard-facing
Log Analytics fields:

| raw field | Log Analytics field | correlation use |
| --- | --- | --- |
| `trace_id`, `traceId`, `oracleApmTraceId` | `Trace ID` | APM trace to Log Analytics pivot |
| `span_id`, `spanId`, `oracleApmSpanId` | `Span ID` | span-level grouping |
| `parentSpanId` | `Parent Span ID` | link view parent/child span graph |
| `service.name` / `serviceName` | `Service Name` | app/service grouping |
| `service.namespace` | `Service Namespace` | workshop scope filter; expected value is supplied by the deployment |
| `request_id`, `requestId` | `Request ID` | edge/app request pivot |
| `workflow_id`, `workflow_step`, `run_id` | `Workflow ID`, `Workflow Step`, `Run ID` | business and attack-run grouping |
| `db.*` | `DB Target`, `DB Statement`, `DB Elapsed ms`, `DB Connection Name` | trace to database span drilldown |
| `java_apm.*` | `Java APM Path`, `Java APM Latency ms`, `Java APM Error Type` | Java sidecar/payment error correlation |
| `orders.order_id`, `order_id`, `source_order_id` | `Order ID`, `Source Order ID` | checkout, CRM sync, invoice, shipping, and payment joins |
| `assistant.*`, `llm.*`, `gen_ai.*`, `langfuse.*` | `Session ID`, `Provider`, `Model Version`, `Application Hash`, `Current Hash`, `Content Size In`, `Content Size Out`, `Session` | assistant traces, ATP LLMetry rows, and Langfuse observation pivots |
| `security.attack.*`, `mitre.*` | `Attack ID`, `Attack Stage`, `Security Severity`, `MITRE Tactic`, `MITRE Technique ID` | attack timeline and rule dimensions |
| `payment.*` | `Payment Provider`, `Payment Risk Score`, `Payment Gateway Request ID`, `Workflow Step`, `Process Phase`, `Elapsed Time (Gateway)`, `Method`, `ORDER_AMOUNT`, `BillingCurrency`, `Payment Network`, `Response Code`, `Gateway ID`, `Transaction ID`, `Error Type`, `Latency`, `Result`, `Security Result`, `Program`, `Flow Code`, `Flow`, `Payment Interception`, `Payment Redirect`, `Payment Redirect URL` | payment rail, gateway triage, and abuse detections |
| `oci.api_gateway.*` | `API Gateway Request ID`, `API Gateway Route`, `API Gateway Action`, `API Gateway Policy Decision`, `API Gateway Threat Signal` | public/private gateway edge decision pivots |
| `osquery.*`, `cloud.instance.id`, `host.*`, `process.command_line` | `OSQuery Query`, `OSQuery Finding`, `OSQuery SQL`, `Instance OCID`, `Host Name`, `Host Role`, `Compromised VM`, `Process Command Line` | host evidence and compromised VM pivots |

Correlation starts from `Trace ID`. From there, analysts can pivot to spans via
`Span ID` and `Parent Span ID`, to edge decisions via `API Gateway Request ID`,
to the attack story via `Attack ID` and `Run ID`, and to host evidence via
`Instance OCID` and `OSQuery Query`.

## APM saved-query pivots

Trace Explorer saved-query descriptors are versioned under
`deploy/oci/apm/saved-queries/`. They are paired with the Log Analytics
queries above so every high-volume troubleshooting entry point has a log pivot:

| APM query | LA pivot | relation proved |
| --- | --- | --- |
| `OCTO APM - checkout end-to-end` | `checkout-payment-correlation` | trace -> order -> payment gateway -> Java sidecar -> CRM sync |
| `OCTO APM - payment Java sidecar` | `checkout-payment-correlation`, `oke-checkout-payment-correlation`, `service-error-triage` | trace -> Java payment span -> processor/network fields |
| `OCTO APM - DB slow spans` | `db-slowness-hotspots`, `trace-drilldown` | trace -> SQL span -> Log Analytics DB fields |
| `OCTO APM - login/auth flow` | `auth-login-correlation` | trace -> request/user hash -> DB/session writes |
| `OCTO APM - assistant GenAI LLMetry` | `genai-assistant-llmetry` | trace -> assistant session -> LLMetry/Langfuse hashes |
| `OCTO APM - service errors` | `service-error-triage` | trace -> service -> route/status/error evidence |
| `OCTO APM - platform workflows` | `service-trace-log-coverage` | service -> run/workflow -> trace/log coverage |

## Live validation gates

Before promotion, run the CAP gate and then the target-tenancy gate with
variables only:

```bash
DETECTIONS_REPO=../oci-log-analytics-detections \
DETECTIONS_PYTHON=<PYTHON_WITH_OCI_SDK> \
OCI_PROFILE=<OCI_PROFILE_CAP> \
OCI_REGION=<OCI_REGION_CAP> \
OCI_COMPARTMENT_ID=<CAP_COMPARTMENT_OCID> \
LA_NAMESPACE=<CAP_LA_NAMESPACE> \
LOG_ANALYTICS_LOG_GROUP_ID=<CAP_LA_LOG_GROUP_OCID> \
./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --verify

DETECTIONS_REPO=../oci-log-analytics-detections \
DETECTIONS_PYTHON=<PYTHON_WITH_OCI_SDK> \
OCI_PROFILE=<OCI_PROFILE_TARGET> \
OCI_REGION=<OCI_REGION_TARGET> \
OCI_COMPARTMENT_ID=<TARGET_COMPARTMENT_OCID> \
LA_NAMESPACE=<TARGET_LA_NAMESPACE> \
LOG_ANALYTICS_LOG_GROUP_ID=<TARGET_LA_LOG_GROUP_OCID> \
OCI_LOG_ANALYTICS_READ_TIMEOUT_SECONDS=<SECONDS> \
./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --deploy --generate-data --ingest-data --verify
```

The verification step checks the dashboard widget queries and the five
deployable Octo detection-rule queries. A successful release has one deployed
dashboard, 17/17 widget HITs, and 5/5 detection-rule query HITs.

The local `rule-*.sql` searches include the five deployable workshop rules from
`oci-log-analytics-detections` plus the two OKE operations rules maintained by
this repo. Keep them scheduled-rule-safe: no dashboard-only commands, no
`countif`, and at most three dimensions in the final `stats by` clause.

## Troubleshooting quick pivots

Use these saved searches when a dashboard is present but data looks missing or
incomplete:

| Symptom | Search | What it proves |
| --- | --- | --- |
| OCI Logging connector path has no app rows | `connector-live-log-coverage.sql` | Connector-fed `OCI Unified Schema Logs` contain app JSON envelopes with trace, span, service, workflow, order, and DB fields. |
| OKE app logs appear in Kubernetes but not Log Analytics | `oke-onm-ingestion-health.sql` | ONM container/tcpconnect ingestion is fresh and scoped to the expected OKE cluster. |
| OKE checkout trace has spans but no promoted payment rows | `oke-checkout-payment-correlation.sql` | `SOC Application Logs` rows carry `Trace ID`, `Order ID`, `Payment Gateway Request ID`, Java sidecar, and payment rail fields. |
| APM trace exists but log drilldown is empty | `service-trace-log-coverage.sql` | Each service emits `Trace ID` and `Span ID` into Log Analytics after parser promotion. |
| Admin assistant or Select AI is slow or refused | `genai-assistant-llmetry.sql` | Assistant session, guardrail, provider/model, prompt/response hashes, Langfuse, and trace pivots are present without raw prompt content. |

For admin-only security checks, start with `genai-assistant-llmetry.sql` and
then pivot by `coordinator.scope.enforced`, `coordinator.auth.mode`,
`oci.auth.mode`, `Session ID`, `Trace ID`, and `Application Hash`.

## Private Demo attack lab ingestion

The admin **Attack Lab** button emits app logs with `security.attack.id`
and `oracleApmTraceId`. Cloud Guard ad-hoc OSQuery results can be pulled
into the same OCI custom log so Service Connector Hub can route them to
Log Analytics with the same parser contract:

```bash
DRY_RUN=false ATTACK_ID=<attack-id> ADHOC_QUERY_ID=<adhoc-query-ocid> \
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
OCI_LOG_ID=<custom-log-ocid> \
./deploy/oci/export_osquery_results_to_logging.sh
```

## Apply

Terraform does not currently bind a Log Analytics source name on the
Service Connector Hub `loggingAnalytics` target. Register or validate the
LA source/parser mapping after the connector exists.

```bash
OCI_CLI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
OCI_LOG_GROUP_ID=<OCI_LOG_GROUP_OCID> \
LA_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
./deploy/oci/ensure_log_analytics_connectors.sh
```

In the current private demo tenancy the helper discovers the requested OCTO logs but
does not create a connector because `service-connector-count` availability
is `0`. It intentionally avoids changing existing shared connectors. The
current private demo app-log path reuses an existing approved Connector Hub route
from the OCTO OCI Logging group into the private demo Log Analytics
group. Connector-fed records appear as `OCI Unified Schema Logs`; use
`connector-live-log-coverage.sql` to extract the app JSON envelope from
`Message`. The default connector list now includes the app, stdout, OS,
security, chaos, WAF, Cloud Guard raw, and Cloud Guard query result logs:

```text
octo-app
<DEPLOYMENT_PREFIX>-app-stdout
<DEPLOYMENT_PREFIX>-os
octo-security
octo-chaos-audit
<DEPLOYMENT_PREFIX>-waf
<DEPLOYMENT_PREFIX>-cloudguard-raw
<DEPLOYMENT_PREFIX>-cloudguard-query-results
```

The OCI CLI command surface for Log Analytics content is:

- parser create/update: `oci log-analytics parser upsert-parser`
- source create/update: `oci log-analytics source upsert-source`
- exported custom content import: `oci log-analytics content-import import-custom-content`
- query smoke test: `oci log-analytics query search`

Use `deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py` for
the saved-search, dashboard, and scheduled-rule surface. Parser/source binding
remains separate because it depends on the target tenancy's active OCI Logging
to Log Analytics connector.
