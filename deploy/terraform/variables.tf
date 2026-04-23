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
  default     = "drone.example.cloud"
  description = "Public hostname for the drone shop frontend."
}

variable "crm_domain" {
  type        = string
  default     = "backend.example.cloud"
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

###############################################################################
# ATP — application database. Off by default so an existing ATP can be
# reused via its OCID.
###############################################################################

variable "create_atp" {
  type    = bool
  default = false
}

variable "atp_admin_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "atp_wallet_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "atp_whitelisted_ips" {
  type    = list(string)
  default = []
}

###############################################################################
# Vault — secret storage for app + integrations. Off by default so an
# existing Vault can be reused.
###############################################################################

variable "create_vault" {
  type    = bool
  default = false
}

variable "vault_secrets" {
  type      = map(string)
  sensitive = true
  default   = {}
}

###############################################################################
# Object Storage — chaos state, wallet mirror, artifacts.
###############################################################################

variable "create_object_storage" {
  type    = bool
  default = false
}

variable "object_storage_namespace" {
  type    = string
  default = ""
}

###############################################################################
# Logging — log group + custom logs (app, chaos-audit, security).
###############################################################################

variable "create_logging" {
  type    = bool
  default = false
}

variable "logging_retention_days" {
  type    = number
  default = 30
}

###############################################################################
# Stack Monitoring — register the ATP DB as a monitored resource.
###############################################################################

variable "create_stack_monitoring" {
  type    = bool
  default = false
}

variable "stack_monitoring_atp_id" {
  type        = string
  default     = ""
  description = "ATP OCID to register. If create_atp=true this is auto-wired to the new DB."
}

###############################################################################
# OKE — provision when the tenancy has no usable cluster. Reuse an existing
# one by passing create_oke = false + existing_cluster_id (no wiring yet —
# root module currently consumes the output only when create_oke=true).
###############################################################################

variable "create_oke" {
  type    = bool
  default = false
}

variable "oke_cluster_name" {
  type    = string
  default = "octo-apm-demo-oke"
}

variable "oke_kubernetes_version" {
  type    = string
  default = "v1.31.1"
}

variable "oke_vcn_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "oke_node_pool_size" {
  type    = number
  default = 3
}

variable "oke_node_ocpus" {
  type    = number
  default = 2
}

variable "oke_node_memory_gbs" {
  type    = number
  default = 16
}

variable "oke_node_boot_volume_gbs" {
  type    = number
  default = 93
}

variable "oke_node_image_id" {
  type    = string
  default = ""
  description = "OKE-managed node image OCID. Required when create_oke=true."
}

variable "oke_availability_domain_names" {
  type    = list(string)
  default = []
}
