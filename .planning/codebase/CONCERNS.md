# Codebase Concerns

Generated: 2026-05-14

## Operational Risks

- The shared emdemo deployment is live, and VM plus OKE can both receive public
  traffic. Deployment changes must avoid route, certificate, backend-set, or
  shared-resource drift unless explicitly requested.
- Service Connector Hub quota has been a constraint. OKE monitoring can send
  directly to Log Analytics through OCI Kubernetes Monitoring, but new OCI
  Logging to Log Analytics connectors may fail if quota is exhausted.
- Live docs and current-status pages are snapshots. Always verify readiness,
  APM, Log Analytics, OKE, and LB state before assuming the environment is
  green.

## Security Risks

- User-provided Langfuse keys and OCI credentials must stay out of source,
  logs, docs, screenshots, and GSD artifacts.
- `credentials/`, wallets, tfvars, runtime envs, and resolved OCI outputs are
  sensitive. Avoid scanning or printing them unless a task explicitly requires
  a local-only validation.
- Payment data must remain fake and token-safe. Do not introduce real payment
  capture or sensitive card/wallet storage.
- OCI Coordinator must remain Admin-only and OCTO-scoped.

## Codebase Risks

- The repo has broad pre-existing changes. Future work should review targeted
  files before editing and avoid reverting unrelated modifications.
- Observability behavior is spread across app code, deployment envs, APM assets,
  Log Analytics parsers/searches, and docs. Feature changes can be incomplete
  unless all surfaces are updated together.
- VM, OKE, Helm, and local-stack deployment paths can drift when new env vars or
  service names are added.
- Log Analytics fields should be reused before creation; duplicates make saved
  searches and dashboards fragile.

## Testing Risks

- Local tests cannot prove OCI APM/Log Analytics ingestion. Live verification is
  required for deployment, connector, parser, dashboard, and saved-query work.
- End-to-end payment traces can be split across correlated traces if browser,
  app, Java, or CRM propagation changes. Tests should validate the expected
  trace or documented correlation path.
- Documentation can pass build checks while still being operationally stale;
  current deployment assertions need live evidence.
