###############################################################################
# OCI Logging resources for octo-apm-demo.
#
# Creates the Log Group + Custom Logs the app writes to via the OCI
# Logging SDK (server/observability/logging_sdk.py). Downstream the
# `log_pipeline` module routes these into Log Analytics so dashboards
# can correlate across services.
#
# Outputs are the OCIDs that the app consumes via env vars:
#   OCI_LOG_GROUP_ID          -> log_group_id
#   OCI_LOG_ID                -> log_app_id
#   OCI_LOG_CHAOS_AUDIT_ID    -> log_chaos_audit_id
#   OCI_LOG_SECURITY_ID       -> log_security_id
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

variable "log_group_display_name" {
  type    = string
  default = "octo-apm-demo"
}

variable "retention_duration" {
  type    = number
  default = 30
  validation {
    condition     = var.retention_duration >= 1 && var.retention_duration <= 180
    error_message = "retention_duration must be 1-180 days."
  }
}

resource "oci_logging_log_group" "this" {
  compartment_id = var.compartment_id
  display_name   = var.log_group_display_name
  description    = "Log Group for octo-apm-demo application + chaos audit logs"

  freeform_tags = {
    "project" = "octo-apm-demo"
  }
}

resource "oci_logging_log" "app" {
  display_name       = "octo-app"
  log_group_id       = oci_logging_log_group.this.id
  log_type           = "CUSTOM"
  is_enabled         = true
  retention_duration = var.retention_duration
}

resource "oci_logging_log" "chaos_audit" {
  display_name       = "octo-chaos-audit"
  log_group_id       = oci_logging_log_group.this.id
  log_type           = "CUSTOM"
  is_enabled         = true
  retention_duration = var.retention_duration
}

resource "oci_logging_log" "security" {
  display_name       = "octo-security"
  log_group_id       = oci_logging_log_group.this.id
  log_type           = "CUSTOM"
  is_enabled         = true
  retention_duration = var.retention_duration
}

output "log_group_id" {
  value       = oci_logging_log_group.this.id
  description = "OCI_LOG_GROUP_ID for app Logging SDK init."
}

output "log_app_id" {
  value       = oci_logging_log.app.id
  description = "OCI_LOG_ID for app logs."
}

output "log_chaos_audit_id" {
  value       = oci_logging_log.chaos_audit.id
  description = "OCI_LOG_CHAOS_AUDIT_ID for chaos apply/clear audit records."
}

output "log_security_id" {
  value       = oci_logging_log.security.id
  description = "OCI_LOG_SECURITY_ID for auth + WAF app-level events."
}
