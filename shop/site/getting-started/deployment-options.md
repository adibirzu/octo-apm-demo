# Deployment options

The current deployment source of truth is the unified
[`octo-apm-demo`](https://github.com/adibirzu/octo-apm-demo) project.
Pick the path that matches the environment; all paths target the same
Shop and CRM container images and the same Oracle Autonomous Database
integration contract.

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
still want network isolation. The unified stack creates or selects a
VCN, keeps Shop and CRM on private Podman Compute instances, keeps ATP
on a private endpoint, and puts public OCI Load Balancer plus WAF in
front. It also wires APM, OCI Logging, Log Analytics connectors, DB
Management, Operations Insights, and Stack Monitoring Standard.

[![Deploy Full Compute Stack to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/adibirzu/octo-apm-demo/releases/download/compute-resource-manager-stack-20260504/octo-compute-stack.zip)

Full walkthrough:
[Compute Deployment](https://adibirzu.github.io/octo-apm-demo/getting-started/compute-deployment/).

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

Full details: [deploy/resource-manager/README.md](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/resource-manager/README.md).

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

Or paste [`deploy/vm/cloud-init.yaml`](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/vm/cloud-init.yaml) into the
OCI Console Compute create form for a one-shot bootstrap. Full
walkthrough: [deploy/vm/README.md](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/vm/README.md).

## Matrix of cross-service contract parity

All app deployment paths enforce the same integration contract:

| | OKE | Two-instance Compute | Resource Manager | Unified VM |
|---|---|---|---|---|
| `SERVICE_CRM_URL` / `SERVICE_SHOP_URL` | ✅ | ✅ (private IP) | n/a | ✅ (loopback) |
| `INTERNAL_SERVICE_KEY` header on cross-service POSTs | ✅ | ✅ | n/a | ✅ |
| `idempotency_token` + `source_order_id` dedup | ✅ | ✅ | n/a | ✅ |
| `/api/integrations/schema` discovery | ✅ | ✅ | n/a | ✅ |
| APM + RUM + Log Analytics + Stack Monitoring | ✅ | ✅ | ✅ (provisions) | ✅ (consumes) |
