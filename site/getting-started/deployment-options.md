# Deployment options

The platform ships four supported install paths. Pick the one that
matches the environment; all four target the same container images
and the same Oracle Autonomous Database integration contract.

[Deploy to Oracle Cloud](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=%%GITHUB_REPO_URL%%/releases/download/resource-manager-stack/octo-stack.zip)

[Deploy Full Private Compute Stack to Oracle Cloud](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=%%GITHUB_REPO_URL%%/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip)

| Path | When to pick | Setup time | Scaling | Zero-downtime rollouts |
|---|---|---|---|---|
| **OKE (Kubernetes)** | Production, HA, autoscaling, WAF-as-code | 45–90 min | Horizontal + vertical | Yes (rolling) |
| **Two-instance Compute** | Production demo without Kubernetes; private app tier with LB/WAF | 60–90 min | Vertical per app | Restart-based |
| **OCI Resource Manager stack** | Pre-flight the observability + WAF surface from the Console | 5–10 min (one-click) | n/a (infra-only) | n/a |
| **Unified single VM** | Demos, workshops, air-gapped installs | 15–25 min | Vertical only | Restart-based |

## OKE (Kubernetes)

Kubernetes path for production-style demos, workshops, autoscaling, and staged
VM-to-OKE cutovers. The OKE runtime deploys the same Shop, CRM, Java
app-server, and Workflow Gateway images behind OCI LB/WAF/API Gateway routing,
uses the same shared Autonomous Database and APM domain contract, and preserves the same
event-generation and Captured Data Center UX as the VM runtime.

Two or more Deployments run behind OCI LB + WAF, with observability wired via
`ensure_apm.sh`, OKE manifests/Helm, OCI Kubernetes Monitoring, and the same Log
Analytics field/search/dashboard assets. See
[new-tenancy.md](new-tenancy.md) and
[oke-deployment.md](oke-deployment.md).

## Two-instance Compute

Production-demo path for teams that want no Kubernetes moving parts but
still want network isolation. Terraform creates a public OCI Load
Balancer with WAF, two private Compute instances, a dedicated private ATP
endpoint, NAT and Service Gateway routes, OCI APM, OCI Logging custom
logs, optional Log Analytics pipelines, Stack Monitoring Standard, and
the instance-principal policies needed for app and OS telemetry.

This path remains the simplest private reference for showing the complete live
journey: Shop checkout, Admin Simulation Lab, Demo Storyboard, Attack Lab,
Java App Servers, OCI APM, OCI Logging, Log Analytics, ATP SQL drilldown, and
the `/captured-data` operator pivot page.

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
`/ready`. The `<OCI_PROFILE>` profile deployment for
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
`%%GITHUB_REPO_URL%%/releases/download/resource-manager-stack/octo-stack.zip`.
That placeholder URL currently returns HTTP 404. On a private branch, build the
zip and upload it manually, or publish a real private release asset before
using a deploy button.

Full details: [deploy/resource-manager/README.md](%%GITHUB_REPO_URL%%/blob/main/deploy/resource-manager/README.md).

## Unified single VM

One OCI Compute instance runs Shop, Admin/CRM, Java payment gateway, and
Workflow Gateway behind nginx, talking to your existing Autonomous Database
over the wallet. Useful for workshops, local reproductions, or air-gapped
deployments.

```bash
cd deploy/vm
cp .env.template .env && ${EDITOR:-vi} .env
unzip /path/to/Wallet_<DB>.zip -d wallet
sudo ./install.sh
```

Or paste [`deploy/vm/cloud-init.yaml`](%%GITHUB_REPO_URL%%/blob/main/deploy/vm/cloud-init.yaml) into the
OCI Console Compute create form for a one-shot bootstrap. Full
walkthrough: [deploy/vm/README.md](%%GITHUB_REPO_URL%%/blob/main/deploy/vm/README.md).

## Matrix of cross-service contract parity

All app deployment paths enforce the same integration contract. The local
container stack is intentionally OCI-disabled and uses Postgres, so Oracle-only
Select AI/workflow execution is profile-gated there; VM, two-instance Compute,
and OKE run the production Oracle path.

| Capability | OKE | Two-instance Compute | Unified VM | Local containers |
|---|---|---|---|---|
| `SERVICE_CRM_URL` / `SERVICE_SHOP_URL` | ✅ | ✅ (private IP) | ✅ (bridge) | ✅ (bridge) |
| `INTERNAL_SERVICE_KEY` header on cross-service POSTs | ✅ | ✅ | ✅ | ✅ |
| `idempotency_token` + `source_order_id` dedup | ✅ | ✅ | ✅ | ✅ |
| `/api/integrations/schema` discovery | ✅ | ✅ | ✅ | ✅ |
| Java payment gateway simulation | ✅ `octo-java-app-server-oke` | ✅ `octo-java-app-server` | ✅ `octo-java-app-server` | ✅ `octo-java-app-server-local` |
| Workflow Gateway / Select AI | ✅ `octo-workflow-gateway-oke` | ✅ `octo-workflow-gateway` | ✅ `octo-workflow-gateway` | ⚠️ Oracle path disabled by default |
| GenAI LLMetry + optional Langfuse export | ✅ | ✅ | ✅ | ✅ local/no export |
| APM + RUM + Log Analytics + Stack Monitoring | ✅ | ✅ | ✅ consumes existing resources | ⚠️ exporters disabled |
| Guided event generation + `/captured-data` pivots | ✅ | ✅ | ✅ | ✅ |
| Resource Manager | provisions infra and can bootstrap OKE dependencies | provisions private Compute path | n/a | n/a |
