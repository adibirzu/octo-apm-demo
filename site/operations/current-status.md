# Current Status

Snapshot date: **April 28, 2026** for the shared `DEFAULT` runtime.
Private Compute stack validation updated on **May 7, 2026**.

This page records the latest observed state of the shared `DEFAULT`
deployment surface tracked by this repo. It is a runtime snapshot, not a
guarantee that the shared environment will remain healthy without checking
the validation commands below.

May 4, 2026 update: the private two-instance Compute Resource Manager
stack has been applied in the `<OCI_PROFILE>` profile as a new deployment for
`shop.example.test` and `crm.example.test`. It is separate from
the shared `DEFAULT` OKE runtime described below.

May 6, 2026 update: the `<OCI_PROFILE>` profile was first reviewed for a new
private Compute install in compartment
`<COMPARTMENT_OCID>`
(`<COMPARTMENT_NAME>`). The preflight and clean no-apply plan passed without
creating resources. The exact limits, Terraform plan scope, APM/Log Analytics
collection review, and apply gate are kept in private operator notes that are
excluded from the public GitHub Pages build.

Later on May 6, an isolated `<OCI_PROFILE>` apply created the private Compute
stack resources and was converged after disabling the optional surfaces
blocked by Service Connector Hub quota, tenancy-level dynamic-group
authorization, and Stack Monitoring authorization/tagging issues. The
runtime is healthy through the Load Balancer IP with `Host` headers:
`shop.example.test` and `admin.example.test` both return
`ready=true`, ATP connected, APM configured, and RUM configured. Public DNS
remains external in the `<REFERENCE_PROFILE>` tenancy; point both hostnames to
`203.0.113.10` before hostname-only browser/E2E tests. OCI Logging and
Log Analytics resources exist, but Log Analytics connectors, unified-agent
log collection, and Compute instance-principal IAM are disabled in
`<OCI_PROFILE>` until quota and authorization are available. A live Service
Connector Hub check on May 6 reported `service-connector-count`
`available=0`; none of the existing shared connectors route the
`<DEPLOYMENT_PREFIX>` OCI Logging log group.

Later on May 6, the app code was updated for the private demo dashboard and
checkout path. The dashboard topology profile now shows only
`octoatp_low`, `shop.example.test`, and `admin.example.test` plus
telemetry status. The shop checkout flow now sends a
`checkout_idempotency_key`, disables duplicate submits in the browser, and
deduplicates backend retries through a unique `orders` table key.

Later on May 6, the repo added a Drone Shop Java app-server sidecar path
for `<OCI_PROFILE>`. Checkout can call `octo-java-app-server` on
`127.0.0.1:18080` for simulated payment authorization, so OCI APM can
link Python spans, Java app-server/JVM metrics, structured payment logs,
and ATP order records. The CRM simulation page now proxies Java slow/GC/
CPU/error scenarios plus payment decline/timeout demos through Drone
Shop. RUM was extended with sanitized custom browser actions and
same-origin trace propagation.

Later on May 6, the private demo admin simulation page gained a Demo
Storyboard and Attack Lab. The storyboard opens the shop path, adds
drones, authorizes a dummy card payment through the simulator, and
creates a support ticket. The attack lab emits MITRE-mapped stage spans,
source/destination/server-hop fields, Java external and SQL error spans,
OSQuery-like detection logs, and Log Analytics dashboard/search assets.
The new `skills/private-demo-observability-triage` skill captures the
repeatable smoke, trace, OSQuery, and dashboard triage workflow for this
deployment.

Cloud Guard Advanced Security is documented for the private demo compartment by
creating target `<DEPLOYMENT_PREFIX>-instance-security`
(`<CLOUD_GUARD_TARGET_OCID>`)
with the existing Instance Security detector recipe. Saved OSQueries were
created for attack-lab listeners, living-off-the-land process candidates,
suspicious shell history, systemd persistence, recent processes,
listening ports, unexpected users, startup items, crontab, sudoers, and
kernel modules. Ad-hoc OSQuery execution was run against the shop and CRM
instances; three runs completed and two failed in-region. Completed
results were normalized into OCI Logging (`<DEPLOYMENT_PREFIX>-os`) with
`ATTACK_ID=attack-851e80f8751b`, producing 246 OSQuery log entries. Those
records are in OCI Logging now; they will not appear in Log Analytics
until Service Connector Hub quota is available or an approved shared
connector is updated.

Two APM Availability Monitoring REST monitors were created and enabled
for the private demo hostnames using DNS override to the preserved LB IP
`203.0.113.10`:

- `<DEPLOYMENT_PREFIX>-drones-ready-global` ->
  `https://shop.example.test/ready`
- `<DEPLOYMENT_PREFIX>-admin-ready-global` ->
  `https://admin.example.test/ready`

Both run every five minutes from Phoenix, Ashburn, Frankfurt, London,
Tokyo, and Sydney.

Later on May 6, the APM-to-log correlation gap was traced to a live app
image still using an obsolete OCI Logging SDK payload. Both Shop and CRM
containers logged:

```text
OCI Logging put_logs failed: Unrecognized keyword arguments: defaultloglevel
```

The repo now removes the invalid `LogEntryBatch(defaultloglevel=...)`
argument, sends timezone-aware `LogEntry.time` values, includes
`timestamp`, `level`, `message`, `oracleApmTraceId`, and
`oracleApmSpanId` in `LogEntry.data`, and emits compact `app.log` span
events on the active APM span. The live hosts need the rebuilt Shop and
CRM images restarted before OCI Logging and Log Analytics will show new
SDK-pushed app rows. If the APM span details page still shows `Logs: 0`,
check the span Events view for `app.log` and pivot to Log Analytics by
`oracleApmTraceId`; the durable log feed is OCI Logging -> Service
Connector Hub -> Log Analytics.

On May 7, another APM drilldown gap was identified from the span details
panel showing `Logs: 0` on the auto-instrumented FastAPI server span even
though JSON logs had `oracleApmTraceId`. The issue is not the trace ID field:
it is where the compact `app.log` span event is attached. The apps now bind
the request/server span at middleware entry and mirror each `push_log()` event
to both the current child span and the request server span. This keeps the
APM span details view useful while preserving the durable log path through
OCI Logging and Log Analytics.

Later on May 7, the rebuilt Shop and CRM images were restarted in the private
Compute runtime. A fresh payment-simulation request verified both paths:
OCI Logging returned correlated rows for the trace via `oracleApmTraceId`, and
APM Trace Explorer returned `app.log` entries on the root FastAPI SERVER span
as well as the relevant child spans. The CRM `audit_logs` table was also
checked in the live Oracle database and includes `user_agent`, so product and
store update audit events should no longer fail with `ORA-00904`.

Later on May 7, the checkout payment drilldown was extended and verified with
a fresh placeholder order, gateway request, and trace. The Shop now exposes
`/api/observability/payment-gateway/events` for `order_id`, `trace_id`, and
`gateway_request_id` filters, and the CRM order view surfaces payment status
plus the gateway correlation key. The verified event sequence includes
gateway receipt, card/wallet data receipt, tokenization, antifraud review,
processor routing, authorization decision, order payment update, and CRM sync;
all pivots use synthetic IDs and tokenized metadata.

The empty APM **App Servers** details page was traced to Java APM metric
dimensions reporting `Appserver=false` for
`ServiceName=octo-java-app-server` even though `HeapUsed` metrics exist
in the `oracle_apm_monitoring` namespace. The Java sidecar entrypoint now
sets `com.oracle.apm.agent.resource.appserver=true`,
`com.oracle.apm.agent.resource.appserver.name=${APM_SERVICE_NAME}`, and
`com.oracle.apm.agent.metric.collect.wait.for.appserver=false`. Rebuild
and restart the Java sidecar, then verify the App Server picker and JVM
metrics again before changing the APM domain or LB.

The Resource Manager Compute package validates locally and now includes the
Java APM sidecar, workflow gateway, and synthetic-user timer bootstrap assets.
The placeholder GitHub release ZIP URLs used by the old deploy buttons return
HTTP 404, so OCI Resource Manager cannot import them. The reported Console
error also used `https://cloud.oracle.com/stacks/create`, which is the wrong
route and can produce `NotAuthorizedOrNotFound(404)` before stack import. Use
manual zip upload for this private branch, or publish a real private release
asset and open `https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=...`.
If a valid asset still fails, verify Console tenancy/region context and grant
Resource Manager create/import/job permissions for this compartment.

## Private Compute reference deployment

Validated on May 5, 2026:

- Public endpoints:
  - `http://shop.example.test/ready` -> HTTP 200, ATP connected,
    APM/RUM configured.
  - `http://crm.example.test/ready` -> HTTP 200, ATP connected,
    APM/RUM/logging configured.
- Load Balancer public IP is available from `terraform output load_balancer`.
- Private app IPs are available from `terraform output instance_ips`.
- Dedicated ATP private endpoint is available from `terraform output atp`.
- APM endpoint is available from `terraform output apm`.
- Shop and CRM were placed in separate availability domains for the reference
  capacity profile.
- Both LB backend sets report `OK`.
- The reference limits check passed for split AD compute capacity, ATP ECPU,
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
- Log Analytics is onboarded in the external DNS tenancy. The reference stack now owns
  an OCTO LA log group plus active Service Connector Hub routes for app,
  OS, container, and WAF logs.
- `deploy/compute/verify-deployment.sh --profile <OCI_PROFILE> --plan` passes and
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
monitored-resource creation remain disabled in the reference tenancy because OCI returns
`Tenant is not permitted to perform this operation`; Standard license
auto-assignment, HOST auto-promote, and the host Stack Monitoring
Management Agent plugin remain enabled.

SSO is not configured for this Compute stack. CRM local auth uses
username `admin`; the password is the sensitive
`bootstrap_admin_password` supplied in the deployment variables. Login
to `POST /api/auth/login` with the reference value was validated with HTTP
200.

Focused validation:

- `./deploy/compute/validate.sh` passed.
- `./deploy/compute/verify-deployment.sh --profile <OCI_PROFILE> --plan` passed
  with expected warnings for HTTPS not yet enabled and explicit ATP Stack
  Monitoring resource registration disabled.
- `terraform -chdir=deploy/compute/terraform validate -no-color` passed.
- `python3 -m pytest -q tests/test_unified_deploy_surface.py` passed:
  `20 passed`.

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
