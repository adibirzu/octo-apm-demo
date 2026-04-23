# Local regression stack

Self-contained docker-compose bringing up:

| Service     | Host port | Purpose |
|-------------|-----------|---------|
| `shop`      | 18080     | Drone shop (FastAPI) |
| `crm`       | 18090     | CRM portal (FastAPI) |
| `redis`     | 16379     | Cache + rate-limit + order stream |
| `postgres`  | 15432     | ATP stand-in (schema is migration-equivalent) |

**Not production.** Use this to run Playwright + k6 regression against a
hermetic stack; no OCI connectivity required.

## Start

```bash
cd deploy/local-stack
docker compose -f docker-compose.test.yml up --build
```

First build takes 2–3 minutes. Afterwards images are cached locally.

## Playwright

```bash
cd shop
SHOP_URL=http://localhost:18080 \
  CRM_URL=http://localhost:18090 \
  npx playwright test tests/e2e/shopping-flow.spec.ts
```

## Teardown

```bash
docker compose -f docker-compose.test.yml down -v
```

`-v` wipes the `pg-data` volume. Omit to preserve data between runs.

## Debugging

- Check health: `docker compose -f docker-compose.test.yml ps`
- Shop logs: `docker compose -f docker-compose.test.yml logs -f shop`
- Shell into shop: `docker compose -f docker-compose.test.yml exec shop sh`
- Redis CLI: `docker compose -f docker-compose.test.yml exec redis redis-cli`
- Postgres shell: `docker compose -f docker-compose.test.yml exec postgres psql -U octo octo`

## Limitations

- Uses Postgres, not Autonomous DB — Oracle-specific SQL (PL/SQL procedures,
  JSON Relational Duality Views) is skipped or adapted. Production parity
  requires an ATP instance; see `deploy/vm/docker-compose-unified.yml` or
  the OKE path.
- OCI observability exporters are disabled (`OCI_AUTH_MODE=disabled`,
  empty OTLP endpoint). Traces surface only in in-process memory exporters.
- No IDCS SSO — basic auth + local admin bootstrap only.
