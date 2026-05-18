---
phase: 04-deployment-parity-and-release-gates
plan: "02"
subsystem: deployment
tags: [release-gates, verifier, terraform, kubectl, docs]

requires:
  - Phase 4 Plan 01
provides:
  - Non-destructive release gate documentation
  - Offline-safe Helm client dry-run
  - Provider-registry outage handling in validators
affects: [deploy, compute, docs, tests]

requirements-completed: [DEPLOY-03, DEPLOY-04]
completed: 2026-05-14
---

# Phase 4 Plan 02: Release Gates and Safe Promotion Summary

## Accomplishments

- Updated `site/operations/deploy-readiness.md` with the non-destructive
  release sequence for repo, Compute, OKE, ONM, round-robin, APM, Log
  Analytics, Playwright, and rollback gates.
- Changed Helm client validation in `deploy/verify.sh` to use
  `kubectl create --dry-run=client --validate=false`, avoiding accidental
  contact with the current Kubernetes API server.
- Made Terraform validation in `deploy/verify.sh` run
  `terraform init -backend=false` before validate.
- Made Terraform provider-registry/network outages warnings instead of code
  failures in `deploy/verify.sh` and `deploy/compute/validate.sh`.
- Made the deploy verifier treat the Mermaid CDN availability check as an
  external dependency warning when the local docs are otherwise buildable.

## Files Modified

- `deploy/verify.sh`
- `deploy/compute/validate.sh`
- `site/operations/deploy-readiness.md`
- `tests/test_unified_deploy_surface.py`

## Verification

- `python3 -m pytest -q tests/test_unified_deploy_surface.py tests/test_deployment_parity_release_gates.py` - passed.
- `bash deploy/verify.sh` - passed with two broad-suite warnings for shop/crm
  pytest in this local environment.

## Notes

The verifier still fails for source-level errors. Only external dependency
availability, such as provider registry or CDN reachability, is downgraded to
warnings.
