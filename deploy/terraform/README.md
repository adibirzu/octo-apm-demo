# Terraform root stack — octo-apm-demo

One-shot provisioning for every OCI resource the platform needs.
Validated against OCI provider `>= 5.0` and Terraform `>= 1.5`.

```bash
cd deploy/terraform
terraform init
terraform validate   # Success! The configuration is valid.
terraform apply
```

`verify.sh` runs `terraform fmt -check` + `terraform validate` on every
push; CI fails if either drifts.

## Modules

Each module is independently toggleable via a `create_*` boolean in
root `variables.tf`. Defaults are **off** so you can reuse existing OCI
resources by passing their OCIDs in tfvars.

| Module | Toggle | Creates |
|---|---|---|
| [`apm_domain`](modules/apm_domain/) | `create_apm_domain` | APM Domain + public/private data keys + RUM endpoint. RUM web-app registration is a one-time Console step — see [OBSERVABILITY-BOOTSTRAP.md §7a](../OBSERVABILITY-BOOTSTRAP.md). |
| [`waf`](modules/waf/) | always | WAF policies for shop / crm / ops / coordinator |
| [`log_pipeline`](modules/log_pipeline/) | per-source | Service Connector from Logging → Log Analytics |
| [`iam`](modules/iam/) | always | Dynamic groups + policies for OKE workers + builder host |
| [`api_gateway`](modules/api_gateway/) | always | API Gateway + alarm on 5xx bursts |
| [`atp`](modules/atp/) | `create_atp` | Autonomous DB + wallet (base64) + connection strings |
| [`vault`](modules/vault/) | `create_vault` | Vault + AES-256 master key + one VaultSecret per entry |
| [`object_storage`](modules/object_storage/) | `create_object_storage` | 3 buckets (`chaos_state`, `wallet`, `artifacts`) — private, versioned |
| [`logging`](modules/logging/) | `create_logging` | Log Group + 3 custom logs (`octo-app`, `octo-chaos-audit`, `octo-security`) |
| [`stack_monitoring`](modules/stack_monitoring/) | `create_stack_monitoring` | Register the ATP as a Stack Monitoring monitored resource |

## Filling `terraform.tfvars`

See [`terraform.tfvars.example`](terraform.tfvars.example) for the full
parameter set. The minimal portable config is:

```hcl
compartment_id     = "ocid1.compartment.oc1..xxxx"
la_namespace       = "<lognamespace>"
la_log_group_id    = "ocid1.loganalyticsloggroup.oc1..xxxx"
waf_log_group_id   = "ocid1.loggroup.oc1..xxxx"

shop_domain        = "drone.<your-domain>"
crm_domain         = "backend.<your-domain>"
ops_domain         = "ops.<your-domain>"
coordinator_domain = "coordinator.<your-domain>"
```

## When you hit a provider schema error

OCI provider schemas drift — a field valid in 5.10 may disappear in 5.20.
Common fixes:

- `config_type` on `oci_apm_config_config` must be one of
  `AGENT / APDEX / MACS_APM_EXTENSION / METRIC_GROUP / OPTIONS / SPAN_FILTER`.
  Do not use `WEB_APPLICATION` — RUM web apps are Console-only until
  Oracle exposes a resource.
- `log_source_name` is not part of the
  `oci_sch_service_connector.target` schema when `kind = "loganalytics"`.
  Set the LA source via `deploy/oci/ensure_la_sources.sh` instead.
- `oci_stack_monitoring_monitored_resource.credential` requires
  `source` (not `key_id`) — for Autonomous DBs, drop the block entirely
  and pass the ATP OCID as `external_id`.

## Known trade-offs

- ATP admin/wallet passwords go in tfvars — protect the tfvars file
  via filesystem perms + git-crypt or sops. Rotate after first login.
- RUM web-app OCID is collected by hand (§7a of OBSERVABILITY-BOOTSTRAP).
  When the provider ships a resource, replace the stub in
  `modules/apm_domain/main.tf`.
- Stack Monitoring for ATP surfaces the DB in the UI but does not
  by itself enable SQL capture — that requires a Management Agent
  attached via `oci_stack_monitoring_monitored_resources_list_member`,
  which is out of scope for the default demo.
