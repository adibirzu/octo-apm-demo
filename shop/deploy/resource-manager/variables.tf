###############################################################################
# Variable definitions surfaced by schema.yaml to the OCI Console UI.
# Every variable passed into module "stack" in main.tf is declared here.
###############################################################################

variable "tenancy_ocid" {
  type        = string
  description = "Populated by OCI Resource Manager at plan time."
  default     = ""
}

variable "region" {
  type    = string
  default = ""
}

variable "compartment_id" {
  type = string
}

variable "shop_domain" {
  type    = string
  default = "shop.example.invalid"
}

variable "crm_domain" {
  type    = string
  default = "crm.example.invalid"
}

variable "ops_domain" {
  type    = string
  default = "ops.example.invalid"
}

variable "coordinator_domain" {
  type    = string
  default = "coordinator.example.invalid"
}

variable "waf_mode" {
  type    = string
  default = "DETECTION"
}

variable "waf_log_group_id" {
  type = string
}

variable "admin_allow_cidrs" {
  type    = list(string)
  default = []
}

variable "la_namespace" {
  type    = string
  default = ""
}

variable "la_log_group_id" {
  type    = string
  default = ""
}

variable "create_apm_domain" {
  type    = bool
  default = true
}

variable "apm_domain_display_name" {
  type    = string
  default = "octo-apm"
}

variable "app_log_id" {
  type    = string
  default = ""
}

variable "app_log_group_id" {
  type    = string
  default = ""
}

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
