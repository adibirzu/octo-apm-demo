###############################################################################
# Root stack — wires the WAF module per frontend.
# This file is additive; it does not touch pre-existing stack components.
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

provider "oci" {}

module "waf_shop" {
  source            = "./modules/waf"
  compartment_id    = var.compartment_id
  display_name      = "octo-waf-shop"
  domain            = var.shop_domain
  mode              = var.waf_mode
  log_group_id      = var.waf_log_group_id
  admin_allow_cidrs = [] # shop has no admin surface
}

module "waf_crm" {
  source            = "./modules/waf"
  compartment_id    = var.compartment_id
  display_name      = "octo-waf-crm"
  domain            = var.crm_domain
  mode              = var.waf_mode
  log_group_id      = var.waf_log_group_id
  admin_allow_cidrs = var.admin_allow_cidrs
}

module "waf_ops" {
  source            = "./modules/waf"
  compartment_id    = var.compartment_id
  display_name      = "octo-waf-ops"
  domain            = var.ops_domain
  mode              = var.waf_mode
  log_group_id      = var.waf_log_group_id
  admin_allow_cidrs = var.admin_allow_cidrs
}

module "waf_coordinator" {
  source            = "./modules/waf"
  compartment_id    = var.compartment_id
  display_name      = "octo-waf-coordinator"
  domain            = var.coordinator_domain
  mode              = var.waf_mode
  log_group_id      = var.waf_log_group_id
  admin_allow_cidrs = var.admin_allow_cidrs
}

###############################################################################
# WAF log pipelines — one service connector per frontend. Source log/group
# OCIDs are passed in via tfvars (they are created outside this module when
# WAF is enabled on the load balancer).
###############################################################################

variable "waf_log_id_shop" {
  type    = string
  default = ""
}
variable "waf_log_id_crm" {
  type    = string
  default = ""
}
variable "waf_log_id_ops" {
  type    = string
  default = ""
}
variable "waf_log_id_coordinator" {
  type    = string
  default = ""
}

module "la_pipeline_waf_shop" {
  source              = "./modules/log_pipeline"
  count               = var.waf_log_id_shop == "" ? 0 : 1
  compartment_id      = var.compartment_id
  display_name        = "la-pipeline-waf-shop"
  source_log_group_id = var.waf_log_group_id
  source_log_id       = var.waf_log_id_shop
  la_namespace        = var.la_namespace
  la_log_group_id     = var.la_log_group_id
  la_source_name      = "octo-waf"
}

module "la_pipeline_waf_crm" {
  source              = "./modules/log_pipeline"
  count               = var.waf_log_id_crm == "" ? 0 : 1
  compartment_id      = var.compartment_id
  display_name        = "la-pipeline-waf-crm"
  source_log_group_id = var.waf_log_group_id
  source_log_id       = var.waf_log_id_crm
  la_namespace        = var.la_namespace
  la_log_group_id     = var.la_log_group_id
  la_source_name      = "octo-waf"
}

module "la_pipeline_waf_ops" {
  source              = "./modules/log_pipeline"
  count               = var.waf_log_id_ops == "" ? 0 : 1
  compartment_id      = var.compartment_id
  display_name        = "la-pipeline-waf-ops"
  source_log_group_id = var.waf_log_group_id
  source_log_id       = var.waf_log_id_ops
  la_namespace        = var.la_namespace
  la_log_group_id     = var.la_log_group_id
  la_source_name      = "octo-waf"
}

module "la_pipeline_waf_coordinator" {
  source              = "./modules/log_pipeline"
  count               = var.waf_log_id_coordinator == "" ? 0 : 1
  compartment_id      = var.compartment_id
  display_name        = "la-pipeline-waf-coordinator"
  source_log_group_id = var.waf_log_group_id
  source_log_id       = var.waf_log_id_coordinator
  la_namespace        = var.la_namespace
  la_log_group_id     = var.la_log_group_id
  la_source_name      = "octo-waf"
}

output "waf_policies" {
  value = {
    shop        = module.waf_shop.policy_ocid
    crm         = module.waf_crm.policy_ocid
    ops         = module.waf_ops.policy_ocid
    coordinator = module.waf_coordinator.policy_ocid
    mode        = upper(var.waf_mode)
  }
}

###############################################################################
# APM Domain + RUM web app. Opt-in: set create_apm_domain = true in tfvars.
# Resulting apm_endpoint, data keys, and RUM web application OCID are
# exported so they can be written to Kubernetes secrets (octo-apm).
###############################################################################

variable "create_apm_domain" {
  type        = bool
  default     = false
  description = "Provision an APM Domain + RUM web app in this tenancy."
}

variable "apm_domain_display_name" {
  type    = string
  default = "octo-apm"
}

module "apm_domain" {
  source                       = "./modules/apm_domain"
  count                        = var.create_apm_domain ? 1 : 0
  compartment_id               = var.compartment_id
  display_name                 = var.apm_domain_display_name
  web_application_display_name = "octo-drone-shop-web"
}

output "apm_domain" {
  value = var.create_apm_domain ? {
    apm_domain_id            = module.apm_domain[0].apm_domain_id
    apm_data_upload_endpoint = module.apm_domain[0].apm_data_upload_endpoint
    rum_web_application_id   = module.apm_domain[0].rum_web_application_id
    rum_endpoint             = module.apm_domain[0].rum_endpoint
  } : null
  description = "APM Domain + RUM coordinates for the app. Data keys are exported separately (sensitive)."
}

output "apm_public_datakey" {
  value       = var.create_apm_domain ? module.apm_domain[0].apm_public_datakey : ""
  sensitive   = true
  description = "Public data key for browser RUM (OCI_APM_PUBLIC_DATAKEY)."
}

output "apm_private_datakey" {
  value       = var.create_apm_domain ? module.apm_domain[0].apm_private_datakey : ""
  sensitive   = true
  description = "Private data key for OTel exporter (OCI_APM_PRIVATE_DATAKEY)."
}

###############################################################################
# App log pipeline — routes the app's OCI Logging log (OCI_LOG_ID) into
# Log Analytics so trace-correlated searches work alongside WAF logs.
###############################################################################

variable "app_log_id" {
  type        = string
  default     = ""
  description = "OCI Logging log OCID for the app (matches OCI_LOG_ID env var). Leave empty to skip."
}

variable "app_log_group_id" {
  type        = string
  default     = ""
  description = "OCI Logging log group OCID that owns app_log_id."
}

module "la_pipeline_app_logs" {
  source              = "./modules/log_pipeline"
  count               = var.app_log_id == "" ? 0 : 1
  compartment_id      = var.compartment_id
  display_name        = "la-pipeline-octo-shop-app"
  source_log_group_id = var.app_log_group_id
  source_log_id       = var.app_log_id
  la_namespace        = var.la_namespace
  la_log_group_id     = var.la_log_group_id
  la_source_name      = "octo-shop-app-json"
}

###############################################################################
# ATP + Vault + Object Storage + Logging + Stack Monitoring.
# Each is gated behind a `create_*` flag so operators can provision
# selectively (e.g. reuse an existing ATP while creating a fresh Vault).
###############################################################################

module "atp" {
  source                   = "./modules/atp"
  count                    = var.create_atp ? 1 : 0
  compartment_id           = var.compartment_id
  admin_password           = var.atp_admin_password
  wallet_password          = var.atp_wallet_password
  whitelisted_ips          = var.atp_whitelisted_ips
}

module "vault" {
  source         = "./modules/vault"
  count          = var.create_vault ? 1 : 0
  compartment_id = var.compartment_id
  secrets        = var.vault_secrets
}

module "object_storage" {
  source         = "./modules/object_storage"
  count          = var.create_object_storage ? 1 : 0
  compartment_id = var.compartment_id
  namespace      = var.object_storage_namespace
}

module "logging" {
  source             = "./modules/logging"
  count              = var.create_logging ? 1 : 0
  compartment_id     = var.compartment_id
  retention_duration = var.logging_retention_days
}

locals {
  stack_monitoring_atp_ocid = var.create_atp ? module.atp[0].atp_id : var.stack_monitoring_atp_id
}

module "stack_monitoring_atp" {
  source           = "./modules/stack_monitoring"
  count            = var.create_stack_monitoring && local.stack_monitoring_atp_ocid != "" ? 1 : 0
  compartment_id   = var.compartment_id
  autonomous_db_id = local.stack_monitoring_atp_ocid
}

output "atp" {
  value = var.create_atp ? {
    atp_id                  = module.atp[0].atp_id
    atp_db_name             = module.atp[0].atp_db_name
    atp_service_console_url = module.atp[0].atp_service_console_url
  } : null
  description = "ATP coordinates (non-sensitive). DSN + wallet exported separately."
}

output "atp_wallet_b64" {
  value       = var.create_atp ? module.atp[0].atp_wallet_content_base64 : ""
  sensitive   = true
  description = "Base64 ATP wallet zip — land in Vault/K8s secret octo-atp-wallet."
}

output "vault" {
  value = var.create_vault ? {
    vault_id      = module.vault[0].vault_id
    master_key_id = module.vault[0].master_key_id
    secret_ids    = module.vault[0].secret_ids
  } : null
}

output "object_storage" {
  value = var.create_object_storage ? {
    chaos_state_bucket = module.object_storage[0].chaos_state_bucket
    wallet_bucket      = module.object_storage[0].wallet_bucket
    artifacts_bucket   = module.object_storage[0].artifacts_bucket
  } : null
}

output "logging" {
  value = var.create_logging ? {
    log_group_id       = module.logging[0].log_group_id
    log_app_id         = module.logging[0].log_app_id
    log_chaos_audit_id = module.logging[0].log_chaos_audit_id
    log_security_id    = module.logging[0].log_security_id
  } : null
}

output "stack_monitoring_atp_id" {
  value = length(module.stack_monitoring_atp) > 0 ? module.stack_monitoring_atp[0].monitored_resource_id : ""
}
