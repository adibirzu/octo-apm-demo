###############################################################################
# Root-stack inputs — tenancy-portable. Fill via terraform.tfvars or
# environment variables (`TF_VAR_*`). No value is hardcoded.
###############################################################################

variable "compartment_id" {
  type        = string
  description = "Compartment OCID hosting the demo stack."
}

variable "shop_domain" {
  type        = string
  default     = "shop.example.cloud"
  description = "Public hostname for the drone shop frontend."
}

variable "crm_domain" {
  type        = string
  default     = "crm.example.cloud"
  description = "Public hostname for the CRM portal."
}

variable "ops_domain" {
  type        = string
  default     = "ops.example.cloud"
  description = "Public hostname for the internal ops/cp console."
}

variable "coordinator_domain" {
  type        = string
  default     = "coordinator.example.cloud"
  description = "Public hostname for the OCI Coordinator UI/API."
}

variable "waf_mode" {
  type        = string
  default     = "DETECTION"
  description = "WAF mode applied to every frontend (DETECTION | BLOCK)."
}

variable "waf_log_group_id" {
  type        = string
  description = "OCI Logging log group OCID for WAF events."
}

variable "admin_allow_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs permitted to reach /api/admin/*. Leave empty to skip the admin guard."
}

variable "la_namespace" {
  type        = string
  description = "OCI Log Analytics namespace."
}

variable "la_log_group_id" {
  type        = string
  description = "OCI Log Analytics log group OCID receiving app + WAF logs."
}
