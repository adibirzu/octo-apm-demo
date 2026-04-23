###############################################################################
# OCI Vault for octo-apm-demo.
#
# One Vault + AES-256 master key, then one VaultSecret per entry consumed
# by the app. The K8s Secret Store CSI driver reads these via the
# `octo-oke-workers` dynamic group (see ../iam).
#
# Secret values come from root variables — operators either pass them via
# tfvars (preferred for CI/CD) or environment (`TF_VAR_*`). Defaults are
# empty; empty strings cause the resource to be skipped so partial setups
# can bootstrap incrementally.
###############################################################################

variable "compartment_id" {
  type = string
}

variable "vault_display_name" {
  type    = string
  default = "octo-apm-vault"
}

variable "vault_type" {
  type    = string
  default = "DEFAULT"
  validation {
    condition     = contains(["DEFAULT", "VIRTUAL_PRIVATE"], var.vault_type)
    error_message = "vault_type must be DEFAULT or VIRTUAL_PRIVATE."
  }
}

variable "key_display_name" {
  type    = string
  default = "octo-apm-master-key"
}

# Map of secret_name -> plaintext value. Anything blank is skipped.
variable "secrets" {
  type = map(string)
  default = {
    INTERNAL_SERVICE_KEY     = ""
    AUTH_TOKEN_SECRET        = ""
    APP_SECRET_KEY           = ""
    BOOTSTRAP_ADMIN_PASSWORD = ""
    ORACLE_PASSWORD          = ""
    ORACLE_WALLET_PASSWORD   = ""
    OCI_APM_PRIVATE_DATAKEY  = ""
    OCI_APM_PUBLIC_DATAKEY   = ""
    IDCS_CLIENT_ID           = ""
    IDCS_CLIENT_SECRET       = ""
    SLACK_WEBHOOK_URL        = ""
    STRIPE_API_KEY           = ""
    STRIPE_WEBHOOK_SECRET    = ""
    PAYPAL_CLIENT_ID         = ""
    PAYPAL_CLIENT_SECRET     = ""
  }
  sensitive = true
}

resource "oci_kms_vault" "this" {
  compartment_id = var.compartment_id
  display_name   = var.vault_display_name
  vault_type     = var.vault_type

  freeform_tags = {
    "project" = "octo-apm-demo"
  }
}

resource "oci_kms_key" "master" {
  compartment_id      = var.compartment_id
  display_name        = var.key_display_name
  management_endpoint = oci_kms_vault.this.management_endpoint

  key_shape {
    algorithm = "AES"
    length    = 32
  }

  protection_mode = "SOFTWARE"

  freeform_tags = {
    "project" = "octo-apm-demo"
  }
}

locals {
  nonempty_secrets = {
    for k, v in var.secrets : k => v if trimspace(v) != ""
  }
}

resource "oci_vault_secret" "this" {
  for_each       = local.nonempty_secrets
  compartment_id = var.compartment_id
  vault_id       = oci_kms_vault.this.id
  key_id         = oci_kms_key.master.id
  secret_name    = each.key
  description    = "octo-apm-demo secret ${each.key}"

  secret_content {
    content_type = "BASE64"
    content      = base64encode(each.value)
  }

  freeform_tags = {
    "project" = "octo-apm-demo"
  }
}

output "vault_id" {
  value = oci_kms_vault.this.id
}

output "vault_management_endpoint" {
  value = oci_kms_vault.this.management_endpoint
}

output "master_key_id" {
  value = oci_kms_key.master.id
}

output "secret_ids" {
  value       = { for k, s in oci_vault_secret.this : k => s.id }
  description = "Map of secret name → secret OCID — feed to SecretProviderClass."
}
