# Codebase Conventions

Generated: 2026-05-14

## General

- Prefer existing service boundaries and helper modules over new cross-cutting
  abstractions.
- Keep customer-facing Shop pages focused on the fake demo shop and evidence
  copy; keep backend/operator controls in Admin.
- Keep runtime code and docs secret-safe. Use placeholders in public docs.
- Keep VM, OKE, and container behavior aligned when adding env vars, service
  names, metrics, logs, or health checks.

## Python

- FastAPI modules are organized by feature under `server/modules/`.
- Observability helpers live under `server/observability/`.
- Configuration flows through `server/config.py` and environment variables.
- Tests live beside each app under `shop/tests/` and `crm/tests/`.
- Prefer structured dictionaries and schema-like helpers for logs and API data.
- Use OpenTelemetry span attributes and structured logs together for every
  business workflow change.

## Java

- Java sidecar code is under `services/apm-java-demo/src/main/java/`.
- Maven owns build/test lifecycle.
- Payment simulation should emit explicit spans, log fields, and response
  metadata that align with Shop logs and APM saved queries.

## Deployment

- Deployment scripts should default to dry-run or validation where practical.
- Apply, destructive, and route-changing actions need explicit operator intent.
- Reuse env var names across VM, OKE, Helm, and local-stack paths.
- Do not create duplicate Log Analytics fields when existing fields can carry
  the same meaning.
- Preserve public LB host routing and certificate assumptions unless the user
  explicitly asks for a cutover.

## Documentation

- Public docs should be sanitized and portable.
- Diagrams should be editable from DrawIO sources and rendered to SVG.
- Operational snapshots belong in `site/operations/current-status.md`.
- Architecture contracts belong under `site/architecture/`.
- Troubleshooting/runbook steps should include validation commands and expected
  evidence in APM, Log Analytics, Monitoring, and app readiness endpoints.

## Git and Worktree

- This repo often has a large dirty worktree. Do not revert unrelated changes.
- GSD config uses no automatic branch strategy and no worktree isolation in
  this Codex runtime.
