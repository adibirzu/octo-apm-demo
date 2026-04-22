###############################################################################
# OCI Resource Manager stack — wraps deploy/terraform so operators get a
# guided Console experience (compartment picker, APM create toggle,
# Log Analytics pickers) without needing local terraform.
#
# Packaging:
#   ./deploy/resource-manager/stack-package.sh
# produces deploy/resource-manager/build/octo-stack.zip which is the
# artifact uploaded to OCI Console → Resource Manager → Stacks.
###############################################################################

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

# Resource Manager injects auth + region via environment variables;
# keep the provider block empty so the stack is portable.
provider "oci" {}

module "stack" {
  source = "../terraform"

  compartment_id     = var.compartment_id
  shop_domain        = var.shop_domain
  crm_domain         = var.crm_domain
  ops_domain         = var.ops_domain
  coordinator_domain = var.coordinator_domain

  waf_mode          = var.waf_mode
  waf_log_group_id  = var.waf_log_group_id
  admin_allow_cidrs = var.admin_allow_cidrs

  la_namespace    = var.la_namespace
  la_log_group_id = var.la_log_group_id

  # APM Domain + RUM
  create_apm_domain       = var.create_apm_domain
  apm_domain_display_name = var.apm_domain_display_name

  # App log pipeline
  app_log_id       = var.app_log_id
  app_log_group_id = var.app_log_group_id

  # WAF per-frontend logs
  waf_log_id_shop        = var.waf_log_id_shop
  waf_log_id_crm         = var.waf_log_id_crm
  waf_log_id_ops         = var.waf_log_id_ops
  waf_log_id_coordinator = var.waf_log_id_coordinator
}

output "apm_data_upload_endpoint" {
  value       = try(module.stack.apm_domain.apm_data_upload_endpoint, "")
  description = "Set as OCI_APM_ENDPOINT in the app secret."
}

output "rum_web_application_id" {
  value       = try(module.stack.apm_domain.rum_web_application_id, "")
  description = "Set as OCI_APM_WEB_APPLICATION."
}

output "waf_policies" {
  value       = module.stack.waf_policies
  description = "OCIDs of the per-frontend WAF policies."
}

output "apm_public_datakey" {
  value       = module.stack.apm_public_datakey
  sensitive   = true
  description = "OCI_APM_PUBLIC_DATAKEY for the browser RUM SDK."
}

output "apm_private_datakey" {
  value       = module.stack.apm_private_datakey
  sensitive   = true
  description = "OCI_APM_PRIVATE_DATAKEY for the OTel exporter."
}
