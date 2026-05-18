---
phase: 01-signal-contract-hardening
plan: "02"
subsystem: observability
tags: [fastapi, logging, traces, request-id, workflow]

requires:
  - phase: 01-signal-contract-hardening
    provides: Plan 01 source-level signal contract inventory
provides:
  - Shop and CRM logging SDK request-id enrichment
  - CRM request span and completion log workflow enrichment
  - Root-level pytest isolation for Shop and CRM logging tests
affects: [shop, crm, log-analytics, apm, phase-1]

tech-stack:
  added: []
  patterns:
    - Request context is pulled from `server.security.request_id.current_request_id`
    - Workflow context is captured by logging SDKs before dynamic module cache changes can affect tests

key-files:
  created:
    - shop/__init__.py
    - shop/tests/__init__.py
    - crm/__init__.py
    - crm/tests/__init__.py
  modified:
    - shop/server/observability/logging_sdk.py
    - crm/server/observability/logging_sdk.py
    - crm/server/middleware/tracing.py
    - shop/tests/test_logging_sdk.py
    - crm/tests/test_logging_sdk.py
    - crm/tests/test_observability_capabilities.py
    - tests/test_signal_contract_inventory.py

key-decisions:
  - "Use the existing request-id context helper instead of requiring every caller to pass request_id manually."
  - "Keep CRM middleware workflow fields duplicated in dotted and snake_case forms for APM span attributes and Log Analytics fields."
  - "Mark Shop and CRM test directories as packages so root pytest can collect same-named tests without import mismatch."

patterns-established:
  - "FastAPI logs get request_id, workflow_id, workflow_step, trace IDs, and service identity before PII masking and span-log events."
  - "Trace and span identifiers are exempt from card-number masking to preserve correlation IDs."

requirements-completed: [OBS-01, OBS-02]

duration: 9 min
completed: 2026-05-14
---

# Phase 1 Plan 02: FastAPI Request And Workflow Logging Summary

**Shop and CRM structured logs now pull request context automatically, while CRM request spans and completion logs carry workflow and request pivots for APM and Log Analytics.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-05-14T10:04:28Z
- **Completed:** 2026-05-14T10:13:26Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments

- Added `current_request_id()` enrichment to Shop and CRM `push_log` before PII masking and span-log events.
- Updated CRM `TracingMiddleware` to stamp request ID, correlation ID, workflow ID, workflow step, HTTP path/method/status, and response time on request logs and `middleware.entry`/`response.finalize` spans.
- Extended Shop and CRM logging tests to validate request IDs, trace IDs, APM trace aliases, service identity, Log Analytics aliases, and PII masking.
- Extended the signal inventory to require `current_request_id` in both FastAPI logging paths.

## Task Commits

No commits were created in this Codex session. The changes remain in the working tree for user-controlled review and commit.

## Files Created/Modified

- `shop/server/observability/logging_sdk.py` - Adds request-id enrichment and trace-id masking exemptions.
- `crm/server/observability/logging_sdk.py` - Adds request-id enrichment and stable workflow helper import.
- `crm/server/middleware/tracing.py` - Adds request/workflow fields to CRM spans and logs.
- `shop/tests/test_logging_sdk.py` - Adds request/trace/service JSON assertions and root pytest isolation.
- `crm/tests/test_logging_sdk.py` - Adds request/trace/service JSON assertions and root pytest isolation.
- `crm/tests/test_observability_capabilities.py` - Adds CRM middleware source guard.
- `tests/test_signal_contract_inventory.py` - Extends the global inventory with `current_request_id`.
- `shop/__init__.py`, `shop/tests/__init__.py`, `crm/__init__.py`, `crm/tests/__init__.py` - Package markers for root-level pytest collection.

## Decisions Made

- Kept request-id lookup defensive so logging continues if the request context helper is unavailable in a narrow test or script path.
- Used source-level assertions for CRM middleware because the plan only needed to protect the required field and span-name contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Root pytest could not collect same-named app tests**

- **Found during:** Task 1 verification
- **Issue:** `python3 -m pytest -q shop/tests/test_logging_sdk.py crm/tests/test_logging_sdk.py` failed because both apps had `test_logging_sdk.py` importing a top-level `server` package.
- **Fix:** Added package markers and app-local import isolation at the top of each logging test file.
- **Files modified:** `shop/__init__.py`, `shop/tests/__init__.py`, `crm/__init__.py`, `crm/tests/__init__.py`, `shop/tests/test_logging_sdk.py`, `crm/tests/test_logging_sdk.py`
- **Verification:** `python3 -m pytest -q shop/tests/test_logging_sdk.py crm/tests/test_logging_sdk.py`
- **Committed in:** Not committed; working-tree change only.

**2. [Rule 2 - Missing Critical] Numeric trace/span IDs could be card-masked**

- **Found during:** Task 1 tests
- **Issue:** The Shop card-number scrubber could mask all-numeric `trace_id` or `span_id` values, breaking trace/log correlation.
- **Fix:** Added card-mask exemptions for trace, span, request, workflow, order, and payment gateway join keys.
- **Files modified:** `shop/server/observability/logging_sdk.py`, `shop/tests/test_logging_sdk.py`
- **Verification:** `python3 -m pytest -q shop/tests/test_logging_sdk.py crm/tests/test_logging_sdk.py`
- **Committed in:** Not committed; working-tree change only.

**Total deviations:** 2 auto-fixed (1 blocking test isolation issue, 1 critical correlation-field masking issue).
**Impact on plan:** Both fixes were necessary for the planned root verification and for preserving the observability contract.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- `python3 -m pytest -q shop/tests/test_logging_sdk.py crm/tests/test_logging_sdk.py` - passed, 15 tests.
- `python3 -m pytest -q crm/tests/test_observability_capabilities.py` - passed, 3 tests.
- `python3 -m pytest -q tests/test_signal_contract_inventory.py` - passed, 7 tests.
- `git diff --check -- shop/server/observability/logging_sdk.py crm/server/observability/logging_sdk.py crm/server/middleware/tracing.py shop/tests/test_logging_sdk.py crm/tests/test_logging_sdk.py crm/tests/test_observability_capabilities.py tests/test_signal_contract_inventory.py shop/__init__.py shop/tests/__init__.py crm/__init__.py crm/tests/__init__.py` - passed.

## Next Phase Readiness

Ready for Phase 1 Plan 03. The FastAPI app paths now protect request/workflow correlation, so the next plan can focus on Java sidecar and support-service telemetry.

---
*Phase: 01-signal-contract-hardening*
*Completed: 2026-05-14*
