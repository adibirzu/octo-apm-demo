###############################################################################
# Autonomous Transaction Processing DB for octo-apm-demo.
#
# Provisions a shared ATP instance consumed by both shop + crm. The DB's
# wallet + credentials are exported so init-tenancy.sh can land them in
# Vault + K8s secrets. A downstream Stack Monitoring module attaches to
# this DB via the exported OCID.
#
# Opt-in: set `create_atp = true` in root tfvars. Default off so a tenancy
# that already has an ATP can pass an existing OCID via `atp_ocid_existing`.
###############################################################################

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

variable "compartment_id" {
  type = string
}

variable "display_name" {
  type    = string
  default = "octo-apm-demo-atp"
}

variable "db_name" {
  type    = string
  default = "OCTOATP"
  validation {
    condition     = can(regex("^[A-Z][A-Z0-9]{0,13}$", var.db_name))
    error_message = "db_name must be 1-14 upper-alphanumeric chars starting with a letter."
  }
}

variable "cpu_core_count" {
  type    = number
  default = 1
}

variable "data_storage_size_in_tbs" {
  type    = number
  default = 1
}

variable "is_auto_scaling_enabled" {
  type    = bool
  default = true
}

variable "admin_password" {
  type        = string
  sensitive   = true
  description = "Bootstrap ADMIN password. Must meet Oracle complexity rules. Rotate immediately after first login."
  validation {
    condition     = length(var.admin_password) >= 12 && length(var.admin_password) <= 30
    error_message = "admin_password must be 12-30 chars."
  }
}

variable "wallet_password" {
  type        = string
  sensitive   = true
  description = "Password protecting the downloaded wallet zip. Min 8 chars — empty produces a zip that cannot be decrypted."
  validation {
    condition     = length(var.wallet_password) >= 8
    error_message = "wallet_password must be at least 8 characters."
  }
}

variable "whitelisted_ips" {
  type        = list(string)
  default     = []
  description = "Optional CIDR allowlist for the mTLS endpoint. Empty = any source (OKE workers still need wallet)."
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "oci_database_autonomous_database" "this" {
  compartment_id           = var.compartment_id
  db_name                  = var.db_name
  display_name             = var.display_name
  cpu_core_count           = var.cpu_core_count
  data_storage_size_in_tbs = var.data_storage_size_in_tbs
  is_auto_scaling_enabled  = var.is_auto_scaling_enabled
  admin_password           = var.admin_password
  db_workload              = "OLTP"
  license_model            = "LICENSE_INCLUDED"

  whitelisted_ips = length(var.whitelisted_ips) == 0 ? null : var.whitelisted_ips

  freeform_tags = merge({
    "project" = "octo-apm-demo"
    "role"    = "application-db"
  }, var.tags)
}

resource "oci_database_autonomous_database_wallet" "this" {
  autonomous_database_id = oci_database_autonomous_database.this.id
  password               = var.wallet_password
  generate_type          = "SINGLE"
  base64_encode_content  = true
}

output "atp_id" {
  value       = oci_database_autonomous_database.this.id
  description = "ATP OCID — feed to Stack Monitoring + CHAOS state tables."
}

output "atp_db_name" {
  value = oci_database_autonomous_database.this.db_name
}

output "atp_service_console_url" {
  value = oci_database_autonomous_database.this.service_console_url
}

output "atp_connection_urls" {
  value       = oci_database_autonomous_database.this.connection_urls
  description = "APEX/SQL Developer Web URLs — NOT application DSNs."
}

output "atp_connection_strings" {
  value       = oci_database_autonomous_database.this.connection_strings
  sensitive   = true
  description = "DSN map — use .high / .medium / .low keys depending on workload profile."
}

output "atp_wallet_content_base64" {
  value       = oci_database_autonomous_database_wallet.this.content
  sensitive   = true
  description = "Base64 wallet zip. Decode + store in K8s secret (octo-atp-wallet) + Vault."
}
