# Deploying to a New OCI Tenancy

The canonical fresh-tenancy path is `deploy/bootstrap.sh`. It provisions
or reconciles the shared OCI surface and lands **both** Shop and CRM
into the cluster. Use `deploy/init-tenancy.sh` only when you already own
the cluster, ATP, and ingress lifecycle yourself and want a staged
bootstrap.

## 1. Prerequisites

- OCI profile with access to the target compartment.
- OKE cluster reachable from `kubectl`.
- Remote x86_64 build host reachable over SSH.
- Local tools: `oci`, `kubectl`, `terraform`, `docker`, `envsubst`, `ssh`, `helm`.
- Planned public hostnames for `shop.<domain>` and `crm.<domain>`.

For the shared `DEFAULT` profile, the baked-in domain is `example.test`.

## 2. Optional pre-flight

Run the light validator before the full bootstrap:

```bash
DNS_DOMAIN=<your-domain> \
OCIR_REPO=<region>.ocir.io/<namespace>/octo-drone-shop \
K8S_NAMESPACE=octo-drone-shop \
./deploy/pre-flight-check.sh
```

`deploy/pre-flight-check.sh` validates the minimum env surface and flags
placeholder values before you start touching the tenancy.

## 3. Recommended path: `deploy/bootstrap.sh`

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
DNS_BASE_DOMAIN=example.test \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh
```

`deploy/bootstrap.sh` is idempotent and handles the end-to-end flow:

1. validates the OCI profile and kube context
2. caches the selected tenancy in `deploy/.last-tenancy.env`
3. creates OCIR repos
4. provisions or reconnects ATP
5. seeds wallet/auth/logging/OCI secrets in both namespaces
6. builds and pushes Shop + CRM images
7. applies manifests or ingress resources
8. reuses or installs shared ingress
9. loads TLS material when available
10. writes DNS records when the active zone is writable
11. smoke-checks the deployed URLs

Use `deploy/deploy.sh` for subsequent rollouts after bootstrap succeeds.

## 4. Staged path: `deploy/init-tenancy.sh` + `deploy/deploy.sh`

Choose this path only when the OKE cluster, ATP, ingress, and DNS are
already managed out-of-band:

```bash
DNS_DOMAIN=<your-domain> \
OCIR_REGION=<region> \
OCIR_TENANCY=<namespace> \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
./deploy/init-tenancy.sh

OCIR_REGION=<region> \
OCIR_TENANCY=<namespace> \
DNS_DOMAIN=<your-domain> \
./deploy/deploy.sh
```

`deploy/init-tenancy.sh` seeds repos, namespaces, and shared secrets but
does not replace the full bootstrap lifecycle.

## 5. Optional observability wiring

APM, RUM, Log Analytics, and Stack Monitoring remain tenancy-specific.
The main references are:

- `deploy/OBSERVABILITY-BOOTSTRAP.md`
- `deploy/terraform/README.md`
- `python3 shop/tools/create_la_source.py --la-namespace ... --la-log-group-id ...`

The Log Analytics helper above is the current in-repo source registration
tool; older docs that mention `deploy/oci/ensure_la_sources.sh` are stale.

## 6. Hand-off to E2E

Do not start Playwright until all of the following are true:

1. `kubectl get deploy -n octo-drone-shop octo-drone-shop` shows `2/2`.
2. `kubectl get deploy -n enterprise-crm enterprise-crm-portal` shows `2/2`.
3. `kubectl -n ingress-nginx get endpoints` is non-empty.
4. `oci db autonomous-database get ...` shows `AVAILABLE`.
5. Public DNS resolves `shop.<your-domain>` and `crm.<your-domain>`.

Then run the root deployment E2E specs:

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
CRM_BASE_URL=https://crm.<your-domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts
```

If SSO is wired for the tenancy, add:

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
OCTO_E2E_TEST_USER_EMAIL=e2e@example.com \
OCTO_E2E_TEST_USER_PASSWORD='***' \
SSO_E2E_ENABLED=1 \
npx playwright test tests/e2e/sso-oidc-pkce.spec.ts
```
