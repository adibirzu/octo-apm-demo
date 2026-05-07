# Current Status

Snapshot date: **April 28, 2026**

This page records the latest observed state of the shared `DEFAULT`
deployment surface tracked by this repo. It is a runtime snapshot, not a
guarantee that the shared environment will remain healthy without checking
the validation commands below.

## Scope confirmed

- Local `~/.oci/config` resolves the `DEFAULT` profile in `eu-frankfurt-1`.
- The cached compartment is represented by `<COMPARTMENT_NAME>` via
  `deploy/.last-tenancy.env`.
- Current kube context for this deployment is represented by
  `<KUBE_CONTEXT>`.
- Bootstrap reused the existing OKE control plane represented by
  `<OKE_CLUSTER_NAME>`.
- Bootstrap used `<OCIR_NAMESPACE>` for image build and push because that is
  the namespace authorized on the remote build host.

## Public DNS status

- `example.test` is currently delegated to external DNS provider nameservers: `ns1.example.test` and `ns2.example.test`.
- The OCI DNS zone is not authoritative for public traffic, so bootstrap switches to `DNS_MODE=manual`.
- Public resolvers such as `1.1.1.1` currently return **no `A` record** for `shop.example.test` or `crm.example.test`.
- Add or update these records in external DNS provider before browser or Playwright tests can use the hostnames directly:

```text
shop.example.test.   A   203.0.113.30   TTL 60
crm.example.test.    A   203.0.113.30   TTL 60
```

Until external DNS provider is updated, use the ingress IP with `Host` headers for smoke and E2E checks.

## Runtime status

- Shared ingress `LoadBalancer` advertises `203.0.113.30`.
- `ingress-nginx/nginx-ingress-ingress-nginx-controller` is `2/2` available.
- The nginx admission service has live endpoints, so ingress creation succeeds.
- The managed worker instances backing ingress were found `STOPPED` again
  after the first successful run; they were restarted and the Kubernetes nodes
  represented by `<NODE_PRIVATE_IP_1>` and `<NODE_PRIVATE_IP_2>` returned to
  `Ready`.
- `deploy/bootstrap.sh` now checks existing nginx ingress readiness, starts stopped OCI worker instances referenced by NotReady real nodes, waits for node readiness, and refuses to continue if the ingress service still has no endpoints.

## Workload status

- `octo-drone-shop` is `2/2` ready in namespace `octo-drone-shop`.
- `enterprise-crm-portal` is `2/2` ready in namespace `enterprise-crm`.
- Current deployed images:
  - `<OCIR_REGION>.ocir.io/<OCIR_NAMESPACE>/octo-drone-shop:<IMAGE_TAG>`
  - `<OCIR_REGION>.ocir.io/<OCIR_NAMESPACE>/enterprise-crm-portal:<IMAGE_TAG>`
- Host-header readiness checks against the ingress IP return `ready=true` for both services.

## Database and secrets

- Autonomous Database `octo-apm-demo-atp` is `AVAILABLE`.
- Runtime DSN alias is `octoatp_low`.
- Required app secrets are seeded in both namespaces: `octo-atp`, `octo-atp-wallet`, `octo-auth`, `octo-logging`, `octo-oci-config`, `octo-integrations`, and `ocir-pull-secret`.
- Optional `octo-apm` and `octo-sso` secrets are absent, so APM/RUM- and SSO-specific flows are not enabled in this snapshot.

## E2E readiness

The shared `DEFAULT` tenancy is ready for deployed cross-service smoke using the ingress IP plus `Host` headers.

Validated on April 28, 2026:

- `bash deploy/verify.sh` passed with `0 warning(s)`.
- `python3 -m pytest tests/test_unified_deploy_surface.py crm/tests/test_orders_auth_and_idempotency.py -q` passed: `18 passed`.
- `tests/e2e/cross-service-smoke.spec.ts` passed: `5 passed`.

Do not run hostname-only E2E until external DNS provider has the two `A` records listed above. Use `SHOP_HOST_HEADER` and `CRM_HOST_HEADER` with `SHOP_BASE_URL=http://203.0.113.30` and `CRM_BASE_URL=http://203.0.113.30` while DNS is pending.

## Validation notes

- Script and doc verification: `bash deploy/verify.sh`
- Incremental rollout wrapper after base infra is healthy: `deploy/deploy.sh`
- Focused deploy/docs regression: `python3 -m pytest -q tests/test_unified_deploy_surface.py`
- CRM idempotency regression: `PYTHONPATH=crm pytest crm/tests/test_orders_auth_and_idempotency.py -q`
- Public DNS authority check: `dig +short NS example.test @1.1.1.1`
- Public hostname check: `dig +short A shop.example.test @1.1.1.1`
- Ingress health check: `kubectl -n ingress-nginx get deploy,svc,pods,endpoints -o wide`
- Workload health check: `kubectl get deploy -n octo-drone-shop octo-drone-shop -o wide` and `kubectl get deploy -n enterprise-crm enterprise-crm-portal -o wide`
