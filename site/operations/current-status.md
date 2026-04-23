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
- OCI DNS A records for `shop.cyber-sec.ro` and `crm.cyber-sec.ro` are present in that zone and now point to the active ingress IP `144.24.178.176`.
- Public internet delegation for `cyber-sec.ro` is still pointed at Wix nameservers, not the OCI nameservers for the `Adrian_Birzu` zone.
- Result: the OCI DNS records are correct inside OCI, but public resolution for `shop.cyber-sec.ro` / `crm.cyber-sec.ro` is not live yet. External cutover still requires either:
  1. changing the registrar delegation from Wix to OCI, or
  2. publishing the same A records at Wix.

## TLS status

- The current ingress TLS secret in the cluster is `*.octodemo.cloud`, not `*.cyber-sec.ro`.
- OCI Certificates contains an imported certificate named `star.cyber-sec.ro`.
- Its current version is expired: validity ended on **April 16, 2025**.
- Result: HTTP host routing for `shop.cyber-sec.ro` / `crm.cyber-sec.ro` now works through the ingress IP, but public HTTPS cutover still needs a renewed `cyber-sec.ro` certificate wired into Kubernetes or the edge load balancer.

## Runtime status

- OKE cluster: `cluster1`
- Managed node pool: `octo-apm-managed-pool`
- ATP: `octo-apm-demo-atp`
- Shop pod: running in namespace `octo-drone-shop`
- CRM pod: running in namespace `enterprise-crm`
- HTTP host-header smoke checks through `144.24.178.176` now return `ready=true` for both `shop.cyber-sec.ro` and `crm.cyber-sec.ro`.
- Both `/api/integrations/schema` endpoints also resolve correctly through those `cyber-sec.ro` hosts when routed via the ingress IP.
- Legacy ingress hostnames still present in the cluster: `shop.octodemo.cloud` and `crm.octodemo.cloud`

## What was wrong

- The repo and docs treated CAP endpoints (`shop.octodemo.cloud`, `crm.octodemo.cloud`) as if they were the validated `oci4cca` public surface.
- Several deployment examples still hardcoded `octodemo.cloud`, which pushed operators toward the wrong tenancy/domain pairing.
- The root bootstrap path had a real functional bug: generated Ingress objects always targeted service port `80` even when the actual backend services exposed `8080`.

## Current remediation

- `deploy/deploy.sh` exists and remains the canonical unified build/push/rollout wrapper.
- `deploy/bootstrap.sh` now routes generated Ingress objects to the declared backend service port instead of a hardcoded `80`.
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
