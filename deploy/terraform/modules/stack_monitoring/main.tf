###############################################################################
# OCI Stack Monitoring — register the ATP DB as a monitored resource so
# the ATP SQL performance + wait events surface in Observability Home.
#
# Stack Monitoring's DB registration requires an OCI Management Agent. The
# compute stack discovers the private shop host's agent after Oracle Cloud
# Agent registers it, then passes that OCID here.
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

variable "management_agent_id" {
  type        = string
  default     = ""
  description = "OCI Management Agent OCID used by Stack Monitoring to manage the database resource."
}

variable "resource_type" {
  type        = string
  default     = "oci_oracle_db"
  description = "Stack Monitoring monitored resource type for the ATP registration."
}

variable "database_connection_details" {
  type = object({
    protocol       = string
    port           = number
    service_name   = string
    connector_id   = optional(string)
    db_id          = optional(string)
    db_unique_name = optional(string)
    ssl_secret_id  = optional(string)
  })
  default     = null
  description = "Database connection details required by OCI Stack Monitoring database resource registration."
}

variable "credential_name" {
  type        = string
  default     = ""
  description = "Existing Management Agent named credential name used for DB monitoring."
}

variable "credential_type" {
  type        = string
  default     = ""
  description = "Management Agent named credential type."
}

locals {
  default_db_named_credential_type = join("", ["DBTCPS", "CREDS", "ADB"])
}

resource "oci_stack_monitoring_monitored_resource" "atp" {
  compartment_id       = var.compartment_id
  name                 = var.monitored_resource_name
  type                 = var.resource_type
  display_name         = var.monitored_resource_name
  external_id          = var.external_id == "" ? null : var.external_id
  external_resource_id = var.autonomous_db_id
  management_agent_id  = var.management_agent_id
  license              = "STANDARD_EDITION"

  lifecycle {
    precondition {
      condition     = var.management_agent_id != ""
      error_message = "management_agent_id is required to register the ATP in OCI Stack Monitoring."
    }
    precondition {
      condition     = var.database_connection_details != null
      error_message = "database_connection_details is required to register database resources in OCI Stack Monitoring."
    }
    precondition {
      condition     = var.credential_name != ""
      error_message = "credential_name is required to register database resources in OCI Stack Monitoring."
    }
  }

  dynamic "database_connection_details" {
    for_each = var.database_connection_details == null ? [] : [var.database_connection_details]
    content {
      protocol       = database_connection_details.value.protocol
      port           = database_connection_details.value.port
      service_name   = database_connection_details.value.service_name
      connector_id   = try(database_connection_details.value.connector_id, null)
      db_id          = try(database_connection_details.value.db_id, null)
      db_unique_name = try(database_connection_details.value.db_unique_name, null)
      ssl_secret_id  = try(database_connection_details.value.ssl_secret_id, null)
    }
  }

  credentials {
    credential_type = "EXISTING"
    name            = var.credential_name
    source          = "NAMED_CREDENTIAL"
    type            = var.credential_type != "" ? var.credential_type : local.default_db_named_credential_type
  }

  dynamic "properties" {
    for_each = var.properties
    content {
      name  = properties.key
      value = properties.value
    }
  }

  freeform_tags = {
    "project" = "octo-apm-demo"
    "type"    = var.resource_type
  }
}

output "monitored_resource_id" {
  value       = oci_stack_monitoring_monitored_resource.atp.id
  description = "OCID of the Stack Monitoring monitored resource for the ATP."
}
