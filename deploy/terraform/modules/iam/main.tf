###############################################################################
# OCI IAM template — dynamic groups + policies for the platform.
#
# Two dynamic groups:
#   octo-oke-workers     — workers in the OKE cluster (instance principal)
#   octo-builder-host    — remote x86_64 builder VM (OCIR push)
#
# Policies grant only what the platform actually uses. Tightening
# further is an operator choice; loosening would be a regression.
###############################################################################

variable "compartment_id" {
  type = string
}

variable "tenancy_ocid" {
  type = string
}

variable "oke_cluster_compartment_id" {
  type        = string
  description = "Compartment that owns the OKE cluster. Usually same as compartment_id."
  default     = ""
}

variable "builder_vm_compartment_id" {
  type        = string
  description = "Compartment that owns the remote builder VM."
  default     = ""
}

locals {
  oke_compartment_id     = var.oke_cluster_compartment_id != "" ? var.oke_cluster_compartment_id : var.compartment_id
  builder_compartment_id = var.builder_vm_compartment_id != "" ? var.builder_vm_compartment_id : var.compartment_id
}

resource "oci_identity_dynamic_group" "oke_workers" {
  compartment_id = var.tenancy_ocid
  name           = "octo-oke-workers"
  description    = "OKE worker instances for octo-apm-demo"
  matching_rule  = "ALL {instance.compartment.id = '${local.oke_compartment_id}'}"
}

resource "oci_identity_dynamic_group" "builder_host" {
  compartment_id = var.tenancy_ocid
  name           = "octo-builder-host"
  description    = "Remote x86_64 Docker builder for octo-apm-demo"
  matching_rule  = "ALL {instance.compartment.id = '${local.builder_compartment_id}'}"
}

resource "oci_identity_policy" "oke_workers" {
  compartment_id = var.compartment_id
  name           = "octo-oke-workers"
  description    = "Grant OKE workers access to OCIR + Vault + Logging + APM + Monitoring"
  statements = [
    # OCIR pull
    "Allow dynamic-group octo-oke-workers to read repos in compartment id ${var.compartment_id}",

    # Vault secrets (used via Secrets Store CSI)
    "Allow dynamic-group octo-oke-workers to read secret-family in compartment id ${var.compartment_id}",

    # Object Storage for wallet + artifacts (read-only)
    "Allow dynamic-group octo-oke-workers to read objects in compartment id ${var.compartment_id}",

    # OCI Logging — ingest app logs via logging-ingestion SDK
    "Allow dynamic-group octo-oke-workers to use log-content in compartment id ${var.compartment_id}",

    # OCI APM — push traces / RUM
    "Allow dynamic-group octo-oke-workers to use apm-domains in compartment id ${var.compartment_id}",

    # OCI Monitoring — publish custom metrics
    "Allow dynamic-group octo-oke-workers to use metrics in compartment id ${var.compartment_id} where target.metrics.namespace = 'octo_drone_shop'",

    # Stack Monitoring — enrich monitored resources
    "Allow dynamic-group octo-oke-workers to use stack-monitoring-resources in compartment id ${var.compartment_id}",

    # GenAI — AI assistant
    "Allow dynamic-group octo-oke-workers to use generative-ai-family in compartment id ${var.compartment_id}",

    # Events — emit cross-service events
    "Allow dynamic-group octo-oke-workers to use ons-topics in compartment id ${var.compartment_id}",
  ]
}

resource "oci_identity_policy" "builder_host" {
  compartment_id = var.compartment_id
  name           = "octo-builder-host"
  description    = "Grant builder VM push rights to OCIR"
  statements = [
    "Allow dynamic-group octo-builder-host to manage repos in compartment id ${var.compartment_id}",
    "Allow dynamic-group octo-builder-host to read objects in compartment id ${var.compartment_id}",
  ]
}

output "dynamic_groups" {
  value = {
    oke_workers_id  = oci_identity_dynamic_group.oke_workers.id
    builder_host_id = oci_identity_dynamic_group.builder_host.id
  }
}

output "policy_ids" {
  value = {
    oke_workers  = oci_identity_policy.oke_workers.id
    builder_host = oci_identity_policy.builder_host.id
  }
}
