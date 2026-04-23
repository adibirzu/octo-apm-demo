# Local regression stack

A self-contained `docker compose` stack for running Playwright + k6
regression against shop + crm without any OCI connectivity. Useful
for CI, airplane-mode development, or reproducing production bugs
against a known state.

## What you get

| Service    | Host port | Role                                  |
|------------|-----------|---------------------------------------|
| `shop`     | 18080     | Drone shop (FastAPI)                  |
| `crm`      | 18090     | Enterprise CRM portal (FastAPI)       |
| `redis`    | 16379     | Cache, rate limit, async-worker stream |
| `postgres` | 15432     | Autonomous DB stand-in                |

## Start

```bash
cd deploy/local-stack
docker compose -f docker-compose.test.yml up --build
```

First build: 2–3 min. Cached afterward.

## Run Playwright against it

```bash
cd shop
SHOP_URL=http://localhost:18080 \
  CRM_URL=http://localhost:18090 \
  npx playwright test tests/e2e/shopping-flow.spec.ts
```

See [`deploy/local-stack/README.md`](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/local-stack/README.md) for teardown, logs,
and caveats (Postgres parity, disabled OCI exporters, no IDCS).

## When to use it

**Do** use when:

- You want fast, hermetic regression (< 1 min cold start after first build)
- You're debugging the container image, not the ATP integration
- CI has no OCI credentials

**Don't** use when:

- You need ATP-specific SQL paths (JSON Duality Views, PL/SQL procedures)
- You're validating OCI observability ingestion (use `deploy/vm/docker-compose-unified.yml` with real ATP + OCI Auth)
- You're testing IDCS SSO flows

## Limitations

Postgres stands in for ATP. The shop and CRM schemas are expressed in
portable SQL, but:

- `shop/server/db_init.sql` uses `SERIAL` / `INTEGER IDENTITY` — works on both.
- PL/SQL procedures and JSON Relational Duality Views are Oracle-only; tests that depend on them are skipped via pytest markers.

OCI exporters are explicitly disabled:

```yaml
OCI_AUTH_MODE: disabled
OTEL_EXPORTER_OTLP_ENDPOINT: ""
```

…so traces surface only in the in-process memory exporter during tests.
