# Quick Start

## Clone the Unified Repo

```bash
git clone https://github.com/example-org/octo-apm-demo.git
cd octo-apm-demo
```

## Verify the Repo Surface

```bash
python3 -m pytest -q tests/test_unified_deploy_surface.py
bash deploy/verify.sh
```

This validates the deploy scripts, manifests, Helm chart, docs build,
and the core Python test suites without touching a tenancy.

## Bootstrap a Fresh Tenancy

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
DNS_BASE_DOMAIN=example.test \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh
```

For a non-`DEFAULT` tenancy, replace `example.test` with your own base
domain and point `OCI_PROFILE` at the correct OCI config profile.

## Roll Forward After Bootstrap

```bash
OCIR_REGION=<region> \
OCIR_TENANCY=<namespace> \
DNS_DOMAIN=<your-domain> \
./deploy/deploy.sh
```

## Hand Off to E2E

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
CRM_BASE_URL=https://crm.<your-domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts
```

Add `SSO_E2E_ENABLED=1` plus test-user credentials only after the
Identity Domain app and `octo-sso` secret are in place.
