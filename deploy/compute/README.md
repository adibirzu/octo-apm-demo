# Private OCI Compute deployment

Production-demo path for running OCTO without Kubernetes:

- one private OCI Compute instance for **OCTO Drone Shop**
- one private OCI Compute instance for **Enterprise CRM Portal**
- one dedicated private Oracle ATP database
- one public OCI Load Balancer with host routing for `shop.<domain>` and
  `crm.<domain>`, or explicit `shop_hostname` / `crm_hostname` values
- OCI Web Application Firewall attached to the Load Balancer
- OCI APM Domain plus OpenTelemetry app instrumentation
- OCI Logging custom logs for app SDK logs, container stdout, OS,
  cloud-init, and install logs, with collection enabled when the required
  IAM and agent configuration toggles are enabled
- optional Service Connector Hub pipelines into OCI Log Analytics
- Stack Monitoring Standard onboarding for hosts, with automatic
  Management Agent plugin deployment and optional explicit
  monitored-resource registration when the tenancy is entitled

The old `deploy/vm/` path remains available for a single host. Use this
path when the demo needs production-shaped network isolation and
host-level telemetry.

[Deploy Full Private Compute Stack to Oracle Cloud](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/example-org/octo-apm-demo/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip)

Private branch import note: build `deploy/compute/build/octo-compute-stack.zip`
locally and upload it through **OCI Console -> Developer Services -> Resource
Manager -> Stacks -> Create Stack -> My Configuration**. The placeholder GitHub
release URL previously used by the deploy button returns HTTP 404, so the
button must stay disabled until a real private release asset exists.

If a Console test opens `https://cloud.oracle.com/stacks/create` and
returns `NotAuthorizedOrNotFound(404)`, use the Resource Manager route instead:
`/resourcemanager/stacks/create?zipUrl=...`. If that corrected route still
fails, check that the zip URL returns HTTP 200, then check the active tenancy,
region, and compartment in the Console and confirm the user has Resource
Manager stack create/import and job permissions, not only stack list/read
access.

## What The Stack Creates

`deploy/compute/terraform` creates:

1. VCN, public Load Balancer subnet, private app subnet, private DB
   subnet, Internet Gateway, NAT Gateway, Service Gateway, route tables,
   security lists, and NSGs when `create_network=true`.
2. Two private Compute instances tagged `project=octo-apm-demo` and
   `surface=compute`; no public IPs are assigned.
3. Public OCI Load Balancer with HTTP host routing and optional HTTPS
   listener.
4. OCI WAF policy and WAF attachment in front of the Load Balancer.
5. Dedicated ATP with a private endpoint in the DB subnet, variable ECPU
   and storage sizing, and generated wallet output.
6. Database Management and Operations Insights enablement plus optional
   private endpoints.
7. OCI Logging log group plus:
   - `octo-app` for app SDK logs.
   - `octo-chaos-audit` and `octo-security`.
   - `octo-compute-os` for OS/cloud-init/install logs.
   - `octo-compute-app-stdout` for Podman/Docker stdout/stderr.
   - `octo-compute-waf` for WAF service logs when WAF logging is enabled.
8. Optional Log Analytics log group and Service Connector Hub pipelines
   for app, OS, container, and WAF logs.
9. OCI APM Domain and data keys when `create_apm_domain=true`.
10. Optional dynamic group and policy for instance-principal app access
    to Logging, Monitoring, OCIR repository reads, APM agent installers,
    and Management Agent.
11. Stack Monitoring Standard license auto-assignment and HOST
    auto-promote, plus automatic deployment of the Stack Monitoring
    Management Agent plugin to both hosts. Explicit host and ATP
    monitored-resource registration are optional because some tenancies
    return a monitored-resource entitlement error.
12. Oracle Cloud Agent plugin configuration for Compute monitoring,
    Custom Logs Monitoring, Run Command, and Management Agent.

With `enable_first_boot_deploy=false` Terraform does **not** put app
passwords, APM private data keys, OCIR auth tokens, or cross-service
secrets in instance metadata; render and copy `/opt/octo/runtime.env`
after apply. With `enable_first_boot_deploy=true`, Resource Manager must
carry those values as sensitive variables and write a shell-quoted
`/opt/octo/runtime.env` during cloud-init so the stack can complete
unattended. Rotate demo secrets after the run if the stack state is
shared.

## Network Contract

Default new network:

| Tier | CIDR | Public IPs | Purpose |
|---|---:|---:|---|
| Public LB subnet | `10.42.10.0/24` | yes | OCI Load Balancer only |
| Private app subnet | `10.42.20.0/24` | no | Shop and CRM Compute instances |
| Private DB subnet | `10.42.30.0/24` | no | ATP private endpoint and optional DBMan/OPSI endpoints |

Ingress is `Internet -> WAF -> OCI Load Balancer -> private app
instances:8080`. The app NSG accepts port `8080` only from the LB NSG
and app-to-app traffic from the app NSG. ATP accepts SQL*Net/TCPS only
from the app NSG, plus the optional DB Management/Operations Insights
private endpoint NSG when those endpoints are enabled.

The app subnet routes `0.0.0.0/0` through NAT for package install,
GitHub clone, and image pulls, and routes Oracle Services Network
traffic through the Service Gateway. The DB subnet uses the Service
Gateway route for private OCI service access.

The DB subnet and DB NSG do not allow broad DB egress. When the stack
creates the network, DB-tier egress is limited to the regional OCI
Services Network through the Service Gateway for DB Management,
Operations Insights, Stack Monitoring, agents, and service APIs.

When `create_network=false`, select:

- existing VCN
- existing public Load Balancer subnet
- existing private app subnet
- existing private DB subnet, or leave it empty to use the app subnet

Your existing VCN must already have equivalent public LB, private app,
NAT, Service Gateway, and DB private routing.

## Offline Validation

Run this before any OCI profile is supplied:

```bash
./deploy/compute/validate.sh
./deploy/verify.sh
```

The compute validator performs shell syntax checks, `--help` checks,
Docker Compose config rendering when Docker is present, nginx template
rendering for the optional host-nginx mode, cloud-init YAML parsing, and
`terraform init -backend=false` plus `terraform validate` for both the
source stack and generated Resource Manager package. It does not call
OCI.

Before applying in a real tenancy, run the read-only limits check with
the same shape, AD, ATP, and LB settings you plan to use:

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

The script also reads matching `TF_VAR_*` names, so it can be wired into
automation without hardcoding profile-specific values.

## Resource Manager Stack

Build and validate the uploadable stack locally:

```bash
./deploy/compute/stack-package.sh
# -> deploy/compute/build/octo-compute-stack.zip
```

Upload that zip in **OCI Console -> Developer Services -> Resource
Manager -> Stacks -> Create Stack**. The schema lets you create a new network
or attach to an existing VCN/subnet layout.

For import failures, validate the asset first:

```bash
curl -I -L https://github.com/example-org/octo-apm-demo/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip
```

The placeholder URL above currently returns HTTP 404. A real deploy-button URL
must return HTTP 200 after redirects. A valid asset plus a
`NotAuthorizedOrNotFound(404)` response normally points to a stale Console
route, wrong tenancy/region context, or missing Resource Manager create/import
permissions.

## Local Terraform Plan

When you are ready to deploy outside Resource Manager, copy the example
vars and fill them:

```bash
cd deploy/compute/terraform
cp terraform.tfvars.example terraform.tfvars
${EDITOR:-vi} terraform.tfvars
terraform init
terraform plan
```

Only apply after the plan shows the expected private network, two
instances, public LB/WAF, one private ATP, one APM domain, one logging
group, Stack Monitoring resources, and unified-agent configurations:

```bash
terraform apply
```

Set `oci_profile` in `terraform.tfvars` when you are ready to target a
real tenancy. Until then, `deploy/compute/validate.sh` is the safe gate
because it never authenticates to OCI.

Cloud-init `user_data` is ignored after instance creation to avoid
accidental replacement of production-demo hosts when bootstrap scripts or
docs change. For an existing stack, reconcile `/opt/octo/deploy/compute`
with Run Command, Bastion, or your private admin path if you need a host
script update; new stacks receive the latest packaged bootstrap files at
first boot.

## Load Balancer HTTPS Certificate

Terraform can add the certificate to the OCI Load Balancer automatically
when `enable_lb_https=true` and the certificate variables are provided.
For local Terraform, use the helper so private key material is loaded
only into the current process environment:

```bash
./deploy/compute/configure-lb-certificate.sh \
  --certificate /path/to/fullchain.pem \
  --private-key /path/to/privkey.pem \
  --ca-certificate /path/to/chain.pem \
  --profile <OCI_PROFILE> \
  --apply
```

Add `--disable-http` only after HTTPS has been validated. If the private
key is encrypted, pass `--passphrase-file /path/to/passphrase.txt` or set
`LB_CERTIFICATE_PASSPHRASE` for the command. The helper runs
`terraform plan` by default and applies only when `--apply` is supplied.

For Resource Manager, set:

- `enable_lb_https=true`
- `lb_certificate_public_certificate=<leaf or full-chain PEM>`
- `lb_certificate_private_key=<private key PEM>`
- `lb_certificate_ca_certificate=<optional CA chain PEM>`
- `lb_certificate_passphrase=<optional key passphrase>`

Terraform state and Resource Manager job state will contain the private
key because OCI Load Balancer certificates are managed through the Load
Balancer API. Keep state access restricted and rotate demo certificates
when a shared state file has been exposed.

If another user must add the certificate manually instead of using
Terraform, use **Networking -> Load Balancers -> Certificates -> Add
certificate**, then create or update a listener on port `443` with the
certificate, the existing `host_routing` routing policy, and the Shop
backend set as default. Also make sure `enable_lb_https=true` or an
equivalent LB subnet/NSG/security-list rule allows public TCP `443`.
Manual console changes will show as Terraform drift.

## Host Prerequisites

The Compute bootstrap and `install.sh` install and validate these host
tools before app startup:

```text
curl git rsync unzip tar gzip make podman java-21-openjdk-devel maven maven-openjdk21
```

`podman` runs the Python app containers and the Java app-server sidecar.
`java-21-openjdk-devel`, `maven`, and `maven-openjdk21` are installed on
the VM so the sidecar can be tested directly on the target host with Java
21 before images are rebuilt or services are restarted. `rsync`, archive
tools, and `make` support controlled repository promotion and operator
repair workflows.

## Runtime Env, Wallet, And Images

After apply, render role-specific env files from Terraform outputs plus
operator-held secrets:

```bash
export OCIR_REGION=<region>
export OCIR_TENANCY=<namespace>
export IMAGE_TAG=<image-tag>
export OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx
export INTERNAL_SERVICE_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export AUTH_TOKEN_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export BOOTSTRAP_ADMIN_PASSWORD='<set outside shell history in production>'
export ORACLE_PASSWORD='<ATP ADMIN password>'
export ORACLE_WALLET_PASSWORD='<ATP wallet password>'
export OCI_APM_PRIVATE_DATAKEY='<terraform output apm_private_datakey>'
export OCI_APM_PUBLIC_DATAKEY='<terraform output apm_public_datakey>'
export OCI_GENAI_ENDPOINT='<optional OCI GenAI endpoint>'
export OCI_GENAI_MODEL_ID='<optional OCI GenAI model id>'
export LLMETRY_CAPTURE_CONTENT=false
export LANGFUSE_ENABLED=false
export LANGFUSE_HOST='https://langfuse.example.test'
export LANGFUSE_PUBLIC_KEY='<optional Langfuse project public key>'
export LANGFUSE_SECRET_KEY='<optional Langfuse project secret key>'
export OCIR_USERNAME='<optional OCIR username>'
export OCIR_AUTH_TOKEN='<optional OCIR auth token>'

ROLE=shop ./deploy/compute/render-runtime-env.sh > runtime.shop.env
ROLE=crm  ./deploy/compute/render-runtime-env.sh > runtime.crm.env
```

## CRM Local Admin Login

SSO is disabled in the Compute stack unless all IDCS variables are
provided, so CRM uses local auth. The bootstrap admin username is
`admin`; the password is the sensitive `bootstrap_admin_password` value
you supplied to Terraform or Resource Manager. The stack exposes
`terraform output crm_admin_username`; it intentionally does not print
the password.

`CONTAINER_RUNTIME=podman` is the default. Set
`CONTAINER_RUNTIME=docker` in the rendered env only if you explicitly
want Docker Compose on the instances.

`runtime.env` is shell-safe because `install.sh`, cloud-init, and the
systemd units source it. During every `install.sh --check` or
`install.sh` run, the script also renders `/opt/octo/container.env` in
plain container env-file format and the Podman/Docker units pass that
file to the container runtime. Re-run `install.sh --check` after editing
`runtime.env` so the container env file is regenerated before a service
restart.

For the assistant demo, the Shop runtime reads `OCI_GENAI_ENDPOINT`,
`OCI_GENAI_MODEL_ID`, `LLMETRY_*`, and `LANGFUSE_*` from the same
container env file. Leave Langfuse disabled until a project has been
created and project ingestion keys are available. Raw prompt/response
capture stays off by default; the app exports hashes, token counts,
guardrail results, trace IDs, and session IDs.

Decode the wallet once:

```bash
terraform -chdir=deploy/compute/terraform output -raw atp_wallet_content_base64 | base64 -d > wallet.zip
unzip -o wallet.zip -d wallet
```

The instances are private. Use OCI Bastion, an existing private network
path, or Oracle Cloud Agent Run Command to copy:

- `runtime.shop.env` to the Shop instance as `/opt/octo/runtime.env`
- `runtime.crm.env` to the CRM instance as `/opt/octo/runtime.env`
- wallet contents to `/opt/octo/wallet` on both instances

On each host:

```bash
sudo install -m 0600 /tmp/runtime.env /opt/octo/runtime.env
sudo rm -rf /opt/octo/wallet
sudo install -d -m 0755 /opt/octo/wallet
sudo cp -a /tmp/wallet/. /opt/octo/wallet/
sudo /opt/octo/deploy/compute/install.sh --check
sudo /opt/octo/deploy/compute/install.sh
sudo systemctl status octo-compute.service --no-pager
```

TLS is terminated at the OCI Load Balancer when `enable_lb_https=true`.
Do not install certificates on the private instances unless you set
`ENABLE_HOST_NGINX=true` for a custom host-nginx fallback.

## App Promotion With Run Command

After the initial `runtime.env` and ATP wallet are on each private
instance, promote new app images or reconcile the host scripts without
opening SSH. `deploy/compute/deploy-apps.sh` uses Oracle Cloud Agent Run
Command, targets the `instance_ids` Terraform output, and is dry-run by
default:

```bash
terraform -chdir=deploy/compute/terraform output -json > /tmp/octo-compute-outputs.json

./deploy/compute/deploy-apps.sh \
  --outputs-json /tmp/octo-compute-outputs.json \
  --profile <oci-profile> \
  --role all \
  --image-tag <new-image-tag> \
  --app-image-pull-policy always
```

Add `--apply` only after the dry-run shows the expected Shop and CRM
instance OCIDs:

```bash
./deploy/compute/deploy-apps.sh \
  --outputs-json /tmp/octo-compute-outputs.json \
  --profile <oci-profile> \
  --role all \
  --image-tag <new-image-tag> \
  --app-image-pull-policy always \
  --apply
```

For OCI Resource Manager deployments, download or copy the stack outputs
as Terraform-style JSON and pass them with `--outputs-json`. If the
stack was created before the `instance_ids` output existed, pass
`--shop-instance-id`, `--crm-instance-id`, and `--compartment-id`
explicitly.

The Run Command payload intentionally carries only non-secret deployment
values: image reference or tag, optional `repo_ref`, image pull policy,
and image build toggle. It does not send database passwords, CRM admin
passwords, APM private data keys, OCIR auth tokens, or cross-service
secrets. On each host the command refreshes `/opt/octo/deploy` from the
repo when `--repo-ref` is supplied, updates `/opt/octo/runtime.env` for
the selected non-secret values, runs
`/opt/octo/deploy/compute/install.sh --check`, applies the install,
restarts `octo-compute.service`, and checks
`http://127.0.0.1:8080/ready`.

## APM Agent And Trace Detail

The application services are Python/FastAPI, so the app-level APM agent
is OpenTelemetry instrumentation already baked into the images. The
Compute deployment supplies:

- `OCI_APM_ENDPOINT`
- `OCI_APM_PRIVATE_DATAKEY`
- `OCI_APM_PUBLIC_DATAKEY`
- `OTEL_SERVICE_NAME`
- `SERVICE_INSTANCE_ID`
- `APP_RUNTIME=compute`
- `OTEL_TRACES_SAMPLER=always_on`

The app records FastAPI, HTTPX, SQLAlchemy, process metrics, and custom
business spans. Logs carry `oracleApmTraceId` so APM traces and Log
Analytics searches can pivot both ways.

For the private demo, the shop host can also run the Java app-server sidecar:

- Podman: `octo-java-apm.service`
- Docker Compose: `java-apm` profile
- Host port: `18080`
- Internal URL used by the shop app:
  `JAVA_APM_SERVICE_URL=http://127.0.0.1:18080`

The checkout route uses this sidecar for simulated payment authorization.
That gives APM a real Python -> Java HTTP segment and gives the APM App
Servers page JVM/app-server metrics from a business flow instead of only
synthetic traffic. If the Java image or agent is not available, the shop
falls back to the Python simulator and logs the sidecar status.

## Synthetic User And Order Activity

The Compute install also deploys a scheduled `octo-synthetic-users.timer`
on each VM. It is the cron-equivalent job for keeping APM Users, RUM
sessions, orders, payment traces, and app logs populated during demos.
The shop VM posts to its local `/api/synthetic/users/run` endpoint; the
CRM VM posts through `SERVICE_SHOP_URL` when that private URL is
configured. Both paths require `X-Internal-Service-Key`.

Tracked defaults use fictional reserved identities:

```text
SYNTHETIC_USERS_ENABLED=true
SYNTHETIC_USER_EMAIL_DOMAIN=apex.example.test
SYNTHETIC_USER_COUNT=12
SYNTHETIC_USER_ORDER_COUNT=6
SYNTHETIC_USER_DELETE_AFTER_DAYS=7
```

For a private deployment, override `SYNTHETIC_USER_EMAIL_DOMAIN` from the
ignored deployment env file. Do not commit real corporate domains or
operator names. The app writes the synthetic e-mail into OCI RUM
`apmrum.username` so the APM Users page shows distinct users, while app
logs and span attributes keep only domain, counts, and hashed/order
context.

## Stack Monitoring Notes

`enable_stack_monitoring_standard=true` now does three things:

- creates Standard license auto-assignment for hosts
- creates HOST auto-promote configuration
- deploys the Linux Management Agent plugin named `Stack Monitoring`
  (`appmgmt`) to both Compute Management Agents

Some tenancies still reject explicit Stack Monitoring monitored-resource
creation with `Tenant is not permitted to perform this operation`. Keep
`enable_stack_monitoring_host_registration=false` and
`enable_stack_monitoring_atp_registration=false` in those tenancies; the
stack will still deploy the plugin and leave auto-promote active. If the
tenancy is entitled for explicit host resources, set
`enable_stack_monitoring_host_registration=true`.

For the Java APM sidecar, keep using `services/apm-java-demo/`; the Java
agent policy (`read apm-agent-installers`) is already included for the
Compute dynamic group. The service can bundle the agent into the image or
mount it at `/opt/apm-agent/bootstrap/apm-java-agent.jar`.

## OCI Logging And Log Analytics

There are three logging paths:

1. **Application SDK logs**: Shop and CRM call OCI Logging Ingestion
   directly with instance principal auth when the Compute dynamic group
   policy is created. These go to `octo-app` and include
   `oracleApmTraceId`.
2. **Host and stdout logs**: Oracle Cloud Agent Custom Logs Monitoring
   tails OS/cloud-init/install logs and Podman/Docker stdout logs. These
   go to the OS and container stdout custom logs when
   `enable_unified_agent_log_collection=true` and
   `create_compute_instance_principal_policies=true`.
3. **WAF logs**: OCI WAF service logs are enabled when
   `enable_waf_logging=true`.

Set `enable_log_analytics=true` only after Log Analytics is onboarded in
the target tenancy, then provide `log_analytics_namespace` or
`existing_log_analytics_log_group_id`. The stack creates Service
Connector Hub pipelines for app, OS, container, and WAF logs when
`enable_log_analytics_connectors=true` and tenancy quota is available.

Before treating the deployment as production-demo ready, confirm in OCI:

- Compute -> Instance -> Oracle Cloud Agent shows Custom Logs
  Monitoring, Compute Instance Monitoring, Run Command, and Management
  Agent as enabled.
- Logging -> Logs shows fresh records for `octo-app`,
  `octo-compute-os`, `octo-compute-app-stdout`, and the WAF service log.
- Log Analytics shows records from the app, OS/container, and WAF
  connectors if enabled.
- APM -> Trace Explorer shows services `octo-drone-shop` and
  `enterprise-crm-portal`.
- Stack Monitoring shows both Compute hosts under Standard monitoring.
  If `enable_stack_monitoring_atp_registration=true` and the tenancy is
  entitled, confirm the ATP monitored resource as well.

## Smoke Test

Point DNS records at the Load Balancer public IP from the
`load_balancer` output. The default names are `shop.<domain>` and
`crm.<domain>`, but explicit `shop_hostname` and `crm_hostname` values
override those names when DNS is managed elsewhere:

```bash
curl -fsS http://shop.<domain>/ready | jq
curl -fsS http://crm.<domain>/ready | jq
curl -fsS http://shop.<domain>/api/integrations/schema | jq .info.title
curl -fsS http://crm.<domain>/api/integrations/schema | jq .info.title
```

Use `https://` when `enable_lb_https=true` and the Load Balancer
certificate is installed.

For an end-to-end read-only check of the deployed stack, run:

```bash
./deploy/compute/verify-deployment.sh --profile <oci-profile> --plan
```

For OCI Resource Manager deployments without local Terraform state, copy
the stack outputs into a Terraform-style JSON file and run:

```bash
./deploy/compute/verify-deployment.sh \
  --outputs-json outputs.json \
  --profile <oci-profile>
```

Add `--require-https` after the Load Balancer certificate has been
attached. Use `--skip-dns --skip-endpoints` while DNS is intentionally
owned in another tenancy and you are validating the Load Balancer with
explicit `Host` headers instead of hostname resolution. The verifier checks
Terraform drift, DNS, `/ready` endpoints, LB lifecycle and backend health,
WAF, APM domain, ATP lifecycle, DB Management, Operations Insights, Log
Analytics Service Connectors when enabled, Management Agents, and Stack
Monitoring HOST auto-promote when enabled. It never prints sensitive
Terraform outputs.

Then run:

```bash
SHOP_BASE_URL=http://shop.<domain> \
CRM_BASE_URL=http://crm.<domain> \
INTERNAL_SERVICE_KEY=<shared-secret> \
CROSS_SERVICE_E2E_ENABLED=1 \
npx playwright test tests/e2e/cross-service-smoke.spec.ts
```

## Validated Reference Deployment

Validated on May 5, 2026 with `OCI_PROFILE=<OCI_PROFILE>`:

- Hostnames: `shop.example.test`, `crm.example.test`
- Load Balancer public IP is available from `terraform output load_balancer`.
- Private app IPs are available from `terraform output instance_ips`.
- Dedicated ATP private endpoint is available from `terraform output atp`.
- APM endpoint is available from `terraform output apm`.
- Shop and CRM were placed in separate availability domains for the reference
  capacity profile.

The latest reference run of `verify-deployment.sh --profile <OCI_PROFILE> --plan`
returned HTTP 200 for both public `/ready` endpoints, confirmed DNS to
the LB public IP, both LB backend sets reported `OK`, LB/WAF/APM/ATP
resources were in the expected active states, and Terraform reported `No
changes`. Log Analytics is enabled in the external DNS tenancy namespace with an
OCTO LA log group and active Service Connector Hub routes for app, OS,
container, and WAF logs. DB Management and Operations Insights are
enabled with active private endpoints. The Management Agents for both
private hosts are `ACTIVE`, and Stack Monitoring HOST auto-promote is
`ACTIVE`. ATP Stack Monitoring resource registration is disabled in the reference tenancy
because OCI returned a tenant entitlement error for database monitored
resources; Stack Monitoring Standard host onboarding remains enabled.
