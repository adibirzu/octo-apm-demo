###############################################################################
# APM Domain + RUM Web Application.
#
# This module is tenancy-portable: every OCID is sourced from module inputs,
# no hardcoded references. Apply once per tenancy; re-apply is idempotent.
#
# Outputs expose the apm_endpoint + data keys expected by the app's
# OTEL exporter and browser RUM SDK.
###############################################################################

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

resource "oci_apm_apm_domain" "this" {
  compartment_id = var.compartment_id
  display_name   = var.display_name
  description    = var.description
  is_free_tier   = var.is_free_tier
  freeform_tags  = var.freeform_tags
}

# Pull the public + private data keys automatically generated with the domain.
data "oci_apm_data_keys" "public" {
  apm_domain_id = oci_apm_apm_domain.this.id
  data_key_type = "PUBLIC"
}

data "oci_apm_data_keys" "private" {
  apm_domain_id = oci_apm_apm_domain.this.id
  data_key_type = "PRIVATE"
}

# Register a RUM Web Application config (optional).
resource "oci_apm_config_config" "rum_web_app" {
  count         = var.create_rum_web_app ? 1 : 0
  apm_domain_id = oci_apm_apm_domain.this.id
  config_type   = "WEB_APPLICATION"
  display_name  = var.web_application_display_name
  freeform_tags = var.freeform_tags
}
