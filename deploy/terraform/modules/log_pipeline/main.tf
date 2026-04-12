###############################################################################
# Log pipeline: route a WAF log group into OCI Log Analytics via a Service
# Connector. One module instance per source (WAF, Shop app, CRM app, …).
###############################################################################

terraform {
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
  type = string
}

variable "source_log_group_id" {
  type        = string
  description = "OCI Logging log group OCID (source)."
}

variable "source_log_id" {
  type        = string
  description = "OCI Logging log OCID within the source log group."
}

variable "la_namespace" {
  type = string
}

variable "la_log_group_id" {
  type        = string
  description = "OCI Log Analytics log group OCID (destination)."
}

variable "la_entity_id" {
  type        = string
  default     = ""
  description = "Optional Log Analytics entity to associate logs with."
}

variable "la_source_name" {
  type        = string
  description = "LA source name that parses the incoming payload (e.g. octo-waf, octo-shop-v2)."
}

resource "oci_sch_service_connector" "this" {
  compartment_id = var.compartment_id
  display_name   = var.display_name
  description    = "Route ${var.display_name} logs into Log Analytics."

  source {
    kind = "logging"
    log_sources {
      compartment_id = var.compartment_id
      log_group_id   = var.source_log_group_id
      log_id         = var.source_log_id
    }
  }

  target {
    kind            = "loganalytics"
    log_group_id    = var.la_log_group_id
    log_source_name = var.la_source_name
  }

  freeform_tags = {
    "octo-demo" = "true"
  }
}

output "service_connector_id" {
  value = oci_sch_service_connector.this.id
}
