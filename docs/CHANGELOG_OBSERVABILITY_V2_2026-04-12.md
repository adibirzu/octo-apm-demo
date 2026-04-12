# Observability v2 — Change Log (2026-04-12)

Intended for sync into the **Notion Development hub** (Changes Log
database). When notion-MCP OAuth is available, paste each row below as a
new entry with the indicated metadata.

---

## Entry 1 — octo-drone-shop

- **Project**: octo-drone-shop
- **Type**: Feature
- **Status**: Completed
- **Date**: 2026-04-12
- **Files Changed**:
  - `server/security/{headers,request_id,auth_deps}.py`
  - `server/observability/{workflow_context,log_enricher}.py`
  - `server/chaos/{registry,router,db_faults}.py`
  - `server/main.py`
  - `server/templates/base.html`
  - `deploy/env.template`
  - `deploy/terraform/` (root + `modules/waf` + `modules/log_pipeline`)
  - `deploy/oci/log_analytics/` (parsers, searches, dashboards)
  - `.github/workflows/{security-gates,mkdocs-deploy}.yml`
  - `site/observability-v2/*` (8 pages)
  - `scripts/demo/full_workflow.sh`, `k6/checkout-load.js`,
    `tests/e2e/demo_autoremediation.spec.ts`
  - `README.md`, `ARCHITECTURE.md`, `mkdocs.yml`
- **Description**:
  Observability + security v2. Unified correlation contract
  (`trace_id` / `request_id` / `workflow_id`). Security headers + WAF
  (DETECTION). Shop is **reader-only** for chaos; all writes live on
  CRM or Ops portal. SQLAlchemy fault injection emits OTel span events
  so APM sees `chaos.injected`. Additive, flag-gated, tenancy-portable.

## Entry 2 — enterprise-crm-portal

- **Project**: enterprise-crm-portal
- **Type**: Feature
- **Status**: Completed
- **Date**: 2026-04-12
- **Files Changed**:
  - `server/security/*`, `server/observability/*`,
    `server/chaos/{registry,admin,db_faults}.py`
  - `server/templates/{base.html,chaos_admin.html}`
  - `server/main.py`
  - `deploy/env.template`
  - `.github/workflows/{security-gates,mkdocs-deploy}.yml`
  - `mkdocs.yml`, `docs-site/*`
  - `README.md`
- **Description**:
  CRM becomes sole chaos controller. `/admin/chaos` page (role
  `chaos-operator`), TTL-bounded apply, clear, audit log. Shared
  observability contract + headers. Same middleware stack, same env
  schema.

## Entry 3 — oci-coordinator

- **Project**: oci-coordinator
- **Type**: Feature
- **Status**: Completed
- **Date**: 2026-04-12
- **Files Changed**:
  - `src/mcp/server/tools/octo_observability.py` (9 tools)
  - `src/agents/coordinator/drilldown_pivot.py` (additive node)
  - `src/incidents/playbooks/*.yaml` (5 playbooks + README)
  - `src/incidents/rules/octo_demo.yaml`
  - `docs/OCTO_DEMO_DRILLDOWN.md`, `docs/index.md`,
    `docs/octo-demo/{playbooks,rules,tools}.md`
  - `mkdocs.yml`
  - `.github/workflows/{security-gates,mkdocs-deploy}.yml`
  - `README.md`
- **Description**:
  Read-only MCP tools + proposal-only write tools. 5 playbooks with
  explicit risk tiers; only `chaos-cleanup` (tier low) may
  auto-execute. Correlation rules bind alarms/hunting searches to
  playbooks. Drill-down pivot node is additive, not yet wired into
  main graph.

## Entry 4 — multicloudoperations

- **Project**: multicloudoperations
- **Type**: Detection
- **Status**: Completed
- **Date**: 2026-04-12
- **Files Changed**:
  - `detections/sigma/oci/octo_shop_chaos_abuse.yml`
  - `detections/sigma/oci/octo_crm_admin_bruteforce.yml`
  - `detections/sigma/oci/octo_waf_owasp_surge.yml`
- **Description**:
  Three Sigma rules covering chaos-endpoint abuse, CRM admin
  brute-force, and WAF OWASP CRS detection surges.

## Entry 5 — oci-log-analytics-detections

- **Project**: oci-log-analytics-detections
- **Type**: Detection
- **Status**: Completed
- **Date**: 2026-04-12
- **Files Changed**:
  - `hunting/octo_checkout_db_slowness.json`
  - `hunting/octo_waf_vs_app_errors.json`
  - `hunting/octo_chaos_stale_state.json`
- **Description**:
  Hunting saved-searches powering the Coordinator drill-down pivot
  and the chaos-cleanup playbook.

## Entry 6 — OCI-DEMO / ops_portal

- **Project**: OCI-DEMO (ops_portal component)
- **Type**: Integration
- **Status**: Completed
- **Date**: 2026-04-12
- **Files Changed**:
  - `ops_portal/chaos_proxy.py`
  - `ops_portal/app.py` (single additive include_router line)
- **Description**:
  Ops portal proxies the CRM's chaos admin API behind the portal's
  existing IDCS SSO guard. Forwards the operator's session cookie so
  the CRM's `chaos-operator` role enforcement still applies.

---

## Cross-project TODOs (Notion TODO database)

1. **P1** — Wire `drilldown_pivot_node` into
   `src/agents/coordinator/graph.py` when team is ready (additive).
2. **P1** — Run 7-day WAF DETECTION soak, then flip `WAF_MODE=BLOCK`.
3. **P2** — Observe `AUTOREMEDIATE_ENABLED=true` in staging; enforce
   tier-low-only auto-execute.
4. **P2** — Build `docs-site/observability-v2/*` images (sequence
   diagrams) via mermaid.
5. **P3** — Onboard additional chaos scenarios
   (`checkout-intermittent-500`, `crm-queue-slow-drain`).

## TODOs (Sync to Notion)

When `mcp__notion__authenticate` completes, paste the six entries above
into the Development hub Changes Log and the five follow-ups into the
TODO database. This file is the canonical local source until sync.
