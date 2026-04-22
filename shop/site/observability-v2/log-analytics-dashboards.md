# Log Analytics dashboards

Artifacts live in `deploy/oci/log_analytics/`.

## Parsers (v2)

| name | feeds | key fields |
| --- | --- | --- |
| `octo-shop-v2` | Shop JSON stdout | Trace ID, Request ID, Workflow ID, DB Elapsed ms, Chaos Injected |
| `octo-crm-v2` | CRM JSON stdout | same contract |
| `octo-waf` | OCI WAF event logs | WAF Rule Name, Client IP, Request ID, Trace ID |
| `octo-chaos-audit` | CRM chaos admin logger | Event, Chaos Scenario, Target, Applied By |

## Saved searches

| file | purpose |
| --- | --- |
| `trace-drilldown.sql` | Full cross-service story for one Trace ID |
| `workflow-health.sql` | Requests, errors, p95 by workflow |
| `db-slowness-hotspots.sql` | Top slow SQL by workflow |
| `waf-vs-app-errors.sql` | Join WAF detections with app 5xx |
| `chaos-vs-organic.sql` | Split errors by `Chaos Injected` |

## Dashboards

- `workflow-command-center.json` — latency heat-map × workflows, chaos
  overlay, WAF correlation, parameterised trace drill-down widget.

## Apply

```bash
for p in deploy/oci/log_analytics/parsers/*.json; do
  oci log-analytics parser upload \
    --namespace-name "$OCI_LA_NAMESPACE" --from-json "file://$p"
done
for q in deploy/oci/log_analytics/searches/*.sql; do
  name=$(basename "$q" .sql)
  oci log-analytics saved-search upload \
    --namespace-name "$OCI_LA_NAMESPACE" \
    --display-name "$name" --query-string "$(cat "$q")"
done
```
