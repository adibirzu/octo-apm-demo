# Deploy readiness — what has been verified

Every item on this page is checked by `deploy/verify.sh` on each push.
Green checkmarks are assertions that have actually run against the
current `main` commit; they are not aspirations.

## Green for production

| Check | How verified |
|---|---|
| `terraform validate` on root + 10 modules | `cd deploy/terraform && terraform validate` — `Success!` |
| `terraform fmt -check -recursive` | `verify.sh` step "Terraform fmt + validate" |
| `docker compose config` on unified VM stack | `verify.sh` step "Docker compose config" (per-run random tokens) |
| JSON manifests (LA parsers, dashboards, saved searches) | `verify.sh` step "JSON manifests" |
| YAML manifests (k8s deployments, ingress, cloud-init, compose) | `verify.sh` step "YAML fmt" |
| Pre-flight required-var enforcement | `verify.sh` step "Pre-flight required-var enforcement" |
| `mkdocs build --strict` | `verify.sh` step "MkDocs strict build" |
| Shop pytest (87 tests) | `verify.sh` step "shop pytest" |
| CRM pytest (39 tests) | `verify.sh` step "crm pytest" |
| Traffic-generator pytest | `verify.sh` step "tools/traffic-generator pytest" |
| Dependabot alerts: 0 open | `gh api repos/.../dependabot/alerts` — empty |
| Shop route inventory (114 paths) | `python -c "from server.main import app; [r.path for r in app.routes]"` |
| CRM route inventory (132 paths) | Same, against `crm/server/main.py` |

Run it yourself:

```bash
cd octo-apm-demo
./deploy/verify.sh
# → VERIFY PASSED — 0 warning(s)
```

## Manual steps not covered by terraform

Two OCI features currently have no first-class Terraform resource in
the provider. Document them in your tenancy runbook:

| Step | Why manual | When to do it |
|---|---|---|
| RUM web application registration | `oci_apm_config_config` rejects `config_type = "WEB_APPLICATION"`. | Once per tenancy, after `terraform apply`. Console: APM → RUM → Create Web Application. |
| Log Analytics source registration | Source identifier is not on the `oci_sch_service_connector.target` schema. | Once per LA source. Use `deploy/oci/ensure_la_sources.sh` or the Console. |

Both leave the app fully functional without them — the RUM beacon
ingests using public data key + endpoint, and LA picks up the JSON
format automatically. They add UI grouping and named-source
filtering respectively.

## What verify.sh does not cover

| Concern | Why | Where to look |
|---|---|---|
| Live ATP connectivity | Requires real wallet + credentials | `deploy/pre-flight-check.sh` warns if unset |
| APM trace ingestion end-to-end | Requires real APM endpoint + data key | Manual — hit `/ready` then inspect APM Trace Explorer |
| RUM beacon emission | Requires real browser + DNS | `site/observability/rum.md` |
| k6 load + chaos burst | Out of CI scope | `k6/` directory + `site/testing/load-tests.md` |
| Playwright E2E | Requires a running stack | `deploy/local-stack/` brings up a hermetic target |

## Failure triage

| Symptom | Fix |
|---|---|
| `Pre-flight FAILED` | Fill in the reported env var; see `deploy/pre-flight-check.sh` |
| `terraform validate` error on new provider | Check `deploy/terraform/README.md` §"When you hit a provider schema error" |
| `docker compose config` fails | Bad substitution — check `.env` file has no newline-embedded values |
| `mkdocs build --strict` complains about missing nav | Add the page to `mkdocs.yml` `nav:` or delete it |
| Shop/CRM pytest fails | Run the suite locally (`cd shop && pytest -x --tb=short`) — conftest.py handles fakeredis + module stubs |
