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
