# End-to-end demo script

Run `scripts/demo/full_workflow.sh` to drive the scenario:

1. Apply chaos `db-slow-checkout` via CRM admin API.
2. Run k6 `checkout-load.js` for 2 minutes.
3. Wait for the `checkout-p95` OCI alarm.
4. Coordinator ingests → `db-slow-remediation` playbook.
5. Evidence collected via `la_trace_fetch`, `apm_trace_spans`,
   `la_workflow_health`, `db_slow_query_advisor`.
6. Index proposal attached to incident (approval required).
7. Chaos cleared (CRM `clear` or Coordinator `chaos-cleanup`).
8. Re-run k6 to confirm recovery.

The script asserts each milestone by polling Log Analytics saved
searches so it can be used inside CI.

See:

- `scripts/demo/full_workflow.sh`
- `k6/checkout-load.js`
- `tests/e2e/demo_autoremediation.spec.ts`
