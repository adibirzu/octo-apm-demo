# Phase 3: Log Analytics Detection Reliability - Patterns

## Offline Apply Pattern

Dry-run helpers must avoid OCI reads and writes. They should validate local
payload construction and print intended upserts with deterministic placeholder
ids.

## Scheduled Rule Pattern

For every `searches/rule-*.sql` file:

- the `stats count as <MetricName>` alias must match `DETECTION_RULES[stem].metric`
- the `by` fields must match `DETECTION_RULES[stem].dimensions`
- the field count must be three or fewer
- the display name must exist in `DETECTION_RULE_DISPLAY_NAMES`

## Dashboard Compile Pattern

Every dashboard JSON widget should reference an existing SQL stem and compile
through `build_dashboard_payload()` without OCI calls. Dashboard SQL must not
contain unsupported colon parameters.
