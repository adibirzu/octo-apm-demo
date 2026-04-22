# octo-wizard — one-click provisioning

Interactive TUI that:

1. Discovers your OCI tenancy (compartments, regions, OKE clusters, ATPs, VCNs, OCIR namespace)
2. Presents the real choices as pick-lists
3. Composes a deployment plan
4. Dispatches to the existing deploy scripts

All SDK calls are **read-only** — the wizard itself never creates
resources; it drives the already-idempotent scripts under `deploy/`.

## Run

```bash
cd deploy/wizard
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,oci]"

octo-wizard
```

Requires `~/.oci/config` with at least one profile.

## Flow

```
profile → region → compartment → runtime (OKE existing/new, VM existing/new)
                                     → existing cluster picker (if OKE-existing)
                                 → DB (ATP existing/new, Postgres dev)
                                     → existing ATP picker (if ATP-existing)
                                 → DNS domain
                                 → plan preview
                                 → mode (dry-run / apply)
```

## Plan shape

Each step of the plan is a shell command with a description + the
minimal env vars it needs. The wizard prints them as a table before
any execution:

```
┌───┬────────┬───────────────────────────────────┬─────────────────────────────────┐
│ # │ Kind   │ Command                           │ Description                     │
├───┼────────┼───────────────────────────────────┼─────────────────────────────────┤
│ 1 │ script │ ./deploy/pre-flight-check.sh      │ Validate required env           │
│ 2 │ script │ ./deploy/init-tenancy.sh          │ OCIR + K8s namespace + secrets  │
│ 3 │ script │ ./deploy/oci/ensure_apm.sh --apply│ APM Domain + RUM                │
│ 4 │ script │ ./deploy/oci/ensure_stack_*       │ Register ATP in SM              │
│ 5 │ script │ ./deploy/oke/deploy-oke.sh        │ Roll out shop + CRM             │
└───┴────────┴───────────────────────────────────┴─────────────────────────────────┘
```

## Modes

- **dry-run** — print only, no side effects. Safe for first-timers.
- **apply** — execute. Each high-risk step still prompts via
  `questionary.confirm` so an escape hatch always exists.

## Tests

```bash
pytest -q
# 7 passed — plan composition invariants, no OCI calls
```

The plan module is pure; discovery is isolated in `discovery.py` and
covered by the manual live-run. CI can run the plan tests on every
PR.

## Extending

Add a new question → update `DeploymentPlan` field + plumb in `cli.py`.
Add a new script to call → append to `DeploymentPlan.compose()` with
its env map. Nothing else.
