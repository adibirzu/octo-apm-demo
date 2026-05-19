---
phase: 07-oke-autoscaling-and-stress-demo
plan: 06
subsystem: ui
tags: [admin, template, jinja2, csp, accessibility, stress-test, ui]

# Dependency graph
requires:
  - phase: 07-oke-autoscaling-and-stress-demo (Plan 05)
    provides: "FastAPI /api/admin/stress/{presets,apply,clear,state} + page route /admin/stress-test with csp_nonce + nav_key='stress' template context"
  - phase: 05-admin-ai-and-secure-operations
    provides: "Admin-host CSP nonce contract + base.html sidebar nav block + glass-dark style.css tokens"
provides:
  - "Admin-facing /admin/stress-test page template (stress_test_admin.html) that consumes the Plan 07-05 API surface"
  - "Sidebar nav entry 'Stress Test' under Admin in base.html (active-state wired to nav_key='stress')"
  - "Operator UI surface for triggering, observing, and stopping bounded k6 stress runs with verbatim UI-SPEC copy"
  - "CSP-nonced inline JS pattern for admin pages with 2s/10s polling cadence and prefers-reduced-motion guard"
affects:
  - "Plan 07-10 (operator runbook — admin nav now lists Stress Test entry)"
  - "Future admin pages — establishes nonce-style + reduced-motion pattern reusable beyond stress-test"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inline <style nonce> block with @media (prefers-reduced-motion: no-preference) wrapper so badge pulse is off by default (UI-SPEC §Reduced motion)"
    - "Audit <pre role=\"status\" aria-live=\"polite\"> for screen-reader announcement of run lifecycle"
    - "Polling interval re-establishment on state transition (clearInterval + setInterval) so 2s active / 10s idle cadence flips without page reload"
    - "Destructive confirm() with run_id interpolation and audit-status copy before DELETE call"
    - "fetch() to /api/admin/stress/{presets,state,apply,clear} from admin template — no external JS, full CSP discipline"

key-files:
  created:
    - "crm/server/templates/stress_test_admin.html (233 lines — clone of chaos_admin.html structure adapted to D-13 form + D-15 audit display)"
  modified:
    - "crm/server/templates/base.html (sidebar nav: inserted single <li> for Stress Test under Admin entry)"
    - "tests/test_stress_demo_surface.py (appended 14 RED→GREEN assertions: template existence, copy contract, nonce discipline, polling cadence, a11y, fetch endpoints, no-external-script, no-internal-wording, no-ocids, nav entry)"

key-decisions:
  - "Reuse style.css tokens (.card, .btn, .btn-primary, .btn-danger, .badge, .badge-active, .eyebrow, .page, .page-header) — no new CSS file or selectors per UI-SPEC §Existing System Reuse"
  - "Implement badge pulse via inline <style nonce> + @media (prefers-reduced-motion: no-preference) guard so the keyframes never ship to style.css and reduced-motion users get no animation by default"
  - "Polling cadence flipped via clearInterval+setInterval on every state transition rather than a single shared interval — guarantees 2s/10s honour without state lag"
  - "Destructive confirm() copy quotes run_id and explicitly states 'audit event will record status=stopped' so operators have non-repudiable awareness before SIGTERM"
  - "Plan 07-05 page-route context required two extra base.html keys (cfg, brand_logo_url, brand) for the template to render without 500 — added in commit 10b0a33 (Rule 3 — blocking) before template authoring could verify GREEN"

patterns-established:
  - "Admin-page template pattern: extends base.html + nonce-scoped inline <style> + nonce-scoped IIFE JS + zero external script tags (CSP-tight by construction)"
  - "Three-channel observability UI: status badge (visual) + <pre role=status aria-live=polite> (assistive) + audit banner explaining trace_id/span_id/run_id audit fields (operator transparency)"
  - "Forbidden-copy enforcement via test: pytest scans template source for internal terms (Workflow Gateway, Coordinator, k6 wrapper) outside <pre>/<script> blocks"

requirements-completed: [SCALE-03]

# Metrics
duration: ~35 min
completed: 2026-05-18
---

# Phase 7 Plan 06: Admin Stress-Test Template + Sidebar Nav Summary

**Admin-only /admin/stress-test page (Jinja2 clone of chaos_admin.html) wiring the Plan 07-05 API surface to operators via CSP-nonced inline JS, 2s/10s polling, confirm-on-stop, ARIA-live audit pre, and a Stress Test entry in the sidebar nav — zero new CSS, all copy verbatim from UI-SPEC.**

## Performance

- **Duration:** ~35 min (including post-timeout SUMMARY finalization)
- **Started:** 2026-05-18T18:50Z (approx, before 1ecd9f1 RED commit)
- **Completed:** 2026-05-18T19:10Z
- **Tasks:** 3 (RED tests, template author, nav edit)
- **Files modified:** 3 (template created, base.html nav, tests appended)

## Accomplishments

- Authored `stress_test_admin.html` (233 lines) as a structural clone of `chaos_admin.html` adapted to D-13 form fields, D-15 three-channel MELTS audit display, and UI-SPEC layout + copywriting contract — no new CSS file.
- Wired the page to Plan 07-05 endpoints (`/api/admin/stress/{presets,state,apply,clear}`) via a single CSP-nonced inline IIFE that handles preset loading, state polling (2s active / 10s idle), apply submit, and confirm-gated stop.
- Inserted a single `<li>` "Stress Test" entry under the existing Admin entry in `base.html`, with `data-journey="nav_stress"` and `class="{% if nav_key == 'stress' %}active{% endif %}"` matching the surrounding pattern. Active-state fires from the Plan 07-05 page-route context.
- Locked the UI contract via 14 grep-style pytest assertions covering: template existence, CSP nonce, form-field labels, primary/destructive CTA copy, confirm-on-stop, polling cadence constants (2000/10000), ARIA-live audit pre, audit banner verbatim, four fetched endpoints, no-external-script discipline, forbidden-internal-wording, no-live-OCID, and nav entry.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 — pytest assertions for template + nav (TDD RED)** — `1ecd9f1` (test)
2. **Task 2: Author stress_test_admin.html (clone of chaos_admin.html)** — `d1e8cf5` (feat)
3. **Task 2 follow-up: Enrich /admin/stress-test page-route context with base.html keys (Rule 3 — blocking)** — `10b0a33` (fix)
4. **Task 3: Add Stress Test entry to admin sidebar nav** — `7344fea` (feat)

**Plan metadata:** (this commit) — `docs(07-06): complete admin stress-test template plan`

## Files Created/Modified

- `crm/server/templates/stress_test_admin.html` (created, 233 lines) — Admin page extending base.html. Sections: page header, audit banner, "Active stress run" card (status badge + RUN ID chip + meta line + `<pre role="status" aria-live="polite">` + Stop button), "Trigger a new run" card (scenario `<select>` populated from /presets, target_service `<select disabled>` with single option `shop`, rps 1–200, duration 10–600, note `<textarea maxlength=512>`, Apply button + result `<pre>`), and "Observability drilldowns" card (D-20 external links + internal pivots). Inline `<style nonce>` block wraps the badge-pulse keyframes in `@media (prefers-reduced-motion: no-preference)`. Inline `<script nonce>` IIFE owns preset loading, state polling with cadence flip on transition, apply submit, and confirm-gated clear.
- `crm/server/templates/base.html` (modified, +1 line) — Single `<li>` inserted between the existing Admin and Simulation entries: `<li><a href="/admin/stress-test" data-journey="nav_stress" class="{% if nav_key == 'stress' %}active{% endif %}">Stress Test</a></li>`.
- `tests/test_stress_demo_surface.py` (modified, +161 lines) — 14 new assertions enforcing the UI contract; all pass in 0.15 s.

## Decisions Made

- **No new CSS file.** Reused `style.css` glass-dark tokens (.card, .btn, .btn-primary, .btn-danger, .badge, .badge-active, .eyebrow, .page, .page-header) per UI-SPEC §Existing System Reuse and D-11. Justified because chaos_admin.html already proves the token set carries this exact layout.
- **Badge pulse via inline nonce style with `prefers-reduced-motion: no-preference` guard.** Keyframes ship inside a `<style nonce="{{ csp_nonce }}">` block in the template, so style.css stays untouched and reduced-motion users get no animation by default (UI-SPEC §Reduced motion).
- **Polling cadence flipped at every state transition** (clearInterval + setInterval). This honours the 2 s active / 10 s idle requirement without lag — a single shared interval would have made the cadence change visible only after the next tick.
- **Destructive confirm() text quotes run_id and explicitly mentions the audit record.** UI-SPEC §Destructive confirmation copy: `Stop run <run_id>? k6 receives SIGTERM and drains in-flight requests. The audit event will record status=stopped with the current operator.` This makes the stop action non-repudiable from the operator's perspective before the DELETE fires.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Page-route context missing base.html keys**
- **Found during:** Task 2 (template authoring) — base.html extends require `cfg`, `brand_logo_url`, and `brand` keys that the Plan 07-05 page-route context omitted.
- **Issue:** Rendering `/admin/stress-test` would 500 on the missing template variables before any UI contract could be verified.
- **Fix:** Enriched the page-route context dict in `crm/server/modules/stress_test.py` to include the keys that all other admin page routes pass to base.html.
- **Files modified:** `crm/server/modules/stress_test.py`
- **Verification:** Page route now renders without 500; existing Plan 07-05 page-route test still passes.
- **Committed in:** `10b0a33` — `fix(07-06): enrich stress page-route context with base.html keys`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to unblock GREEN verification of Task 2 acceptance criteria. No scope creep — the fix was a single dict update in code that Plan 07-05 had already authored.

## Issues Encountered

- Previous executor session timed out **after** all four implementation commits landed but **before** writing this SUMMARY. Finalization was completed in a fresh executor session: re-verified the 14 plan-06 assertions are GREEN (14 passed, 77 deselected, 0.15 s), re-checked the template at 233 lines (≤250 budget), and committed the SUMMARY + STATE/ROADMAP updates as the closing metadata commit.

## User Setup Required

None — no external service configuration required. The page is server-rendered and authenticated through the existing admin-host + admin-role gates established in Phase 5 and re-used by Plan 07-05.

## Next Phase Readiness

- Operator UI for stress test is complete; Plan 07-10 (operator runbook) can now reference `/admin/stress-test` with the verified copy contract.
- The CSP-nonced inline-style + inline-script pattern with reduced-motion guard is reusable for future admin pages that need bespoke micro-animations without polluting `style.css`.
- No blockers for Plan 07-10 (the last plan in this phase).

## Self-Check: PASSED

- `crm/server/templates/stress_test_admin.html` — FOUND (233 lines)
- `crm/server/templates/base.html` — FOUND (Stress Test nav entry inserted)
- `tests/test_stress_demo_surface.py` — FOUND (14 plan-06 assertions appended)
- Commit `1ecd9f1` — FOUND (test RED)
- Commit `d1e8cf5` — FOUND (feat template)
- Commit `10b0a33` — FOUND (fix context keys)
- Commit `7344fea` — FOUND (feat nav)
- `pytest tests/test_stress_demo_surface.py -k "stress_template or base_html_has_stress"` — 14 passed, 0 failed

---
*Phase: 07-oke-autoscaling-and-stress-demo*
*Completed: 2026-05-18*
