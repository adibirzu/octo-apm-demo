###############################################################################
# OCI Stack Monitoring — register the ATP DB as a monitored resource so
# the ATP SQL performance + wait events surface in Observability Home.
#
# Stack Monitoring uses a resource-type of `oci_autonomous_database`.
# Agent-less monitoring is enabled via the ATP's built-in metrics; no
# Management Agent needed for DB-level visibility (agent is only needed
# for host-level metrics which ATP abstracts away).
###############################################################################

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
  description = "Optional external identifier — e.g. SQL Developer Web connection alias."
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

  management_agent_id = null

  external_id = var.external_id == "" ? null : var.external_id

  dynamic "properties" {
    for_each = var.properties
    content {
      name  = properties.key
      value = properties.value
    }
  }

  additional_aliases {
    name   = "atp_ocid"
    source = "terraform"
    credential {
      name    = "atp_identity"
      service = "oci_autonomous_database"
      key_id  = var.autonomous_db_id
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
