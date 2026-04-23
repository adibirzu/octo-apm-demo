# OCI Resource Manager stack

One-click tenancy bootstrap for the observability + integration surface
(APM Domain + RUM, Log Analytics app-log pipeline, WAF policies).
Uploaded to **OCI Console → Resource Manager → Stacks**.

The stack does **not** create OKE, VCNs, or the Autonomous Database —
those are selected from existing tenancy resources via the picker
widgets. This is intentional: tenancies vary wildly in network layout
and DB sizing, so hard-coding those would break portability.

## Package + upload

```bash
./deploy/resource-manager/stack-package.sh
# → deploy/resource-manager/build/octo-stack.zip
```

Or create/update the stack directly from the repo:

```bash
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
./deploy/resource-manager/upsert-stack.sh
```

Then in the OCI Console:

1. Developer Services → Resource Manager → Stacks → Create Stack
2. Source = **My Configuration** → upload `octo-stack.zip`
3. Pick the compartment + DB/log pickers guided by the schema
4. Plan → Apply

## What gets created

| Resource | Controlled by |
|---|---|
| `oci_apm_apm_domain` + RUM `oci_apm_config_config` | `create_apm_domain = true` |
| WAF policies (`octo-waf-{shop,crm,ops,coordinator}`) | always |
| Log Analytics Service Connectors (WAF logs) | `waf_log_id_*` when populated |
| Log Analytics Service Connector (app log) | `app_log_id` when populated |

## Outputs

| Output | Purpose |
|---|---|
| `apm_data_upload_endpoint` | Set as `OCI_APM_ENDPOINT` in the app secret |
| `rum_web_application_id` | Set as `OCI_APM_WEB_APPLICATION` |
| `waf_policies` | Attach to the respective load balancers |
| `apm_public_datakey` / `apm_private_datakey` (sensitive) | Inject into the app's Kubernetes secret |

## What this stack does NOT do

- Create OKE clusters, node pools, VCNs, subnets, or load balancers.
- Provision the Autonomous Database (reuse your existing ATP).
- Build or push container images (see `deploy/deploy.sh` and
  `deploy/init-tenancy.sh`).
- Render Kubernetes manifests (see `deploy/k8s/*.yaml` +
  `envsubst`).

The stack is **idempotent**: running apply twice is a no-op if nothing
changed, and the `count`-gated modules keep previously-unused features
(e.g. APM disabled) from drifting.
