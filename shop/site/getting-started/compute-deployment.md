# Compute Deployment

Use this path for the production demo when you want private OCI Compute
instances plus one private ATP database, with public ingress through OCI
Load Balancer and WAF:

| Component | Placement | Purpose |
|---|---|---|
| Public Load Balancer | Public LB subnet | Host routing for `shop.<domain>` and `crm.<domain>`, or explicit `shop_hostname` / `crm_hostname` overrides |
| WAF | Attached to Load Balancer | Edge protection and WAF logs |
| Shop Compute | Private app subnet | Customer storefront and checkout |
| CRM Compute | Private app subnet | Operations console, catalog, order sync |
| ATP | Private DB subnet | Dedicated application database |

The source of truth is
[`deploy/compute/README.md`](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/compute/README.md).

[![Deploy Full Compute Stack to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/adibirzu/octo-apm-demo/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip)

If the Console test opens `https://cloud.oracle.com/stacks/create` and
returns `NotAuthorizedOrNotFound(404)`, reopen the button above and
confirm the browser URL contains `/resourcemanager/stacks/create` plus a
`zipUrl` query parameter. The shorter `/stacks/create` route is stale.
If the corrected URL still fails, verify that the active Console tenancy,
region, and compartment are the intended target and that the user can
create/import Resource Manager stacks and run Resource Manager jobs.

## What Is Configured

- VCN, public LB subnet, private app subnet, private DB subnet,
  Internet Gateway, NAT Gateway, Service Gateway, route tables,
  security lists, and NSGs when `create_network=true`.
- Optional existing VCN selection with existing public LB subnet,
  private app subnet, and optional private DB subnet.
- Private Shop and CRM Compute instances with no public IPs.
- Public OCI Load Balancer with host routing to the private instances on
  port `8080`.
- OCI WAF policy and WAF attachment in front of the Load Balancer.
- Dedicated ATP private endpoint with wallet output and variable ECPU
  and storage sizing. DB ingress is limited to the
  app NSG, plus optional DB Management/Operations Insights private
  endpoint NSG when those endpoints are enabled.
- Oracle Cloud Agent plugins for Compute monitoring, Custom Logs
  Monitoring, Run Command, and Management Agent.
- OCI APM Domain and OpenTelemetry app instrumentation.
- OCI Logging log group and custom/service logs for app SDK logs,
  security, chaos audit, OS logs, cloud-init logs, Podman/Docker stdout,
  and WAF events.
- Optional Service Connector Hub pipelines into Log Analytics.
- Stack Monitoring Standard license auto-assignment and HOST
  auto-promote, plus automatic deployment of the `Stack Monitoring`
  Management Agent plugin to both hosts. Explicit host and ATP
  monitored-resource registration are optional because some tenancies
  require additional monitored-resource entitlement.
- Instance-principal policies for OCIR repository reads, APM ingest,
  Logging ingest, Monitoring metrics, Management Agent, and APM agent
  installer reads.

The Python/FastAPI apps use OpenTelemetry as the APM application agent.
The deployment sets `OTEL_SERVICE_NAME`, `SERVICE_INSTANCE_ID`,
`APP_RUNTIME=compute`, `OCI_APM_ENDPOINT`, and
`OCI_APM_PRIVATE_DATAKEY`, so APM shows service topology, HTTP spans,
SQLAlchemy spans, process metrics, and custom business spans. Logs carry
`oracleApmTraceId` for trace-to-log pivots in Logging and Log Analytics.

## Validate Before Profile Selection

These commands do not call OCI:

```bash
./deploy/compute/validate.sh
./deploy/verify.sh
```

They validate the shell scripts, help surfaces, Compose config, nginx
template rendering for optional host-nginx mode, cloud-init YAML,
Terraform syntax, Resource Manager package Terraform, Helm, root
Terraform validation, docs, and Python tests.

Before applying in a real tenancy, check service limits with the same AD,
shape, ATP, and LB settings:

```bash
OCI_PROFILE=<OCI_PROFILE> \
COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
SHOP_AVAILABILITY_DOMAIN="YLXT:EU-FRANKFURT-1-AD-2" \
CRM_AVAILABILITY_DOMAIN="YLXT:EU-FRANKFURT-1-AD-1" \
INSTANCE_SHAPE=VM.Standard.E5.Flex \
INSTANCE_OCPUS=2 \
INSTANCE_MEMORY_GBS=16 \
ATP_ECPU_COUNT=2 \
LB_MAX_BANDWIDTH_MBPS=100 \
./deploy/compute/check-oci-limits.sh
```

The limits script also reads matching `TF_VAR_*` names, so deployment
automation can stay variable-driven across tenancies.

For the `<OCI_PROFILE>` profile, the May 6, 2026 read-only gate is recorded in
the private demo deployment notes. Those notes also document the required state
isolation because the local
`deploy/compute/terraform` directory contains state and auto-var files
from the earlier `<REFERENCE_PROFILE>` deployment.

## Deployment Sequence

1. Build and push the Shop and CRM images.
2. Build the Resource Manager package with
   `./deploy/compute/stack-package.sh` or use the button above. The
   upstream release asset is already published under
   `compute-resource-manager-stack-20260504/octo-compute-stack.zip`.
   Validate the URL with `curl -I -L` if Console import fails; the asset
   must return HTTP 200 after redirects.
3. In the stack form, either create a new network or select an existing
   VCN with a public LB subnet and private app subnet.
4. Enable HTTPS only when you can provide the Load Balancer certificate
   PEM and private key. In Resource Manager, set
   `enable_lb_https=true` and paste the certificate/key variables. For
   local Terraform, run `deploy/compute/configure-lb-certificate.sh`.
   Otherwise keep HTTP enabled for first smoke tests.
5. Enable Log Analytics only after the namespace is onboarded, then
   provide the namespace or an existing LA log group OCID.
6. For local Terraform, fill `deploy/compute/terraform/terraform.tfvars`.
7. Set `oci_profile` in `terraform.tfvars` when you are ready to target
   the real tenancy.
8. Run stack plan; review that it creates exactly the expected private
   network, two instances, public LB/WAF, ATP, APM, Logging, Stack
   Monitoring, optional Log Analytics pipelines, and agent
   configurations.
9. Run apply.
10. Render `runtime.shop.env` and `runtime.crm.env` using
    `deploy/compute/render-runtime-env.sh`.
11. Decode the ATP wallet output and copy the wallet plus runtime env to
    both private instances through OCI Bastion, an existing private
    network path, or Oracle Cloud Agent Run Command.
12. Run `/opt/octo/deploy/compute/install.sh --check`, then
    `/opt/octo/deploy/compute/install.sh` on both instances. Podman is
    the default runtime; Docker Compose remains available with
    `CONTAINER_RUNTIME=docker`.
13. Confirm `systemctl status octo-compute.service --no-pager` is
    active on each private host.
14. For later image promotions or host script reconciliation, use
    `deploy/compute/deploy-apps.sh` with OCI Run Command instead of
    replacing the stack or opening SSH.
15. Point the resolved Shop and CRM hostnames at the Load Balancer
    public IP. The defaults are `shop.<domain>` and `crm.<domain>`;
    use `shop_hostname` and `crm_hostname` when DNS is managed in a
    separate tenancy or uses nonstandard labels.
16. Run `./deploy/compute/verify-deployment.sh --profile <profile>
    --plan` to verify Terraform drift, DNS, `/ready`, LB health, WAF,
    APM, ATP, DB Management, Operations Insights, Log Analytics
    connectors, Management Agents, and Stack Monitoring. For Resource
    Manager deployments, copy the stack outputs to a JSON file and use
    `--outputs-json outputs.json` when local Terraform state is not
    available.
17. Confirm APM traces before starting E2E tests. Add `--require-https`
    to the verifier after the Load Balancer certificate is attached, and
    use `--skip-dns` only for host-header testing before public DNS is
    delegated.

Cloud-init `user_data` is ignored after instance creation to avoid
accidental replacement of production-demo hosts when bootstrap scripts or
docs change. New stacks receive the latest packaged bootstrap files at
first boot; existing stacks should be reconciled through Run Command,
Bastion, or another private admin path when host scripts need updates.

## Host Prerequisites

The Compute bootstrap and `install.sh` install and validate the host
tooling needed for app delivery and Java sidecar tests:

```text
curl git rsync unzip tar gzip make podman java-21-openjdk-devel maven maven-openjdk21
```

`podman` runs the Python app containers and the Java app-server sidecar.
`java-21-openjdk-devel`, `maven`, and `maven-openjdk21` are installed on
the VM so `services/apm-java-demo` can run `mvn test` with Java 21 on the
target host before the updated image is built and restarted.

## Podman Runtime Check

The OCI Compute path defaults to Podman on Oracle Linux. `runtime.env`
is shell-safe because cloud-init, `install.sh`, and the systemd units
source it; container runtimes do not strip those shell quotes from
`--env-file` values. To avoid quoted secrets and URLs inside the app
container, `install.sh --check` renders `/opt/octo/container.env` from
the sourced values and both the Podman and Docker units use that
container-runtime env file.

On each host, these checks should pass before the Load Balancer backend
is expected to turn healthy:

```bash
sudo /opt/octo/deploy/compute/install.sh --check
sudo test -s /opt/octo/container.env
sudo grep -q "^OCI_APM_ENDPOINT=https://" /opt/octo/container.env
sudo systemctl cat octo-compute.service
```

If you edit `/opt/octo/runtime.env` after first boot, re-run
`install.sh --check` to regenerate `/opt/octo/container.env`, then
restart `octo-compute.service`.

For the assistant demo, set `OCI_GENAI_ENDPOINT` and
`OCI_GENAI_MODEL_ID` on the Shop runtime when OCI GenAI is available. Optional
Langfuse comparison uses `LANGFUSE_ENABLED`, `LANGFUSE_HOST`,
`LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY` or their `*_FILE` variants.
Keep `LLMETRY_CAPTURE_CONTENT=false` unless you are running a controlled
redacted-content demo; the default export uses hashes, token counts, guardrail
fields, trace IDs, and session IDs.

## App Promotion

Use `deploy/compute/deploy-apps.sh` to promote new Shop or CRM images on
the private instances through Oracle Cloud Agent Run Command. It is
dry-run by default:

```bash
terraform -chdir=deploy/compute/terraform output -json > /tmp/octo-compute-outputs.json

./deploy/compute/deploy-apps.sh \
  --outputs-json /tmp/octo-compute-outputs.json \
  --profile <oci-profile> \
  --role all \
  --image-tag <new-image-tag> \
  --app-image-pull-policy always
```

Add `--apply` after confirming the target Shop and CRM instance OCIDs.
For Resource Manager stacks, copy the stack outputs to JSON and pass
`--outputs-json`. For older stacks without `instance_ids`, pass
`--shop-instance-id`, `--crm-instance-id`, and `--compartment-id`.

The command payload only includes non-secret deployment values. It does
not transmit database passwords, CRM admin passwords, APM private data
keys, OCIR auth tokens, or cross-service secrets. On each host it runs
`/opt/octo/deploy/compute/install.sh --check`, applies the install,
restarts `octo-compute.service`, and checks local `/ready`.

## Current Reference Validation

Validated on May 5, 2026 with `OCI_PROFILE=<OCI_PROFILE>`:

- `shop.example.test` and `crm.example.test` return HTTP 200
  from `/ready`.
- Load Balancer backend sets for both services are `OK`.
- Load Balancer public IP is available from `terraform output load_balancer`.
- Private app IPs are available from `terraform output instance_ips`.
- Dedicated ATP private endpoint is available from `terraform output atp`.
- APM endpoint is available from `terraform output apm`.
- Shop and CRM were placed in separate availability domains for the reference
  capacity profile.
- Log Analytics is enabled with an OCTO LA log group and active Service
  Connector Hub routes for app, OS, container, and WAF logs.
- A Log Analytics query over the deployment compartment returned fresh
  records after the connectors were created.
- Stack Monitoring Standard license and HOST auto-promote configs are
  active. The Stack Monitoring Management Agent plugin is deployed and
  running on both hosts.
- `./deploy/compute/verify-deployment.sh --profile <OCI_PROFILE> --plan` passed
  with DNS, LB, WAF, APM, ATP, DB Management, Operations Insights, Log
  Analytics, Management Agent, and Stack Monitoring checks active. The
  only expected warnings are HTTPS not yet enabled and explicit ATP
  Stack Monitoring resource registration disabled.
- Direct host and ATP Stack Monitoring monitored-resource registration
  are disabled in the reference profile because OCI returns `Tenant is not permitted to
  perform this operation`; keep the explicit registration toggles off in
  tenancies with the same entitlement behavior.
- Terraform reports `No changes` after the final apply.

SSO is not configured for the Compute stack. The CRM backend uses local
auth with username `admin`; the password is the sensitive
`bootstrap_admin_password` value supplied to Terraform or Resource
Manager. The stack intentionally exposes only
`terraform output crm_admin_username`.

For local Terraform HTTPS certificate automation:

```bash
./deploy/compute/configure-lb-certificate.sh \
  --certificate /path/to/fullchain.pem \
  --private-key /path/to/privkey.pem \
  --ca-certificate /path/to/chain.pem \
  --profile <OCI_PROFILE> \
  --apply
```

If you cannot use Terraform for the certificate, add it manually in OCI
Load Balancer **Certificates**, then create/update the `443` listener to
use the uploaded certificate, the existing `host_routing` routing policy,
and the Shop backend set as default. Manual console changes will be
Terraform drift.

## Logging Contract

Application logs are sent through the OCI Logging SDK to `octo-app` and
include `oracleApmTraceId`. Host logs are collected by Oracle Cloud
Agent Custom Logs Monitoring into separate custom logs:

- OS/cloud-init/install: `/var/log/messages`, `/var/log/syslog`,
  `/var/log/cloud-init*.log`, `/var/log/octo/*.log`
- containers:
  `/var/lib/containers/storage/overlay-containers/*/userdata/ctr.log`
  and `/var/lib/docker/containers/*/*.log`
- WAF: OCI service log when `enable_waf_logging=true`

Before demo time, confirm fresh records in `octo-app`,
`octo-compute-os`, `octo-compute-app-stdout`, and the WAF service log.
Also confirm Log Analytics pipelines if enabled, and confirm Stack
Monitoring shows both Compute hosts under Standard monitoring. If ATP
registration is enabled and entitled in the target tenancy, confirm the
ATP monitored resource as well.
