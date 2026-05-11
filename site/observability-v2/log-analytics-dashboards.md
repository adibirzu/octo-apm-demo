# Log Analytics dashboards

Artifacts live in `deploy/oci/log_analytics/`.

The private Compute stack can create the OCI Logging log group, app/OS/
container/WAF logs, Log Analytics log group, and Service Connector Hub
routes when the required IAM, agent, and connector toggles are enabled.
Parser, source, saved-search, and dashboard asset upload remains an
operator step after the connectors are active.

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
| `octo-shop-v2` | Shop JSON stdout | Trace ID, Request ID, Workflow ID, DB Elapsed ms, Chaos Injected, payment gateway steps, checkout security checks |
| `octo-crm-v2` | CRM JSON stdout | same contract |
| `octo-waf` | OCI WAF event logs | WAF Rule Name, Client IP, Request ID, Trace ID |
| `octo-chaos-audit` | CRM chaos admin logger | Event, Chaos Scenario, Target, Applied By |

Additional private demo fields to extract from app/container logs:

| field | source | purpose |
| --- | --- | --- |
| `java_apm.path` | Shop sidecar client logs | Java app-server endpoint called |
| `java_apm.status_code` | Shop sidecar client logs | HTTP status from the Java sidecar |
| `java_apm.latency_ms` | Shop sidecar client logs | Downstream app-server latency |
| `payment.provider` | Checkout/payment simulation logs | Active gateway simulator |
| `payment.method` | Checkout/payment simulation logs | credit card, Apple Pay, Google Pay, or other safe simulator method |
| `payment.status` | Checkout/payment simulation logs | authorized, declined, timeout |
| `payment.risk_score` | Checkout/payment simulation logs | demo fraud/risk score |
| `payment.gateway.request_id` | Payment gateway emulator logs | stable join key across order, trace, CRM, and gateway step records |
| `payment.gateway.step` | Payment gateway emulator logs | ordered gateway step such as `gateway_card_tokenization` or `merchant_authorization_result` |
| `payment.gateway.phase` | Payment gateway emulator logs | ingress, card token, wallet token, verification, processor, network, or merchant response |
| `payment.verification.decision` | Java antifraud verification logs | approved, review, declined |
| `payment.processor.decision` | Java processor simulator logs | processor authorization decision |
| `payment.amount_bucket` | Checkout/payment simulation logs | low-cardinality amount range |
| `payment.decision_source` | Checkout/payment simulation logs | python-simulator or java-app-server |
| `payment.java_app_server.status` | Checkout/payment simulation logs | sidecar ok/disabled/unreachable |
| `auth.user_id` / `auth.role` | Login, profile, checkout, and order logs | user-to-order correlation for DB audit rows and checkout actions |
| `auth.success` / `auth.failure_reason` | Login logs | password login success/failure and rate-limit investigation |
| `oci.api_gateway.request_id` | Attack lab/API Gateway logs | edge request pivot for route-policy decisions |
| `oci.api_gateway.route` | Attack lab/API Gateway logs | public or private route that handled the request |
| `oci.api_gateway.action` | Attack lab/API Gateway logs | allow, deny, throttle, or backend_error |
| `oci.api_gateway.policy.decision` | Attack lab/API Gateway logs | auth, quota, route, or backend policy outcome |
| `oci.api_gateway.latency_ms` | Attack lab/API Gateway logs | edge-to-backend decision latency |
| `security.attack.id` | Attack lab logs | groups one full attack run |
| `security.attack.stage` | Attack lab logs | kill-chain stage for timeline widgets |
| `security.check.name` | Checkout guardrail logs | cart validation check: `mass_assign`, `rate_limit`, or `idor` |
| `security.endpoint` | Checkout guardrail logs | endpoint where the guardrail fired, for example `/api/cart/add` |
| `cart.product_id` / `cart.quantity` | Checkout guardrail logs | product and quantity involved in a cart security event |
| `owasp.category` | Checkout guardrail logs | OWASP category for the guardrail event |
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
| `chaos-vs-organic.sql` | Split errors by `Chaos Injected` |
| `api-gateway-edge-detections.sql` | API Gateway route-policy detections by attack id and trace id |
| `attack-lab-detections.sql` | MITRE detections by attack id, tactic, technique, and source |
| `attack-lab-trace-timeline.sql` | Full attack timeline by `Attack ID` or `Trace ID` |
| `osquery-attack-findings.sql` | OSQuery findings by host, instance, query, and severity |
| `payment-gateway-timeline.sql` | Ordered real payment gateway steps by gateway request id, trace id, or order id |
| `payment-risk-decisions.sql` | Payment authorization and antifraud outcomes by method, network, status, and risk |
| `checkout-security-checks.sql` | Real cart/checkout security guardrails by check, endpoint, source IP, product, and trace |
| `user-order-action-correlation.sql` | Login, checkout, order, payment, and guardrail pivots by user id, order id, and trace |

## Dashboards

- `workflow-command-center.json` — latency heat-map × workflows, chaos
  overlay, WAF correlation, parameterised trace drill-down widget.
- `attack-lab-command-center.json` — attack-lab command center with
  API Gateway route-policy evidence, MITRE detections, APM trace timeline,
  OSQuery findings, and WAF/app error correlation.
- `payment-security-command-center.json` — payment gateway timeline,
  payment risk decisions, checkout security checks, user/order correlation,
  and trace drilldown.

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
default connector list now includes the app, stdout, OS, security, chaos,
WAF, Cloud Guard raw, and Cloud Guard query result logs:

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

May 11, 2026 `emdemo` check:

- OCI Logging is receiving fresh Shop/CRM records with
  `oracleApmTraceId`, `trace_id`, `span_id`, `service.name`,
  `http.url.path`, `http.status_code`, and DB target metadata.
- Log Analytics can execute queries in namespace `axfo51x8x2ap`, but
  `Log Source = octo-shop-app-json` returned `0` rows for the last hour.
- No custom OCTO source/parser named `octo-*` is currently registered in Log
  Analytics for this compartment.
- The shared connector `all-service-logs` targets Log Analytics but does not
  include the OCTO app log group from the current Compute deployment. Do not
  mutate that shared connector for OCTO DEMO without explicit operator approval.

Operational conclusion: dashboards in `deploy/oci/log_analytics/` are ready
as versioned assets, and the apps produce the required fields in OCI Logging.
Real Log Analytics dashboard data requires either Service Connector quota for a
new OCTO-owned route or an approved consolidation of an existing OCTO-owned
connector plus source/parser registration.

The OCI CLI command surface for Log Analytics content is:

- parser create/update: `oci log-analytics parser upsert-parser`
- source create/update: `oci log-analytics source upsert-source`
- exported custom content import: `oci log-analytics content-import import-custom-content`
- query smoke test: `oci log-analytics query search`

Recommended enhancement: add an idempotent
`deploy/oci/apply_log_analytics_assets.sh` helper that converts these repo
descriptors into the current OCI CLI upsert/import payloads, registers the
source/parser mapping, imports dashboards or saved searches, and then runs
a trace-id query smoke test for fresh Shop and CRM records.
