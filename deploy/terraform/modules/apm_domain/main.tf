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
  required_version = ">= 1.5.0"
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

# RUM Web Application registration — OCI provider does NOT yet expose a
# first-class resource for RUM web app creation (config_type "WEB_APPLICATION"
# is rejected by the schema; valid values are AGENT/APDEX/MACS_APM_EXTENSION/
# METRIC_GROUP/OPTIONS/SPAN_FILTER). Register the RUM web app via the OCI
# Console under APM → RUM → Web Applications after this module runs, using
# the APM domain + public data key outputs below. The page-embedded RUM SDK
# needs only the public data key + RUM endpoint; the web-app OCID is a
# metadata handle that isn't required for beacon ingestion.
#
# When the provider ships a dedicated resource, wire it here.
