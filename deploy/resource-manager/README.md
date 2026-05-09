# OCI Resource Manager stack

[Deploy to Oracle Cloud](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/adibirzu/octo-apm-demo/releases/download/resource-manager-stack/octo-stack.zip)

One-click tenancy bootstrap for the observability + integration surface
(APM Domain + RUM, Log Analytics app-log pipeline, WAF policies).
Uploaded to **OCI Console → Resource Manager → Stacks**.

Private branch note: build `deploy/resource-manager/build/octo-stack.zip`
locally and upload it manually. The placeholder GitHub release URL previously
used by the deploy button currently returns HTTP 404 and cannot be imported by
OCI Resource Manager.

The stack does **not** create OKE, VCNs, or the Autonomous Database —
those are selected from existing tenancy resources via the picker
widgets. This is intentional: tenancies vary wildly in network layout
and DB sizing, so hard-coding those would break portability.

If the Console opens `https://cloud.oracle.com/stacks/create` and returns
`NotAuthorizedOrNotFound(404)`, manually open the Resource Manager route:
`https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=...`.
The shorter `/stacks/create` route is stale. If the corrected route still
fails, verify the zip URL returns HTTP 200, then verify Console
tenancy/region context and Resource Manager create/import/job permissions for
the selected compartment.

## Package + upload

The historical deploy button expected a stack package from the
`resource-manager-stack` GitHub Release:

```text
https://github.com/adibirzu/octo-apm-demo/releases/download/resource-manager-stack/octo-stack.zip
```

That placeholder asset currently returns HTTP 404. On a private fork, build
the zip and upload it to a real private release asset before using a
fork-specific button URL, or use manual Console upload.

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
