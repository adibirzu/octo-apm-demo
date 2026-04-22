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
