# Log Analytics artefacts (v2 enrichment)

Everything here is **additive** — existing parsers, sources, and dashboards are
untouched. Apply by importing into OCI Log Analytics:

```bash
oci log-analytics parser upload \
  --namespace-name "$OCI_LA_NAMESPACE" \
  --from-json file://parsers/octo-shop-v2.json
```

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

## Correlation contract

Every record should expose at least one of:

* `Trace ID` (W3C traceparent) — preferred
* `Request ID` (`X-Request-Id`) — glue for WAF ↔ app
* `Workflow ID` + time window — business-level fallback

Saved searches rely on this contract; keep it stable.
