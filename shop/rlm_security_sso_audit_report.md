# RLM Audit Report — octo-drone-shop Security, SSO, OTel & Portability

**Date**: 2026-04-09 | **Commit**: aa5940499 (HEAD) | **Mode**: Full
**Deployment profile**: Shop storefront on OKE
**Repo**: `https://github.com/adibirzu/octo-drone-shop`
**Repository layout note**: this report describes the standalone shop repo only

## Executive Summary
SSO is not "broken" — it had never been implemented. The shop only had a custom HMAC bearer-token login (`server/modules/auth.py`) wired into `main.py`. This audit found three security issues (CRIT) and three code-portability gaps (HIGH) and fixes all of them with a fresh, hardened OIDC + PKCE + JWKS-verified SSO module ported from the working `enterprise-crm-portal` flow but stripped of its intentional vulnerabilities.

After the changes:
- App boots with **92 routes**, 4 of them new SSO routes.
- CORS no longer falls back to wildcard.
- Bearer-token signing key requires `AUTH_TOKEN_SECRET` in production (fail-fast).
- Standalone K8s manifest is tenancy-portable via `${OCI_LB_SUBNET_OCID}`.
- Any external deployment wrapper remains free to render its own manifest.
- Existing OTel→APM wiring (with `shared.observability_lib` fallback) is correct and untouched.

## Findings

### CRITICAL — fixed

**CRIT-1: HMAC signing key falls back to credentials and a literal**
- **Where**: `server/auth_security.py:24-32`
- **What**: `_secret_bytes()` chained `AUTH_TOKEN_SECRET → oracle_password → splunk_hec_token → oracle_dsn → "octo-default-secret"`
- **Impact**: Tokens forgeable by anyone who knows the literal; sessions silently invalidated on credential rotation.
- **Fix**: New `_resolve_secret_material()` requires `AUTH_TOKEN_SECRET` in production (raises `RuntimeError`); in dev generates a per-process random secret with a `WARNING` log. `Config.validate()` enforces the same rule at startup.
- **Verified**:
  - `ENVIRONMENT=production AUTH_TOKEN_SECRET="" → RuntimeError`
  - `ENVIRONMENT=development → ephemeral secret + warning`
  - `issue_token` / `verify_token` roundtrip OK in dev.

**CRIT-2: CORS wildcard with credentials**
- **Where**: `server/main.py:96-101`
- **What**: `_cors_origins or ["*"]` combined with `allow_credentials=True`. Empty/whitespace env value silently became wildcard.
- **Fix**: Strip `*`, never default to `["*"]`. If filtering produces an empty list, **don't install** the CORS middleware at all and log a `WARNING` so operators see what happened. Wildcard with credentials is now structurally impossible.
- **Verified**:
  - `CORS_ALLOWED_ORIGINS="" → middleware not installed, warning logged`
  - `CORS_ALLOWED_ORIGINS=https://shop.example.cloud → middleware installed with that exact origin + credentials`

**CRIT-3: SSO not implemented**
- **Where**: nowhere — entire `server/` tree had no OIDC/IDCS code.
- **Fix**: New `server/modules/sso.py` (382 lines) implementing:
  - `GET /api/auth/sso/status` — returns `{configured, provider, domain_url, verify_jwt}`
  - `GET /api/auth/sso/login` — Authorization Code + PKCE (S256), state and code_verifier signed and stored in a short-lived `octo_sso_pkce` httpOnly cookie
  - `GET /api/auth/sso/callback` — verifies cookie, exchanges code for tokens, **verifies the IDCS ID token via JWKS** (`/admin/v1/SigningCert/jwk`) using PyJWT + RS256, validates `aud`/`iss`/`exp`/`iat`, upserts the local user, issues our existing HMAC bearer token in an httpOnly `octo_session` cookie
  - `GET /api/auth/sso/logout` — clears cookies and (when configured) redirects to IDCS' user-logout endpoint
- **Hardening over the CRM port**:
  - JWT signature verification is **on by default**; `IDCS_VERIFY_JWT=false` exists only as an emergency bypass for air-gapped dev and logs a warning when used
  - JWKS keys cached for 1h with automatic refresh on key-id mismatch (handles rotation)
  - PKCE cookie has its own TTL (10 min) and is signed with the same secret as the bearer token, so it inherits the strict-secret requirement
  - User role is **not** taken from the ID token claims (mass-assignment guard) — SSO users get `role=user` and admins are managed locally
  - SSO-provisioned users get a non-bcrypt password hash (`sso:<sub>`) so they can never log in via the password endpoint
  - CSRF state-mismatch and tampered-cookie events emit `security_span("csrf", severity="high", ...)` for OCI APM correlation

### HIGH — fixed

**HIGH-1: Exception handler leaks types/paths in production**
- **Where**: `server/main.py:289-301`
- **Fix**: In production, return only `{"error": "Internal server error"}`. Detailed type/path/message is still logged via `push_log("ERROR", ...)` so observability is not lost.

**HIGH-2: Hardcoded subnet OCID makes standalone deploy not portable**
- **Where**: `deploy/k8s/deployment.yaml:217` had a literal Frankfurt subnet OCID.
- **Fix**: Replaced with `${OCI_LB_SUBNET_OCID}`. Install guide section 9 now documents the `envsubst` render pattern, and any deployment wrapper can inject its own subnet value at render time.
- **Verified**: `grep "ocid1.subnet" deploy/k8s/deployment.yaml` returns nothing; only the placeholder remains.

**HIGH-3: AUTH_TOKEN_SECRET silently optional in K8s deployment**
- **Where**: `deploy/k8s/deployment.yaml` had `optional: true` on the `octo-auth/token-secret` secret.
- **Fix**: Removed `optional: true`. Pod will now fail to start in production unless the secret exists, which is the desired behavior.

### MEDIUM — accepted / documented

| ID    | Where                       | Status                                                                                  |
|-------|-----------------------------|-----------------------------------------------------------------------------------------|
| MED-1 | `oracle_user` defaults to `ADMIN` | Documented in install guide section 4. Changing requires DB migration; tracked, not blocking. |
| MED-2 | `/api/cart/add` accepts unauth payload | Existing `security_span` instrumentation + WAF rate limiting cover this; behavior is intentional for the demo. |
| MED-3 | `requirements.txt` lacked PyJWT | Added `PyJWT[crypto]==2.10.1` for JWKS-verified ID tokens. |

## OTel → OCI APM verification
`server/observability/otel_setup.py` is **correct as-is** and was not modified by this audit:
1. Tries `shared.observability_lib.init_observability()` first (the shared deployment path that gives traces, metrics, and a unified Resource).
2. Falls back to a local standalone init that:
   - Builds a `Resource` with full service/host/runtime attributes
   - Configures `OTLPSpanExporter` → `${APM_BASE}/20200101/opentelemetry/private/v1/traces` with `Authorization: dataKey ${KEY}`
   - Configures `OTLPMetricExporter` → `/v1/metrics` (for App Server metrics) — known to work for metrics, the earlier 404 with `/private/v1/metrics` was already fixed in commit `83d8af1`
   - Optionally enables OTLP log export when `OTLP_LOG_EXPORT_ENABLED=true`
3. Always instruments SQLAlchemy (sync + async sync_engine), httpx (W3C traceparent propagation), and stdlib logging.
4. Adds DB span enrichment via SQLAlchemy `before_cursor_execute` / `after_cursor_execute` events (statement, bind count, execution time, row count, db trace_id).

The CRM-side cross-service trace context is auto-injected by `HTTPXClientInstrumentor`, which is what makes `/api/integrations/crm/customer-enrichment` show as a single distributed trace in OCI APM.

## ATP integration verification
`server/database.py` and `server/config.py` cleanly support both backends:
- `oracle_dsn` set → `oracle+oracledb_async://` async engine + `oracle+oracledb://` sync engine, both relying on the wallet at `ORACLE_WALLET_DIR`.
- `DATABASE_URL` set + `oracle_dsn` empty → falls back to `postgresql+asyncpg://`.
- `Config.validate()` already refuses to start when `ORACLE_DSN` is set without `ORACLE_PASSWORD`.
- `/ready` returns `database: connected` only after a real `SELECT 1 FROM DUAL` round-trip, so K8s readiness probe waits for the wallet/DSN to actually work.

No changes needed.

## Files changed by this audit
| File                                              | Change                                                              |
|---------------------------------------------------|---------------------------------------------------------------------|
| `requirements.txt`                                | Added `PyJWT[crypto]==2.10.1`                                       |
| `server/config.py`                                | Added IDCS fields + `idcs_configured` + strict `validate()`         |
| `server/auth_security.py`                         | Replaced credential fallback with strict/lenient secret resolution  |
| `server/main.py`                                  | Fixed CORS, fixed exception handler, mounted SSO router, ctx update |
| `server/modules/sso.py`                           | **NEW** — OIDC + PKCE + JWKS-verified SSO module (382 lines)        |
| `server/templates/login.html`                     | Added "Sign in with OCI IAM (IDCS)" button + sso_error display      |
| `deploy/k8s/deployment.yaml`                      | Subnet placeholder; new IDCS env vars; AUTH_TOKEN_SECRET required   |
| `.env.example`                                    | IDCS_* + `OCI_LB_SUBNET_OCID`                                       |
| `.env.local.example`                              | IDCS_* + comment on `AUTH_TOKEN_SECRET` behavior                    |
| `docs/install-guide.md`                           | Section 9 (envsubst rendering) + new section 11 (IDCS SSO setup)    |
| `.gitignore`                                      | Added `.rlm/`                                                       |
| `.rlm/2026-04-09/synthesis.md`                    | Audit checkpoint (gitignored)                                       |
| `rlm_security_sso_audit_report.md`                | This report                                                         |

## Verification matrix

| Check                                                         | Result |
|---------------------------------------------------------------|--------|
| `python3 -m py_compile` of all modified Python files          | ✅ OK   |
| `from server.main import app` (full app boot)                 | ✅ 92 routes, 4 SSO routes mounted at `/api/auth/sso/*` |
| `cfg.validate()` in dev with empty `AUTH_TOKEN_SECRET`        | ✅ OK + warning |
| `cfg.validate()` in production with empty `AUTH_TOKEN_SECRET` | ✅ Raises `RuntimeError` |
| `issue_token` / `verify_token` roundtrip                      | ✅ OK   |
| SSO PKCE cookie sign / verify roundtrip                       | ✅ OK   |
| SSO PKCE cookie tampering detection                           | ✅ Returns `None` |
| Empty `CORS_ALLOWED_ORIGINS` env                              | ✅ Middleware not installed, warning logged |
| Explicit `CORS_ALLOWED_ORIGINS` env                           | ✅ Middleware installed with that exact origin + credentials |
| K8s manifest grep for hardcoded OCIDs                         | ✅ No literal OCIDs remain |

## What's NOT in scope (by design)
- The seeded admin/shopper passwords in `db_init.sql` are still demo defaults — this is intentional for a demo app.
- The shop's existing intentional MITRE/security spans (`security_span("brute_force", ...)`, `security_span("mass_assign", ...)`) are demo telemetry, not bugs.
- Frontend RUM beacon configuration is unchanged — it works via `cfg.rum_configured` in templates.
- The vendored `enterprise-crm-portal` SSO is left as-is. It is intentionally vulnerable. The drone shop now has its own clean implementation.
