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
parsers/        JSON parser definitions (one per log source)
sources/        Source definitions that bind parsers to OCI Logging groups
searches/       Saved searches (.sql + metadata.json)
dashboards/     Dashboard JSON descriptors
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
* `Client IP`, `Source IP`, `Server Address`, `Destination IP`,
  `Destination Port`, `Network Protocol`
* `OSQuery Query`, `OSQuery Finding`, `OSQuery SQL`, `OSQuery Result Count`
* `Security Severity`, `LOTL Binary`, `Instance OCID`, `Host Name`

## Private Demo attack-lab assets

Saved searches:

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

Saved searches rely on this contract; keep it stable.

## OCI CLI mapping

The JSON files in this directory are versioned descriptors for the demo
contract. The current OCI CLI exposes Log Analytics creation through:

- `oci log-analytics parser upsert-parser`
- `oci log-analytics source upsert-source`
- `oci log-analytics content-import import-custom-content`
- `oci log-analytics query search`

Use these commands, or the Console, to bind the parser/source mapping
after the Service Connector is active.
