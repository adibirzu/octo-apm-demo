# Guided demo rollout

This runbook promotes the guided event-generation UI, Captured Data Center, and
documentation updates to the supported runtimes without exposing tenancy-specific
details. Keep real hostnames, OCIDs, IPs, credential paths, profile names, and
operator allowlists in ignored operator notes or environment files.

## Scope

The change set is app/docs only:

- Admin Simulation Lab presenter guide.
- Shop checkout observability guide and captured-data pivots.
- Admin `/captured-data` operator page.
- Public docs for event generation, APM presentation, Log Analytics pivots,
  OKE, and private VM/Compute architecture.

Do **not** run Terraform for this rollout unless a separate infrastructure drift
change is explicitly approved.

## Preflight

Run from the repo root:

```bash
python -m pytest \
  crm/tests/test_observability_guidance_surfaces.py \
  shop/tests/test_dashboard_demo_page.py \
  tests/test_log_analytics_attack_assets.py \
  -q

python -m mkdocs build --strict

rg -n "<TENANCY_LEAKAGE_PATTERN>" site README.md ARCHITECTURE.md mkdocs.yml || true
```

Expected result:

- tests pass
- docs build succeeds
- leakage scan returns no matches except intentionally redacted examples such as
  placeholder OCID fragments ending in `..xxxx`

Use the project regression test as the authoritative public-doc leakage scan;
it blocks live profile names, live domains, concrete public/private IP fragments,
real OCIR namespace values, and concrete attack ids from public Markdown.

## Private VM/Compute rollout

Use this path when public host routing still targets the VM/Compute backend
sets.

1. Build or copy the scoped app changes to the private Shop and CRM hosts using
   the existing app deployment wrapper or a scoped file copy.
2. Rebuild the local container images on each host if the runtime uses local
   image tags.
3. Restart only the application service, for example the host-managed
   `octo-compute.service`.
4. Validate readiness through the load balancer with placeholder hostnames:

```bash
curl -k -fsS --resolve shop.example.test:443:<LB_PUBLIC_IP> \
  https://shop.example.test/ready | jq

curl -k -fsS --resolve admin.example.test:443:<LB_PUBLIC_IP> \
  https://admin.example.test/ready | jq
```

5. Browser-validate:
   - `https://admin.example.test/settings` shows **Event Generation Guide**.
   - `https://admin.example.test/captured-data` shows **Captured Data Center**.
   - `https://shop.example.test/shop` checkout panel shows **What this checkout
     generates**.

6. Generate one safe Demo Storyboard or manual checkout and confirm:
   - an APM trace can be opened by `TraceId`
   - `checkout-payment-correlation` can be filtered by `Trace ID` or `Order ID`
   - `/captured-data` builds the same pivots without exposing secrets

## OKE rollout

Use this path when deploying the same app changes into Kubernetes, either staged
behind NodePort backend sets or after host-routing cutover.

1. Build Shop, CRM, and Java images with an immutable tag:

```bash
IMAGE_TAG=<IMAGE_TAG> ./deploy/oke/build-push-images.sh
```

2. Dry-run manifests first:

```bash
APPLY=false IMAGE_TAG=<IMAGE_TAG> ./deploy/oke/deploy-oke.sh
```

3. Apply only after the dry run is clean:

```bash
APPLY=true IMAGE_TAG=<IMAGE_TAG> ./deploy/oke/deploy-oke.sh
```

4. Verify rollout status:

```bash
kubectl -n octo-drone-shop rollout status deploy/octo-drone-shop
kubectl -n enterprise-crm rollout status deploy/enterprise-crm-portal
kubectl -n octo-drone-shop rollout status deploy/octo-java-app-server
```

5. If OKE is staged behind existing LB backend sets, validate through the staged
   backend/NodePort path before host-routing cutover. If OKE has been promoted,
   validate via the same public placeholder hostnames used by VM/Compute.

6. Confirm OCI Kubernetes Monitoring and Log Analytics still ingest app/container
   logs. Kubernetes log source names can differ from VM/Compute, but the app
   field contract should still include `Trace ID`, `Order ID`, `Payment Gateway
   Request ID`, and `Attack ID` where applicable.

## APM presentation smoke test

Use the same demo script for both runtimes:

1. Admin Simulation Lab → **Demo Storyboard**.
2. Copy `trace_id`, `order_id`, and `payment_gateway_request_id`.
3. Captured Data Center → paste the keys and copy the generated pivots.
4. OCI APM Trace Explorer → open the trace or use `OCTO APM - checkout end-to-end`.
5. Log Analytics → run `checkout-payment-correlation` with the generated filter.
6. If Java App Servers is empty, regenerate **Java Health** and verify the Java
   sidecar/deployment is running with the OCI APM Java agent app-server flags.

## Rollback

- VM/Compute: restart the previous container image/tag or restore the previous
  scoped app files and restart the application service.
- OKE: use `kubectl rollout undo` for the affected Deployments or redeploy the
  previous immutable image tag.
- Docs: revert the docs commit or redeploy the previous static site artifact.
