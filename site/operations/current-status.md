# Current Status

Snapshot date: **April 23, 2026**

This page records the current validated state of the unified OCTO deployment in the `oci4cca` tenancy using the `DEFAULT` OCI profile.

## Tenancy confirmation

- `DEFAULT` OCI profile resolves to tenancy `oci4cca`.
- `cap` OCI profile resolves to a different tenancy, `pbncapgemini`.
- The unified OCI Resource Manager stack was created in the right tenancy: compartment `Adrian_Birzu`, stack `octo-apm-demo-unified-stack`.

## DNS and cutover status

- The intended `oci4cca` public hostnames are `shop.cyber-sec.ro` and `crm.cyber-sec.ro`.
- The OCI DNS zone `cyber-sec.ro` exists in compartment `Adrian_Birzu`.
- OCI DNS A records for `shop.cyber-sec.ro` and `crm.cyber-sec.ro` are present in that zone and now point to the active ingress IP `144.24.173.224`.
- Public internet delegation for `cyber-sec.ro` is still pointed at Wix nameservers, not the OCI nameservers for the `Adrian_Birzu` zone.
- Public DNS currently resolves both hostnames to `144.24.173.224`, so browser access is live today.
- Operational implication: until the registrar delegation moves from Wix to OCI, the public Wix-hosted rrsets and the OCI zone must stay aligned.

## TLS status

- OCI Certificates contains an imported certificate named `star.cyber-sec.ro`.
- Its current certificate bundle resolves to version `4`, valid from **April 23, 2026** until **November 7, 2026**.
- The deployment scripts now load that certificate and private key into Kubernetes TLS secrets named `cyber-sec-ro-tls` so the shared ingress can terminate `shop.cyber-sec.ro` and `crm.cyber-sec.ro`.
- Result: direct `https://shop.cyber-sec.ro/ready` and `https://crm.cyber-sec.ro/ready` return `200 OK`, and plain HTTP now redirects to HTTPS.

## Runtime status

- OKE cluster: `cluster1`
- Managed node pool: `octo-apm-managed-pool`
- Shared ingress controller: `ingress-nginx/nginx-ingress-ingress-nginx-controller` at `2/2`
- Shared ingress IP: `144.24.173.224`
- ATP: `octo-apm-demo-atp`
- Shop deployment: `octo-drone-shop` at `2/2` in namespace `octo-drone-shop`
- CRM deployment: `enterprise-crm-portal` at `2/2` in namespace `enterprise-crm`
- Public HTTPS `/ready` returns `ready=true` for both `shop.cyber-sec.ro` and `crm.cyber-sec.ro`.
- Public HTTP `/ready` redirects to the equivalent HTTPS endpoint for both hosts.
- Both `/api/integrations/schema` endpoints resolve correctly through the public `cyber-sec.ro` hosts.
- Legacy ingress hostnames still present in the cluster: `shop.octodemo.cloud` and `crm.octodemo.cloud`

## Observability status

- Server-side APM is configured in both apps (`apm_configured=true` on both `/ready` endpoints).
- Browser RUM is active on both apps (`rum_configured=true` on both `/ready` endpoints).
- OCI Logging is configured in both namespaces, including the app, chaos audit, and security log OCIDs.
- OCI Logging Analytics is wired through the created service connector for the application log stream.
- The optional OCI APM RUM web-application OCID remains unset; beacon ingestion still works, but named RUM application metadata remains a manual OCI Console step.

## What was wrong

- The repo and docs treated CAP endpoints (`shop.octodemo.cloud`, `crm.octodemo.cloud`) as if they were the validated `oci4cca` public surface.
- Several deployment examples still hardcoded `octodemo.cloud`, which pushed operators toward the wrong tenancy/domain pairing.
- The root bootstrap path had a real functional bug: generated Ingress objects always targeted service port `80` even when the actual backend services exposed `8080`.
- The legacy bootstrap/init flow also generated per-namespace auth keys, skipped the OCIR pull secret, and wrote empty observability secrets into CRM, which broke the unified manifests on a clean redeploy.

## Current remediation

- `deploy/deploy.sh` exists and remains the canonical unified build/push/rollout wrapper.
- `deploy/bootstrap.sh` now routes generated Ingress objects to the declared backend service port, reuses the shared ingress controller, imports the OCI wildcard certificate, and preserves non-empty APM / Logging / integration secrets.
- `deploy/init-tenancy.sh` now keeps auth consistent across both namespaces, recreates `ocir-pull-secret`, and can sync wallet / observability secrets instead of leaving CRM blank.
- `deploy/destroy.sh` now defaults to deleting only the shop / CRM workloads and keeps shared ingress and the managed node pool unless explicitly asked to remove them.
- `deploy/resource-manager/upsert-stack.sh` packages and creates or updates the unified OCI Resource Manager stack from this repo.
- Deployment comments, wizard defaults, and E2E defaults now target `cyber-sec.ro` for `DEFAULT` / `oci4cca`.
- The docs now distinguish the `oci4cca` target domain from the legacy CAP reference endpoints.

## Legacy CAP reference

- `https://shop.octodemo.cloud`
- `https://crm.octodemo.cloud`

Those hostnames still resolve through the existing `octodemo.cloud` ingress path, but they are not the correct public domain for `oci4cca`.

## Validation notes

- Focused root regression test: `tests/test_unified_deploy_surface.py`
- Broader script/doc validator: `deploy/verify.sh`
