---
phase: 01-signal-contract-hardening
plan: "03"
subsystem: observability
tags: [java, opentelemetry, payment, support-services, apm]

requires:
  - phase: 01-signal-contract-hardening
    provides: Plan 01 inventory and Plan 02 FastAPI correlation fields
provides:
  - Java stdout JSON aliases for APM and Log Analytics joins
  - Support-service OTel resource instance identity
  - Inventory coverage for Java and support-service telemetry
affects: [java-sidecar, support-services, apm, log-analytics, phase-1]

tech-stack:
  added: []
  patterns:
    - Java structured events emit dotted and alias fields from the same payload
    - Support services resolve service.instance.id from SERVICE_INSTANCE_ID, POD_NAME, HOSTNAME, then unknown

key-files:
  created: []
  modified:
    - services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java
    - services/apm-java-demo/src/test/java/com/octo/apmdemo/AppTest.java
    - services/async-worker/src/octo_async_worker/telemetry.py
    - services/load-control/src/octo_load_control/telemetry.py
    - services/object-pipeline/src/octo_object_pipeline/telemetry.py
    - services/remediator/src/octo_remediator/telemetry.py
    - services/edge-fuzz/src/octo_edge_fuzz/telemetry.py
    - tests/test_signal_contract_inventory.py

key-decisions:
  - "Use MDC for Java request_id, workflow_id, workflow_step, and run_id so stdout events and spans share the same request headers."
  - "Keep support-service OTEL_RESOURCE_ATTRIBUTES overrides after default resource attributes so deployments can still tune resource identity."

patterns-established:
  - "Java payment events expose both legacy snake_case and Log Analytics dotted payment fields."
  - "Support service telemetry helpers share the same service.instance.id fallback chain."

requirements-completed: [OBS-01, OBS-02, OBS-03]

duration: 4 min
completed: 2026-05-14
---

# Phase 1 Plan 03: Java And Support Telemetry Summary

**Java payment stdout events now carry request, workflow, service, deployment, order, processor, network, and token-safe payment fields; support services now publish stable instance identity.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-14T10:13:26Z
- **Completed:** 2026-05-14T10:16:57Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Extended Java request filtering to copy `X-Request-Id`, `X-Workflow-Id`, `X-Workflow-Step`, and `X-Run-Id` into MDC and span attributes.
- Added Java stdout JSON aliases for `service.name`, `service.namespace`, `deployment.environment`, `request_id`, `workflow_id`, `workflow_step`, `orders.order_id`, `payment.gateway.request_id`, `payment.processor.name`, `payment.processor.response_code`, `payment.network`, `payment.network.transaction_id`, and `payment.token.safe`.
- Added AppTest assertions for the new Java structured-event contract.
- Added `service.instance.id` fallback resolution to async-worker, load-control, object-pipeline, remediator, and edge-fuzz telemetry helpers.
- Extended `tests/test_signal_contract_inventory.py` to guard Java and support-service additions.

## Task Commits

No commits were created in this Codex session. The changes remain in the working tree for user-controlled review and commit.

## Files Created/Modified

- `services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java` - Adds MDC request/workflow propagation and structured-event aliases.
- `services/apm-java-demo/src/test/java/com/octo/apmdemo/AppTest.java` - Adds Java stdout JSON contract assertions.
- `services/*/src/*/telemetry.py` - Adds shared `service.instance.id` fallback chain.
- `tests/test_signal_contract_inventory.py` - Adds Java/support-service guard tokens.

## Decisions Made

- Kept Java aliases at the stdout event boundary so existing payment simulation payloads remain backward-compatible.
- Did not hardcode any OCI endpoint or data key; Java and support services still read exporter configuration from environment.

## Deviations from Plan

None - plan executed as written, with local verification constraints documented below.

## Issues Encountered

- `mvn test` could not run because Maven is not installed in this environment (`zsh:1: command not found: mvn`).
- `python3 -m pytest -q services/load-control services/remediator services/object-pipeline services/edge-fuzz services/async-worker` reached collection but failed because the service packages are not installed on the local Python path and same-named service tests collide under root pytest collection. This matches the plan's allowed local service test-environment documentation path.

## User Setup Required

None - no external service configuration required.

## Verification

- `cd services/apm-java-demo && mvn test` - blocked locally, Maven missing.
- `python3 -m pytest -q tests/test_signal_contract_inventory.py` - passed, 7 tests.
- `python3 -m pytest -q services/load-control services/remediator services/object-pipeline services/edge-fuzz services/async-worker` - blocked by local package/import setup, documented above.
- `python3 -m py_compile services/async-worker/src/octo_async_worker/telemetry.py services/load-control/src/octo_load_control/telemetry.py services/object-pipeline/src/octo_object_pipeline/telemetry.py services/remediator/src/octo_remediator/telemetry.py services/edge-fuzz/src/octo_edge_fuzz/telemetry.py` - passed.
- `git diff --check -- services/apm-java-demo/src/main/java/com/octo/apmdemo/App.java services/apm-java-demo/src/main/java/com/octo/apmdemo/OtelSupport.java services/apm-java-demo/src/test/java/com/octo/apmdemo/AppTest.java services/async-worker/src/octo_async_worker/telemetry.py services/load-control/src/octo_load_control/telemetry.py services/object-pipeline/src/octo_object_pipeline/telemetry.py services/remediator/src/octo_remediator/telemetry.py services/edge-fuzz/src/octo_edge_fuzz/telemetry.py tests/test_signal_contract_inventory.py` - passed.

## Next Phase Readiness

Ready for Phase 1 Plan 04. The remaining Phase 1 work should validate APM, Log Analytics, and Monitoring asset coverage against the hardened source contracts.

---
*Phase: 01-signal-contract-hardening*
*Completed: 2026-05-14*
