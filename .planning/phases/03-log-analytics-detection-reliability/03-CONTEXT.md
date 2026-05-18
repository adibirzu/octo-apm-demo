# Phase 3: Log Analytics Detection Reliability - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning
**Source:** GSD autonomous smart-discuss fallback, roadmap, requirements, and Log Analytics asset scout

<domain>
## Phase Boundary

Phase 3 hardens Log Analytics saved searches, dashboards, parser field reuse,
and scheduled detection-rule source assets so troubleshooting and
threat-hunting flows are reliable before live import. The phase remains local
and non-destructive unless a later operator explicitly runs the apply helpers
with `--apply`.

This phase covers `OBS-04` and `SEC-01`.
</domain>

<decisions>
## Implementation Decisions

### Local Before Live
- Treat versioned SQL, dashboard JSON, parser mappings, field manifests, and
  apply helpers as the source of truth for local reliability checks.
- Do not query or mutate OCI during GSD validation. Live import and real-data
  verification remain explicit operator actions.

### Detection Rule Reliability
- Scheduled-rule SQL must have metric aliases and dimensions that match the
  metadata in `apply_saved_searches_and_dashboards.py`.
- Scheduled-rule dimensions should stay at three fields or fewer.
- Dry-run mode must be safe in shells without OCI credentials; it should not
  call OCI lookup commands.

### Dashboard Reliability
- Every dashboard widget must compile to an import payload backed by a
  versioned saved search.
- Saved-search SQL used in dashboards must not contain unsupported colon
  placeholders.

### the agent's Discretion
- The executor may add focused tests or helper hardening where they prevent
  query/dashboard/rule drift.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/test_log_analytics_attack_assets.py` already validates parser field
  maps, saved searches, dashboard widget references, query token safety, and
  Octo detection-rule mirrors.
- `tests/test_observability_asset_contract.py` validates required APM and Log
  Analytics assets.
- `deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py` builds
  saved-search, dashboard, and scheduled detection-rule payloads.
- `deploy/oci/log_analytics/README.md` documents connector, ONM, parser, saved
  search, dashboard, and detection-rule operations.

### Established Patterns
- Keep source validation dependency-light and credential-free.
- Prefer existing Log Analytics fields from the reuse map.
- Keep public docs sanitized and variable-driven.

### Integration Points
- APM saved-query descriptors point to Log Analytics saved searches.
- Dashboards reference `searches/*.sql` by stem.
- Scheduled rules extract metrics into `octo_log_analytics_detections` and
  resource group `octo-apm-demo`.
</code_context>

<specifics>
## Specific Ideas

- Make Log Analytics apply dry-run fully offline.
- Add a local reliability test that compares each `rule-*.sql` metric alias and
  dimensions with the scheduled-rule metadata.
- Add a dashboard compile test that builds every dashboard payload locally.
- Add a colon-placeholder rejection test for Log Analytics SQL.
</specifics>

<deferred>
## Deferred Ideas

- Live Log Analytics query execution and real sample checks require OCI
  credentials, namespace, and an approved operator window. Keep those as
  documented Phase 4/operations validation steps.
</deferred>
