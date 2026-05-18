# Phase 3: Log Analytics Detection Reliability - Research

**Date:** 2026-05-14

## Findings

- Existing source tests already cover the core parser/source/search/dashboard
  contract and reject several known unsupported query patterns.
- The apply helper builds scheduled detection rules from in-code metadata, but
  there was no focused test ensuring each `rule-*.sql` metric alias and `stats
  by` dimensions match that metadata.
- Dry-run mode in the apply helper still called OCI lookup helpers before
  printing the intended action. That made "dry-run" unsuitable for credential
  free source validation.
- Dashboard payload construction can be tested locally because it only reads
  JSON descriptors and SQL files.

## Source Files Read

- `deploy/oci/log_analytics/apply_saved_searches_and_dashboards.py`
- `deploy/oci/log_analytics/README.md`
- `deploy/oci/log_analytics/searches/rule-*.sql`
- `deploy/oci/log_analytics/dashboards/*.json`
- `tests/test_log_analytics_attack_assets.py`
- `tests/test_observability_asset_contract.py`

## Constraints

- Do not run live OCI apply or query commands.
- Keep detection-rule specs and public docs free of OCIDs, hostnames, IPs, and
  credential material.
