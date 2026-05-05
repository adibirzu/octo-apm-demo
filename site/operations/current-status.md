# Current Status

Snapshot date: **April 28, 2026** for the shared `DEFAULT` runtime.
Private Compute stack validation updated on **May 5, 2026**.

This page records the latest observed state of the shared `DEFAULT`
deployment surface tracked by this repo. It is a runtime snapshot, not a
guarantee that the shared environment will remain healthy without checking
the validation commands below.

May 4, 2026 update: the private two-instance Compute Resource Manager
stack has been applied in the `cap` profile as a new deployment for
`shop.1.octodemo.cloud` and `crm.1.octodemo.cloud`. It is separate from
the shared `DEFAULT` OKE runtime described below.

## Private Compute cap deployment

Validated on May 5, 2026:

- Public endpoints:
  - `http://shop.1.octodemo.cloud/ready` -> HTTP 200, ATP connected,
    APM/RUM configured.
  - `http://crm.1.octodemo.cloud/ready` -> HTTP 200, ATP connected,
    APM/RUM/logging configured.
- Load Balancer public IP is available from `terraform output load_balancer`.
- Private app IPs are available from `terraform output instance_ips`.
- Dedicated ATP private endpoint is available from `terraform output atp`.
- APM endpoint is available from `terraform output apm`.
- Shop and CRM were placed in separate availability domains for the cap
  capacity profile.
- Both LB backend sets report `OK`.
- The cap limits check passed for split AD compute capacity, ATP ECPU,
  LB count/bandwidth, and VCN count.
- Terraform reports `No changes` after the final DB egress tightening
  apply.
- APM domain `octo-shop1-apm` is `ACTIVE`.
- WAF attachment `octo-shop1-lb-waf` is `ACTIVE`.
- Management Agents for both private Compute hosts are `ACTIVE`.
- Stack Monitoring Management Agent plugin `appmgmt` is deployed and
  `RUNNING` on both private Compute hosts.
- OCI Logging agent configurations `octo-shop1-os-logs` and
  `octo-shop1-container-stdout` are enabled.
- Log Analytics is onboarded in the cap tenancy. The cap stack now owns
  an OCTO LA log group plus active Service Connector Hub routes for app,
  OS, container, and WAF logs.
- `deploy/compute/verify-deployment.sh --profile cap --plan` passes and
  checks Terraform drift, DNS, public `/ready` endpoints, Load Balancer
  lifecycle/backend health, WAF, APM, ATP, DB Management, Operations
  Insights, Log Analytics connectors, Management Agents, and Stack
  Monitoring HOST auto-promote state.
- A Log Analytics query over the last 30 minutes returned 212 records in
  `OCI Unified Schema Logs` after the connectors were created.
- ATP reports `database-management-status=ENABLED` and
  `operations-insights-status=ENABLED`.

The stack creates a public LB/WAF and keeps Shop, CRM, and ATP in
private subnets. DB ingress is limited to the app NSG plus the optional
DB Management/Operations Insights private endpoint NSG, and DB-tier
egress is limited to the regional OCI Services Network through the
Service Gateway.

Temporary Bastion debug access was removed after validation: the app NSG
SSH rule was deleted, both Bastion sessions are `DELETED`, and the
Bastion resource is `DELETED`. Direct Stack Monitoring host and ATP
monitored-resource creation remain disabled in cap because OCI returns
`Tenant is not permitted to perform this operation`; Standard license
auto-assignment, HOST auto-promote, and the host Stack Monitoring
Management Agent plugin remain enabled.

SSO is not configured for this Compute stack. CRM local auth uses
username `admin`; the password is the sensitive
`bootstrap_admin_password` supplied in the deployment variables. Login
to `POST /api/auth/login` with the cap value was validated with HTTP
200.

Focused validation:

- `./deploy/compute/validate.sh` passed.
- `./deploy/compute/verify-deployment.sh --profile cap --plan` passed
  with expected warnings for HTTPS not yet enabled and explicit ATP Stack
  Monitoring resource registration disabled.
- `terraform -chdir=deploy/compute/terraform validate -no-color` passed.
- `python3 -m pytest -q tests/test_unified_deploy_surface.py` passed:
  `20 passed`.

## Scope confirmed

- Local `~/.oci/config` resolves the `DEFAULT` profile in `eu-frankfurt-1`.
- The cached compartment is `Adrian_Birzu` via `deploy/.last-tenancy.env`.
- Current kube context for this deployment is `octo-Adrian_Birzu`.
- Bootstrap reused the existing OKE control plane `cluster1`.
- Bootstrap used the OCIR namespace authorized on the remote build host
  for image build and push.

## Public DNS status

- `cyber-sec.ro` is currently delegated to Cloudflare nameservers: `alfred.ns.cloudflare.com` and `rayne.ns.cloudflare.com`.
- The OCI DNS zone is not authoritative for public traffic, so bootstrap switches to `DNS_MODE=manual`.
- Public resolvers such as `1.1.1.1` currently return **no `A` record** for `shop.cyber-sec.ro` or `crm.cyber-sec.ro`.
- Add or update these records in Cloudflare before browser or Playwright tests can use the hostnames directly:

```text
shop.cyber-sec.ro.   A   144.24.173.224   TTL 60
crm.cyber-sec.ro.    A   144.24.173.224   TTL 60
```

Until Cloudflare is updated, use the ingress IP with `Host` headers for smoke and E2E checks.

## Runtime status

- Shared ingress `LoadBalancer` advertises `144.24.173.224`.
- `ingress-nginx/nginx-ingress-ingress-nginx-controller` is `2/2` available.
- The nginx admission service has live endpoints, so ingress creation succeeds.
- The managed worker instances backing ingress were found `STOPPED` again after the first successful run; they were restarted and Kubernetes nodes `10.0.10.20` and `10.0.10.36` returned to `Ready`.
- `deploy/bootstrap.sh` now checks existing nginx ingress readiness, starts stopped OCI worker instances referenced by NotReady real nodes, waits for node readiness, and refuses to continue if the ingress service still has no endpoints.

## Workload status

- `octo-drone-shop` is `2/2` ready in namespace `octo-drone-shop`.
- `enterprise-crm-portal` is `2/2` ready in namespace `enterprise-crm`.
- Current deployed images are in OCIR with the timestamped Shop and CRM
  tags recorded in the deployment logs.
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

Do not run hostname-only E2E until Cloudflare has the two `A` records listed above. Use `SHOP_HOST_HEADER` and `CRM_HOST_HEADER` with `SHOP_BASE_URL=http://144.24.173.224` and `CRM_BASE_URL=http://144.24.173.224` while DNS is pending.

## Validation notes

- Script and doc verification: `bash deploy/verify.sh`
- Incremental rollout wrapper after base infra is healthy: `deploy/deploy.sh`
- Focused deploy/docs regression: `python3 -m pytest -q tests/test_unified_deploy_surface.py`
- CRM idempotency regression: `PYTHONPATH=crm pytest crm/tests/test_orders_auth_and_idempotency.py -q`
- Public DNS authority check: `dig +short NS cyber-sec.ro @1.1.1.1`
- Public hostname check: `dig +short A shop.cyber-sec.ro @1.1.1.1`
- Ingress health check: `kubectl -n ingress-nginx get deploy,svc,pods,endpoints -o wide`
- Workload health check: `kubectl get deploy -n octo-drone-shop octo-drone-shop -o wide` and `kubectl get deploy -n enterprise-crm enterprise-crm-portal -o wide`
