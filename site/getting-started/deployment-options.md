# Deployment options

The platform ships four supported install paths. Pick the one that
matches the environment; all four target the same container images
and the same Oracle Autonomous Database integration contract.

[Deploy to Oracle Cloud](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/example-org/octo-apm-demo/releases/download/resource-manager-stack/octo-stack.zip)

[Deploy Full Private Compute Stack to Oracle Cloud](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/example-org/octo-apm-demo/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip)

| Path | When to pick | Setup time | Scaling | Zero-downtime rollouts |
|---|---|---|---|---|
| **OKE (Kubernetes)** | Production, HA, autoscaling, WAF-as-code | 45–90 min | Horizontal + vertical | Yes (rolling) |
| **Two-instance Compute** | Production demo without Kubernetes; private app tier with LB/WAF | 60–90 min | Vertical per app | Restart-based |
| **OCI Resource Manager stack** | Pre-flight the observability + WAF surface from the Console | 5–10 min (one-click) | n/a (infra-only) | n/a |
| **Unified single VM** | Demos, workshops, air-gapped installs | 15–25 min | Vertical only | Restart-based |

## OKE (Kubernetes)

Reference path. Two separate Deployments (shop + CRM) behind OCI LB +
WAF, shared Autonomous Database, observability wired via `ensure_apm.sh`
/ `ensure_stack_monitoring.sh`. See
[new-tenancy.md](new-tenancy.md) and
[oke-deployment.md](oke-deployment.md).

## Two-instance Compute

Production-demo path for teams that want no Kubernetes moving parts but
still want network isolation. Terraform creates a public OCI Load
Balancer with WAF, two private Compute instances, a dedicated private ATP
endpoint, NAT and Service Gateway routes, OCI APM, OCI Logging custom
logs, optional Log Analytics pipelines, Stack Monitoring Standard, and
the instance-principal policies needed for app and OS telemetry.

Private branch note: build `deploy/compute/build/octo-compute-stack.zip`
locally and upload it in Resource Manager. The placeholder GitHub release URL
previously used by the deploy button returns HTTP 404 until a real private
release asset is published.

```bash
./deploy/compute/validate.sh
OCI_PROFILE=<profile> COMPARTMENT_ID=<compartment_ocid> ./deploy/compute/check-oci-limits.sh
cd deploy/compute/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
```

Set `enable_first_boot_deploy=true` for a one-shot Resource Manager
deployment that writes a shell-quoted runtime env, generates the ATP
wallet on each private instance with instance principals, and starts the
Podman services. The host install now also renders
`/opt/octo/container.env` for Podman/Docker so quoted shell values from
`runtime.env` are not passed literally into the app containers. With
`enable_first_boot_deploy=false`, render
role-specific runtime env files after apply and use OCI Bastion, an
existing private route, or Oracle Cloud Agent Run Command to copy the
env files and ATP wallet to the private instances. Run
`/opt/octo/deploy/compute/install.sh --check` on each instance before
starting services. For later image promotions, use
`deploy/compute/deploy-apps.sh`; it targets the private instances with
OCI Run Command, updates only non-secret deployment values, runs the
host pre-flight, restarts `octo-compute.service`, and checks local
`/ready`. The `<REFERENCE_PROFILE>` profile deployment for
`shop.example.test` and `crm.example.test` was validated on May
5, 2026. Full walkthrough:
[compute-deployment.md](compute-deployment.md).

## OCI Resource Manager stack

A pre-packaged Terraform stack that provisions only the **tenancy-level
observability + security surface** (APM Domain, RUM app, Log Analytics
Service Connectors, WAF policies). It does **not** create OKE or the
Autonomous Database — you select those from the picker widgets.

```bash
# Build the zip once per release
./deploy/resource-manager/stack-package.sh
# → deploy/resource-manager/build/octo-stack.zip
```

Upload in **OCI Console → Developer Services → Resource Manager →
Stacks → Create Stack** (source = My Configuration, file =
`octo-stack.zip`). The schema groups variables into Tenancy, DNS,
APM/RUM, Log Analytics, and WAF sections with native OCI pickers.

The historical deploy button used the GitHub Release stack package at
`https://github.com/example-org/octo-apm-demo/releases/download/resource-manager-stack/octo-stack.zip`.
That placeholder URL currently returns HTTP 404. On a private branch, build the
zip and upload it manually, or publish a real private release asset before
using a deploy button.

Full details: [deploy/resource-manager/README.md](https://github.com/example-org/octo-apm-demo/blob/main/deploy/resource-manager/README.md).

## Unified single VM

One OCI Compute instance runs both apps behind nginx, talking to your
existing Autonomous Database over the wallet. Useful for workshops,
local reproductions, or air-gapped deployments.

```bash
cd deploy/vm
cp .env.template .env && ${EDITOR:-vi} .env
unzip /path/to/Wallet_<DB>.zip -d wallet
sudo ./install.sh
```

Or paste [`deploy/vm/cloud-init.yaml`](https://github.com/example-org/octo-apm-demo/blob/main/deploy/vm/cloud-init.yaml) into the
OCI Console Compute create form for a one-shot bootstrap. Full
walkthrough: [deploy/vm/README.md](https://github.com/example-org/octo-apm-demo/blob/main/deploy/vm/README.md).

## Matrix of cross-service contract parity

All app deployment paths enforce the same integration contract:

| | OKE | Two-instance Compute | Resource Manager | Unified VM |
|---|---|---|---|---|
| `SERVICE_CRM_URL` / `SERVICE_SHOP_URL` | ✅ | ✅ (private IP) | n/a | ✅ (loopback) |
| `INTERNAL_SERVICE_KEY` header on cross-service POSTs | ✅ | ✅ | n/a | ✅ |
| `idempotency_token` + `source_order_id` dedup | ✅ | ✅ | n/a | ✅ |
| `/api/integrations/schema` discovery | ✅ | ✅ | n/a | ✅ |
| APM + RUM + Log Analytics + Stack Monitoring | ✅ | ✅ | ✅ (provisions) | ✅ (consumes) |
