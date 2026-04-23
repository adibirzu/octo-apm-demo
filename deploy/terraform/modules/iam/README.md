# IAM template

Two dynamic groups + two policies covering every OCI service the
platform touches. Apply once per tenancy:

```hcl
module "iam" {
  source               = "./modules/iam"
  tenancy_ocid         = var.tenancy_ocid
  compartment_id       = var.compartment_id
  oke_cluster_compartment_id = var.oke_cluster_compartment_id  # optional, same compartment by default
  builder_vm_compartment_id  = var.builder_vm_compartment_id   # optional
}
```

## Dynamic groups

| Name | Match rule | Why |
|---|---|---|
| `octo-oke-workers` | `ALL {instance.compartment.id = '<oke-compartment>'}` | OKE worker nodes use instance principal to talk to OCIR + APM + Logging + etc. |
| `octo-builder-host` | `ALL {instance.compartment.id = '<builder-compartment>'}` | The x86_64 remote builder VM pushes images to OCIR |

## Policies

`octo-oke-workers`:

- `read repos` — pull images from OCIR
- `read secret-family` — fetch Vault secrets via CSI driver
- `read objects` — wallet + artifacts from Object Storage
- `use log-content` — ingest app logs via Logging SDK
- `use apm-domains` — push traces to APM
- `use metrics where target.metrics.namespace = 'octo_drone_shop'` — publish the shop's custom metrics
- `use stack-monitoring-resources` — enrich monitored resources
- `use generative-ai-family` — AI assistant
- `use ons-topics` — emit cross-service events

`octo-builder-host`:

- `manage repos` — create + push to OCIR repositories
- `read objects` — fetch source artifacts from Object Storage

## What this does NOT grant

- No OCIR-level admin (no `delete`).
- No access to other compartments.
- No VCN / IAM / tenancy-level operations.
- No Functions / Cloud Shell.

Add additional narrow grants as the platform expands — never wildcards.
