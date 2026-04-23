###############################################################################
# OCI Stack Monitoring — register the ATP DB as a monitored resource so
# the ATP SQL performance + wait events surface in Observability Home.
#
# Stack Monitoring's registration for Autonomous DBs is deliberately
# minimal from Terraform's side: OCI already knows the ATP exists (by
# `external_id` = autonomous_database OCID) and auto-collects the
# built-in metric stream. This module is the declarative hand-shake that
# says "surface this DB in Stack Monitoring dashboards".
#
# NOTE: The richer agent-led monitoring (custom SQL capture, host-level
# resources, alarms wired to DB sessions) requires an OCI Management
# Agent registered with `oci_stack_monitoring_monitored_resources_list_member`.
# That is out of scope for this module — ATP's built-in signal is enough
# for the default demo.
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

variable "monitored_resource_name" {
  type    = string
  default = "octo-apm-demo-atp"
}

variable "autonomous_db_id" {
  type        = string
  description = "ATP OCID to register (output of modules/atp)."
}

variable "external_id" {
  type        = string
  default     = ""
  description = "Optional external identifier — defaults to the ATP OCID."
}

variable "properties" {
  type        = map(string)
  default     = {}
  description = "Additional properties surfaced in Stack Monitoring UI (e.g. environment=prod)."
}

resource "oci_stack_monitoring_monitored_resource" "atp" {
  compartment_id = var.compartment_id
  name           = var.monitored_resource_name
  type           = "oci_autonomous_database"
  display_name   = var.monitored_resource_name
  external_id    = var.external_id == "" ? var.autonomous_db_id : var.external_id

  dynamic "properties" {
    for_each = var.properties
    content {
      name  = properties.key
      value = properties.value
    }
  }

  freeform_tags = {
    "project" = "octo-apm-demo"
    "type"    = "oci_autonomous_database"
  }
}

output "monitored_resource_id" {
  value       = oci_stack_monitoring_monitored_resource.atp.id
  description = "OCID of the Stack Monitoring monitored resource for the ATP."
}
