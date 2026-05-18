# Phase 6: Documentation and Architecture Closure - Context

**Gathered:** 2026-05-14
**Status:** Ready for execution
**Source:** GSD autonomous, public docs, DrawIO diagrams, Phase 1-5 evidence,
deployment verifier output, and docs regression tests

<domain>
## Phase Boundary

Phase 6 closes the public documentation and architecture surface so it matches
the source implementation: VM/OKE/container paths share one validation story,
admin AI remains off the customer surface, diagrams are editable in layers,
and troubleshooting guides point operators to APM, Log Analytics, OKE ONM,
Connector Hub, dashboard, and saved-query evidence.

This phase covers `DOC-01`, `DOC-02`, and `DOC-03`.
</domain>

<decisions>
## Implementation Decisions

### Public Docs Stay Sanitized
- Public docs keep placeholders for tenancy/profile/host/IP/OCID values.
- Live environment specifics stay in private operator notes or ignored files.

### Diagrams Are Source of Truth
- Public `.drawio` files are layered for editability.
- Rendered SVG previews stay aligned with visible text changes when the DrawIO
  CLI is unavailable.

### Admin AI Boundary Is Architectural
- Architecture pages must show Coordinator, Query Lab, Select AI, and Workflow
  Gateway labs as Admin surfaces, not customer storefront capabilities.
- Guardrail fields are documented as safe pivots for APM and Log Analytics.
</decisions>

<code_context>
## Existing Code and Docs Insights

- `site/architecture/system-design.md` still showed Coordinator/GenAI paths
  too close to the customer storefront.
- `site/architecture/diagrams/*.drawio` used one default layer, making diagrams
  hard to edit by section.
- `site/observability-v2/synthetic-monitoring.md` existed but was not in the
  MkDocs nav.
- `site/operations/deploy-readiness.md` described checks but did not record the
  latest zero-warning verifier result.
- `site/observability-v2/log-analytics-dashboards.md` had assets and live
  status, but needed a short operator troubleshooting table for connector,
  ONM, trace/log, payment, and GenAI pivots.
</code_context>

<specifics>
## Specific Ideas

- Add a source-level docs regression test for layered DrawIO, admin-only AI
  architecture, release gate evidence, and troubleshooting links.
- Add layers to all public DrawIO sources and document layer authoring.
- Update architecture diagrams and pages for Admin Coordinator, admin Query
  Lab, Select AI, LLMetry, and Workflow Gateway host-bound behavior.
- Update release readiness with the zero-warning verifier result.
- Add quick Log Analytics troubleshooting pivots.
</specifics>

<deferred>
## Deferred Ideas

- Re-export all DrawIO diagrams through the desktop CLI when available. The
  visible SVG text was patched for the changed labels in this run.
- Live APM/Log Analytics/dashboard validation remains a separate operator
  action with approved OCI credentials.
</deferred>
