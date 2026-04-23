###############################################################################
# OCI Object Storage buckets for octo-apm-demo.
#
# Creates three buckets:
#   - chaos_state  — JSON blob of the currently-applied chaos scenario
#   - wallet       — ATP wallet zip (encrypted at rest)
#   - artifacts    — app uploads / object-pipeline source corpus
#
# All are private (no public access). Lifecycle to be added in a follow-up
# when retention is finalized.
###############################################################################

variable "compartment_id" {
  type = string
}

variable "namespace" {
  type        = string
  description = "Object Storage namespace for the tenancy (same in every compartment). Use `oci os ns get`."
}

variable "chaos_state_bucket_name" {
  type    = string
  default = "octo-chaos-state"
}

variable "wallet_bucket_name" {
  type    = string
  default = "octo-wallet"
}

variable "artifacts_bucket_name" {
  type    = string
  default = "octo-artifacts"
}

variable "versioning" {
  type    = string
  default = "Enabled"
  validation {
    condition     = contains(["Enabled", "Disabled", "Suspended"], var.versioning)
    error_message = "versioning must be Enabled, Disabled, or Suspended."
  }
}

locals {
  common_tags = {
    "project" = "octo-apm-demo"
  }
}

resource "oci_objectstorage_bucket" "chaos_state" {
  compartment_id = var.compartment_id
  namespace      = var.namespace
  name           = var.chaos_state_bucket_name
  access_type    = "NoPublicAccess"
  versioning     = var.versioning
  freeform_tags  = merge(local.common_tags, { "role" = "chaos-state" })
}

resource "oci_objectstorage_bucket" "wallet" {
  compartment_id = var.compartment_id
  namespace      = var.namespace
  name           = var.wallet_bucket_name
  access_type    = "NoPublicAccess"
  versioning     = var.versioning
  freeform_tags  = merge(local.common_tags, { "role" = "atp-wallet" })
}

resource "oci_objectstorage_bucket" "artifacts" {
  compartment_id = var.compartment_id
  namespace      = var.namespace
  name           = var.artifacts_bucket_name
  access_type    = "NoPublicAccess"
  versioning     = var.versioning
  freeform_tags  = merge(local.common_tags, { "role" = "artifacts" })
}

output "chaos_state_bucket" {
  value = oci_objectstorage_bucket.chaos_state.name
}

output "wallet_bucket" {
  value = oci_objectstorage_bucket.wallet.name
}

output "artifacts_bucket" {
  value = oci_objectstorage_bucket.artifacts.name
}
