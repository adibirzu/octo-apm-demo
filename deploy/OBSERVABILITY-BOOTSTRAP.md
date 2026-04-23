# OCI Observability Bootstrap — octo-apm-demo

End-to-end recipe for provisioning APM Domain + RUM + Logging + Log
Analytics + Stack Monitoring against a fresh OCI tenancy, then wiring
the outputs into the app via K8s secrets.

Everything is Terraform-managed (see `deploy/terraform/modules/{apm_domain,logging,stack_monitoring}`). No click-ops required.

## 1. Fill tfvars

```hcl
# deploy/terraform/terraform.tfvars
compartment_id     = "ocid1.compartment.oc1..xxxx"
la_namespace       = "<la namespace from oci log-analytics namespace list>"
la_log_group_id    = "ocid1.loganalyticsloggroup.oc1..xxxx"

create_apm_domain          = true
create_logging             = true
create_stack_monitoring    = true
create_atp                 = true          # if tenancy has no ATP yet
create_vault               = true
create_object_storage      = true
object_storage_namespace   = "<same as OCIR namespace>"

atp_admin_password  = "StrongP@ssw0rd-change-me-12345"
atp_wallet_password = "WalletP@ssw0rd-12345"

vault_secrets = {
  INTERNAL_SERVICE_KEY     = ""   # let init-tenancy.sh generate
  AUTH_TOKEN_SECRET        = ""
  APP_SECRET_KEY           = ""
  BOOTSTRAP_ADMIN_PASSWORD = ""
  # Populate real values for integrations:
  STRIPE_API_KEY           = ""
  STRIPE_WEBHOOK_SECRET    = ""
  SLACK_WEBHOOK_URL        = ""
}

# WAF prerequisites (existing)
waf_log_group_id   = "ocid1.loggroup.oc1..xxxx"
shop_domain        = "drone.<your-domain>"
crm_domain         = "backend.<your-domain>"
ops_domain         = "ops.<your-domain>"
coordinator_domain = "coordinator.<your-domain>"
```

## 2. Apply Terraform

```bash
cd deploy/terraform
terraform init
terraform apply
```

Resources created:

| Resource | Module | Outputs |
|---|---|---|
| APM Domain + RUM web app | `apm_domain` | `apm_endpoint`, `apm_private_datakey`, `apm_public_datakey`, `rum_endpoint`, `rum_web_application_id` |
| ATP (1 OCPU, 1 TB, auto-scale) | `atp` | `atp_id`, `atp_wallet_b64`, `atp_connection_strings` |
| Vault + AES-256 master key + secret OCIDs | `vault` | `vault_id`, `secret_ids` |
| Object Storage buckets (chaos-state, wallet, artifacts) | `object_storage` | bucket names |
| Log Group + 3 custom logs (app, chaos-audit, security) | `logging` | `log_group_id`, `log_app_id`, `log_chaos_audit_id`, `log_security_id` |
| LA pipelines (WAF + app) | `log_pipeline` | per-pipeline OCIDs |
| Stack Monitoring monitored resource (ATP) | `stack_monitoring` | `monitored_resource_id` |

## 3. Read outputs into env for init-tenancy.sh

```bash
cd deploy/terraform
eval "$(terraform output -json | jq -r '
  to_entries[] |
  select(.value.value != null and .value.value != "") |
  "export " + (.key | ascii_upcase) + "=\"" + (.value.value | tostring) + "\""
')"

# Decode the wallet zip to /tmp/wallet.zip
terraform output -raw atp_wallet_b64 | base64 -d > /tmp/wallet.zip
```

## 4. Run init-tenancy.sh

```bash
export OCI_APM_PRIVATE_DATAKEY=$(terraform output -raw apm_private_datakey)
export OCI_APM_PUBLIC_DATAKEY=$(terraform output -raw apm_public_datakey)
export OCI_APM_ENDPOINT=$(terraform output -json apm_domain | jq -r .apm_data_upload_endpoint)
export OCI_APM_RUM_ENDPOINT=$(terraform output -json apm_domain | jq -r .rum_endpoint)
export OCI_APM_RUM_WEB_APPLICATION_OCID=$(terraform output -json apm_domain | jq -r .rum_web_application_id)

export OCI_LOG_GROUP_ID=$(terraform output -json logging | jq -r .log_group_id)
export OCI_LOG_ID=$(terraform output -json logging | jq -r .log_app_id)
export OCI_LOG_GROUP_CHAOS_AUDIT=$(terraform output -json logging | jq -r .log_chaos_audit_id)
export OCI_LOG_SECURITY=$(terraform output -json logging | jq -r .log_security_id)

cd ../..
./deploy/init-tenancy.sh
```

`init-tenancy.sh` creates the following K8s secrets (see `deploy/init-tenancy.sh`):
`octo-auth`, `octo-atp`, `octo-apm`, `octo-logging`, `octo-sso`, `octo-genai`, `octo-integrations`.

Every secret is seeded with the env values above — or generated random
where applicable (`AUTH_TOKEN_SECRET`, `INTERNAL_SERVICE_KEY`,
`APP_SECRET_KEY`, `BOOTSTRAP_ADMIN_PASSWORD`).

## 5. Deploy shop + crm

```bash
export OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop
./deploy/deploy-shop.sh

export OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal
./deploy/deploy-crm.sh
```

## 6. Verify

| Signal | Where | Expectation |
|---|---|---|
| Traces | OCI APM → Trace Explorer | `service.name=octo-drone-shop` and `octo-enterprise-crm` |
| RUM beacons | OCI APM → Real User Monitoring | `drone.<your-domain>` page views |
| App logs | OCI Logging → `octo-apm-demo/octo-app` | stream of JSON with `trace_id` |
| Chaos audit | OCI Logging → `octo-apm-demo/octo-chaos-audit` | one record per apply/clear |
| Security logs | OCI Logging → `octo-apm-demo/octo-security` | auth denials, WAF-correlated events |
| LA search | OCI Log Analytics → source `octo-shop-app-json` | rows visible within 2 min of traffic |
| ATP monitoring | OCI Observability → Stack Monitoring → Autonomous Databases | `octo-apm-demo-atp` shown as Up, SQL perf chart populated |
| WAF pipeline | OCI Log Analytics → source `octo-waf` | both shop + crm WAF traffic |

## 7. Stack Monitoring details for ATP

ATP's built-in metrics cover:

- CPU utilization, storage, IOPS
- Active sessions, wait events, SQL performance
- Backup status, data guard lag
- Connection count per service (low/medium/high)

These are pushed by OCI itself (agentless). Dashboards ship in OCI
Observability → Databases → Autonomous Database by default; the
Stack Monitoring resource created by this module adds the ATP to the
cross-service dependency map so drill-down from app traces → DB sessions
works in APM.

No Management Agent required. For host-level or custom SQL metric
capture, add a Management Agent on an OKE node and register the ATP
with an `external_id` — but this is beyond the default setup.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| No traces in APM | Check pod logs for `OCI_APM_ENDPOINT` — must be the data-upload endpoint, not the domain API endpoint. |
| No app logs in Logging | `kubectl exec` into shop pod, `printenv | grep OCI_LOG_ID` — must be non-empty. Rebuild the `octo-logging` secret via `init-tenancy.sh`. |
| ATP monitored resource reports Unknown | Allow 10 min after first connection; Stack Monitoring polls on its own cadence. Confirm the ATP OCID in `terraform output stack_monitoring_atp_id` matches. |
| LA pipeline empty | Check `la_log_group_id` is in the same region as `source_log_group_id` — cross-region pipelines require explicit federation. |
