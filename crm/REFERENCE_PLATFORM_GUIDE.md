# Reference Platform Guide

**Date**: 2026-03-12  
**Scope**: Sanitized technical reference for the CRM, shop, shared database, and optional operator services.

## Public surfaces

- CRM: `https://crm.example.cloud`
- Shop: `https://shop.example.cloud`
- Optional ops surface: `https://ops.example.cloud`

Use placeholders in tracked files. Inject real domains through `DNS_DOMAIN`,
`CRM_BASE_URL`, `OCTO_DRONE_SHOP_URL`, `CONTROL_PLANE_URL`, and
`PLATFORM_BACKEND_URL` at deploy time.

## Core service boundaries

- CRM is the operational control surface for customers, orders, invoices,
  products, storefront settings, and catalog synchronization.
- Shop is the public storefront. It should not expose write endpoints for
  catalog or chaos control.
- Shared database access must be configured through secret-backed env vars or
  `*_FILE` mounted secrets.
- Optional operator services such as browser access, automation backends, and
  observability drilldowns should be configured through generic endpoint
  variables rather than hardcoded environment names.

## Portable runtime variables

| Purpose | Variable |
| --- | --- |
| CRM public URL | `CRM_BASE_URL` |
| Shop public or service URL | `OCTO_DRONE_SHOP_URL` |
| Control plane URL | `CONTROL_PLANE_URL` |
| Platform backend URL | `PLATFORM_BACKEND_URL` |
| Shared DNS suffix | `DNS_DOMAIN` |
| Bootstrap admin credential | `BOOTSTRAP_ADMIN_PASSWORD` or `BOOTSTRAP_ADMIN_PASSWORD_FILE` |
| App signing secret | `APP_SECRET_KEY` or `APP_SECRET_KEY_FILE` |

## Security checklist

- Keep secrets in `deploy/credentials.env`, OCI Vault mounts, Kubernetes
  secrets, or `*_FILE` paths. Do not commit populated env files.
- Do not expose internal `.cluster.local` or `.svc.cluster.local` hostnames in
  HTML, API responses, docs, or frontend config.
- Do not ship default credentials in tracked files. Bootstrap admin access
  should come from a deploy-time secret.
- Use explicit CORS origins. Do not combine wildcard origins with
  `allow_credentials=true`.
- Administrative routes must require authenticated management or admin roles.

## Verification workflow

1. Populate `.env` from `.env.example`.
2. Populate `deploy/credentials.env` from `deploy/credentials.template`.
3. Run the app locally or in your target cluster.
4. Verify `/health`, `/ready`, CRM data pages, and catalog sync.
5. Run targeted tests plus a tracked-file grep for live domains, private
   hostnames, and secret-looking values before pushing.

## Observability expectations

- Distributed traces should propagate between CRM, shop, and DB-facing code.
- Runtime summaries and admin config views must return sanitized values only.
- Console drilldowns should use deploy-time URLs, not hardcoded tenant links.
- k6 and smoke-test scripts should require credentials via env vars instead of
  embedding passwords in the repository.
