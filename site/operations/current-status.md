# Current Status

Snapshot date: **April 24, 2026**

This page records the current validated state of the unified OCTO deployment in the `oci4cca` tenancy using the `DEFAULT` OCI profile.

## Tenancy confirmation

- `DEFAULT` OCI profile resolves to tenancy `oci4cca`.
- `cap` OCI profile resolves to a different tenancy, `pbncapgemini`.
- The unified OCI Resource Manager stack was created in the right tenancy: compartment `Adrian_Birzu`, stack `octo-apm-demo-unified-stack`.

## DNS and cutover status

- The intended `oci4cca` public hostnames are `shop.cyber-sec.ro` and `crm.cyber-sec.ro`.
- The OCI DNS zone `cyber-sec.ro` exists in compartment `Adrian_Birzu`.
- OCI DNS A records for `shop.cyber-sec.ro` and `crm.cyber-sec.ro` are present in that zone and now point to the active ingress IP `144.24.173.224`.
- Public internet delegation for `cyber-sec.ro` is still pointed at Wix nameservers (`ns2.wixdns.net`, `ns3.wixdns.net`), not the OCI nameservers for the `Adrian_Birzu` zone.
- As of April 24, 2026, public resolvers such as `1.1.1.1` return **no A record** for either `shop.cyber-sec.ro` or `crm.cyber-sec.ro`.
- Operational implication: until the active Wix-hosted rrsets are updated or delegation moves from Wix to OCI, the apps are not publicly reachable by normal DNS resolution.

## TLS status

- OCI Certificates contains an imported certificate named `star.cyber-sec.ro`.
- Its current certificate bundle resolves to version `4`, valid from **April 23, 2026** until **November 7, 2026**.
- The deployment scripts now load that certificate and private key into Kubernetes TLS secrets named `cyber-sec-ro-tls` so the shared ingress can terminate `shop.cyber-sec.ro` and `crm.cyber-sec.ro`.
- `openssl s_client -connect 144.24.173.224:443 -servername shop.cyber-sec.ro` presents `CN=*.cyber-sec.ro`.
- Result: host-routed HTTPS checks with `curl --resolve` return `200 OK` for both `/ready` endpoints, and plain HTTP on the ingress redirects to HTTPS.

## Runtime status

- OKE cluster: `cluster1`
- Managed node pool: `octo-apm-managed-pool`
- Shared ingress controller: `ingress-nginx/nginx-ingress-ingress-nginx-controller` at `2/2`
- Shared ingress IP: `144.24.173.224`
- ATP: `octo-apm-demo-atp` at `AVAILABLE`
- Managed ingress nodes `10.0.10.20` and `10.0.10.36` are back to `Ready`
- Shop deployment: `octo-drone-shop` at `2/2` in namespace `octo-drone-shop`
- CRM deployment: `enterprise-crm-portal` at `2/2` in namespace `enterprise-crm`
- `curl --resolve shop.cyber-sec.ro:443:144.24.173.224 https://shop.cyber-sec.ro/ready` returns `ready=true` and `database=connected`.
- `curl --resolve crm.cyber-sec.ro:443:144.24.173.224 https://crm.cyber-sec.ro/ready` returns `ready=true` and `database=connected`.
- Public browser access through normal DNS is still blocked until the authoritative `A` records are fixed at the active DNS provider.
- Legacy ingress hostnames still present in the cluster: `shop.octodemo.cloud` and `crm.octodemo.cloud`

## Observability status

- Both namespaces have populated `octo-apm` secrets with the APM endpoint plus public/private data keys.
- Both `/ready` endpoints report `apm_configured=true` and `rum_configured=true`.
- Both namespaces have populated `octo-logging` secrets with the shared OCI log group, application log, chaos-audit log, and security log OCIDs.
- OCI Logging log group `octo-apm-demo` is `ACTIVE`.
- OCI Service Connector `la-pipeline-octo-shop-app` is `ACTIVE`, so the Log Analytics pipeline for the shop application log stream exists.
- OCI Stack Monitoring onboarding for the ATP is still a manual/conditional step because the current helper requires a management agent plus DB connection details.

## What was wrong

- The repo and docs treated `cyber-sec.ro` as publicly live just because the OCI DNS zone and `A` records existed, even though the internet was still delegated to Wix.
- ATP had been left in `STOPPED`, which caused both apps to fail Oracle ATP startup and readiness.
- The managed ingress nodes had been left stopped as well, which broke the shared `ingress-nginx` controller.
- The service rollout scripts verified only through the public hostname, so they could report a failed deployment even when the ingress, TLS certificate, and app pods were healthy behind the load balancer.
- Earlier bootstrap/init bugs around ingress port selection, OCIR pull secrets, and per-namespace secret drift were already fixed in the April 23 deploy-script cleanup.

## Current remediation

- `deploy/deploy.sh` exists and remains the canonical unified build/push/rollout wrapper.
- `deploy/bootstrap.sh` now routes generated Ingress objects to the declared backend service port, reuses the shared ingress controller, imports the OCI wildcard certificate, preserves non-empty APM / Logging / integration secrets, and automatically falls back to manual DNS mode when the OCI zone is not the public authority.
- `deploy/init-tenancy.sh` now keeps auth consistent across both namespaces, recreates `ocir-pull-secret`, and can sync wallet / observability secrets instead of leaving CRM blank.
- `deploy/destroy.sh` now defaults to deleting only the shop / CRM workloads and keeps shared ingress and the managed node pool unless explicitly asked to remove them.
- `deploy/deploy.sh` now auto-starts a stopped ATP before rollout and fails early if the shared ingress is unhealthy.
- `deploy/deploy-shop.sh` and `deploy/deploy-crm.sh` now verify through the ingress IP with `--resolve`, so rollout validation still works before public DNS cutover.
- `deploy/oci/ensure_atp.sh` now starts a stopped existing ATP instead of treating it as already usable.
- `deploy/resource-manager/upsert-stack.sh` packages and creates or updates the unified OCI Resource Manager stack from this repo.
- Deployment comments, wizard defaults, E2E defaults, and the published docs now target `cyber-sec.ro` for `DEFAULT` / `oci4cca` while calling out the remaining DNS cutover blocker explicitly.

## Legacy CAP reference

- `https://shop.octodemo.cloud`
- `https://crm.octodemo.cloud`

Those hostnames still resolve through the existing `octodemo.cloud` ingress path, but they are not the correct public domain for `oci4cca`.

## Validation notes

- Focused root regression test: `tests/test_unified_deploy_surface.py`
- Broader script/doc validator: `deploy/verify.sh`
- Live DNS check: `dig +short NS cyber-sec.ro @1.1.1.1`
- Live ingress/TLS checks:
  - `curl --resolve shop.cyber-sec.ro:443:144.24.173.224 https://shop.cyber-sec.ro/ready`
  - `curl --resolve crm.cyber-sec.ro:443:144.24.173.224 https://crm.cyber-sec.ro/ready`
