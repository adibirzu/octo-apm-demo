# Deploying to a New OCI Tenancy

The current canonical new-tenancy flow lives at the repo root. Use the
root docs and scripts, then return here for shop-specific follow-up.

## Canonical bootstrap

From the repo root:

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
DNS_BASE_DOMAIN=cyber-sec.ro \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh
```

That flow provisions or reconnects ATP, seeds the shared secrets,
builds and deploys Shop + CRM, and publishes `shop.<domain>` plus
`crm.<domain>`.

## Canonical docs

- Root new-tenancy guide: `site/getting-started/new-tenancy.md`
- Root quickstart: `site/getting-started/quickstart.md`
- Root E2E hand-off: `site/testing/e2e.md`
- Current shared-tenancy status: `site/operations/current-status.md`

## Shop-specific follow-up

After the unified bootstrap is healthy, use the shop-local surface for
feature regression:

```bash
cd shop
npm install
npm run test:e2e
```

For live-tenancy smoke, switch back to the root Playwright specs under
`tests/e2e/`.
