# Phase 6: Documentation and Architecture Closure - Research

## Surface Inventory

| Surface | Evidence | Notes |
|---|---|---|
| Platform architecture | `site/architecture/platform-overview.md`, `platform-overview.drawio/svg` | Needed Admin AI and Workflow Gateway boundary updates. |
| System design | `site/architecture/system-design.md` | Needed Coordinator path moved to Admin CRM and GenAI flow reframed as admin LLMetry. |
| Diagram authoring | `site/architecture/diagrams/README.md` | Needed explicit layer and flow-movement conventions. |
| Deploy readiness | `site/operations/deploy-readiness.md` | Needed current zero-warning local gate evidence. |
| Log Analytics runbooks | `site/observability-v2/log-analytics-dashboards.md` | Needed troubleshooting quick pivots for connector, ONM, payment, trace/log, and GenAI. |
| MkDocs nav | `mkdocs.yml` | Synthetic monitoring page existed but was not listed in nav. |

## Gaps Found

- DrawIO sources were single-layer files even though the docs require layered,
  editable architectures.
- Public architecture implied the Coordinator or GenAI path could originate
  from the customer shop surface.
- Workflow Gateway Query Lab and Select AI were not consistently described as
  admin-only and host-bound.
- Public docs did not record the latest `deploy/verify.sh` zero-warning result.
- Troubleshooting content did not provide a compact path from dashboard symptom
  to the correct Log Analytics saved search.

## Validation Strategy

- Add `tests/test_documentation_architecture_closure.py`.
- Parse DrawIO XML and require multiple named layers with used cells.
- Assert architecture pages include admin-only Coordinator/Workflow Gateway
  language and guardrail fields.
- Assert MkDocs nav, deploy readiness, troubleshooting pivots, and diagram
  authoring docs include the closure content.
- Run strict MkDocs, DrawIO XML parse, public-doc leakage tests, and the
  canonical deployment verifier.

## Live Validation Deferred

- APM dashboard widget rendering in the live tenancy.
- Log Analytics saved-search execution against fresh live rows.
- Public VM/OKE/browser E2E during a live approved rollout window.
