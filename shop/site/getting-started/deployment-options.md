# Deployment options

The platform ships three supported install paths. Pick the one that
matches the environment; all three target the same container images
and the same Oracle Autonomous Database backend.

| Path | When to pick | Setup time | Scaling | Zero-downtime rollouts |
|---|---|---|---|---|
| **OKE (Kubernetes)** | Production, HA, autoscaling, WAF-as-code | 45–90 min | Horizontal + vertical | Yes (rolling) |
| **OCI Resource Manager stack** | Pre-flight the observability + WAF surface from the Console | 5–10 min (one-click) | n/a (infra-only) | n/a |
| **Unified single VM** | Demos, workshops, air-gapped installs | 15–25 min | Vertical only | Restart-based |

## OKE (Kubernetes)

Reference path. Two separate Deployments (shop + CRM) behind OCI LB +
WAF, shared Autonomous Database, observability wired via `ensure_apm.sh`
/ `ensure_stack_monitoring.sh`. See
[new-tenancy.md](new-tenancy.md) and
[oke-deployment.md](oke-deployment.md).

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

Full details: [deploy/resource-manager/README.md](https://github.com/adibirzu/octo-drone-shop/blob/main/deploy/resource-manager/README.md).

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

Or paste [`deploy/vm/cloud-init.yaml`](https://github.com/adibirzu/octo-drone-shop/blob/main/deploy/vm/cloud-init.yaml) into the
OCI Console Compute create form for a one-shot bootstrap. Full
walkthrough: [deploy/vm/README.md](https://github.com/adibirzu/octo-drone-shop/blob/main/deploy/vm/README.md).

## Matrix of cross-service contract parity

All three paths enforce the same integration contract:

| | OKE | Resource Manager | Unified VM |
|---|---|---|---|
| `SERVICE_CRM_URL` / `SERVICE_SHOP_URL` | ✅ | n/a | ✅ (loopback) |
| `INTERNAL_SERVICE_KEY` header on cross-service POSTs | ✅ | n/a | ✅ |
| `idempotency_token` + `source_order_id` dedup | ✅ | n/a | ✅ |
| `/api/integrations/schema` discovery | ✅ | n/a | ✅ |
| APM + RUM + Log Analytics + Stack Monitoring | ✅ | ✅ (provisions) | ✅ (consumes) |
