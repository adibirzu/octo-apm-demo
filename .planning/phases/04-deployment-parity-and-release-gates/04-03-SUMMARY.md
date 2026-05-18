---
phase: 04-deployment-parity-and-release-gates
plan: "03"
subsystem: validation
tags: [release-gate, pytest, mkdocs, deploy-verify]

requires:
  - Phase 4 Plan 01
  - Phase 4 Plan 02
provides:
  - Phase 4 validation evidence
  - Deferred live validation list
affects: [planning, deployment, docs]

requirements-completed: [DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04]
completed: 2026-05-14
---

# Phase 4 Plan 03: Phase Validation Gate Summary

## Accomplishments

- Ran deployment parity, unified deploy, signal-contract, observability asset,
  and Log Analytics reliability tests together.
- Ran the canonical deployment verifier after the offline-safety fixes.
- Ran `git diff --check`.
- Recorded live VM/OKE validation as a manual operator action because it
  changes or observes shared emdemo runtime state.

## Verification

- `python3 -m pytest -q tests/test_deployment_parity_release_gates.py tests/test_unified_deploy_surface.py tests/test_signal_contract_inventory.py tests/test_observability_asset_contract.py tests/test_log_analytics_detection_reliability.py tests/test_log_analytics_attack_assets.py` - 61 passed.
- `bash deploy/verify.sh` - passed with 2 warnings for broad shop/crm pytest
  execution in this local environment.
- `python3 -m mkdocs build --strict` - passed.
- `git diff --check` - passed.

## Deferred Live Checks

- Run public VM + OKE round-robin smoke against the shared OCI Load Balancer
  during an approved window.
- Confirm APM Trace Explorer shows browser, Shop, Java payment gateway,
  Admin/CRM, and database spans for a successful purchase.
- Confirm Log Analytics saved searches return matching real records for trace
  ID, workflow ID, order ID, payment gateway request ID, and service names.
- Use `wire-existing-lb-backends.sh --rollback-active-vm` if OKE round-robin
  regresses the live customer or admin flow.

## Notes

No live OCI resources were created, modified, or deleted during this phase.
