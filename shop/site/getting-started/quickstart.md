# Quick Start

## Local shop development

```bash
cd shop
docker compose up -d

curl http://localhost:8080/health
curl http://localhost:8080/ready
```

Open `http://localhost:8080/shop` for the storefront.

## Unified repo verification

Before touching a tenancy, validate the repo surface from the root:

```bash
python3 -m pytest -q tests/test_unified_deploy_surface.py
bash deploy/verify.sh
```

## Fresh-tenancy bootstrap

For the current unified deployment path, run the root bootstrap flow:

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
DNS_BASE_DOMAIN=cyber-sec.ro \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh
```

For a non-`DEFAULT` tenancy, replace `cyber-sec.ro` with your own base
domain.

## E2E hand-off

```bash
SHOP_BASE_URL=https://shop.<your-domain> \
CRM_BASE_URL=https://crm.<your-domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts
```
