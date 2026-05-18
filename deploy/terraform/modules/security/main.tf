terraform {
  required_version = ">= 1.5.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.0.0"
    }
  }
}

# 1. Quarantine Network Security Group (Empty = Drop All Traffic)
resource "oci_core_network_security_group" "quarantine" {
  compartment_id = var.compartment_id
  vcn_id         = var.vcn_id
  display_name   = "${var.name_prefix}-quarantine-nsg"
  freeform_tags = {
    project = "octo-apm-demo"
  }
}

# 2. Notification Topic for Alarms
resource "oci_ons_notification_topic" "remediation" {
  compartment_id = var.compartment_id
  name           = "${var.name_prefix}-auto-remediation-topic"
  description    = "Topic to receive Log Analytics Alarms and trigger the auto-remediation function."
  freeform_tags = {
    project = "octo-apm-demo"
  }
}

# 3. Dynamic Group for the Function to access OCI APIs
resource "oci_identity_dynamic_group" "remediation_fn" {
  compartment_id = var.compartment_id
  name           = "${var.name_prefix}-remediation-fn-dg"
  description    = "Dynamic Group for Auto-Remediation Function"
  matching_rule  = "ALL {resource.type = 'fnfunc', resource.compartment.id = '${var.compartment_id}'}"

  # Ignore matching_rule errors in some tenancies due to eventual consistency
  lifecycle {
    ignore_changes = [matching_rule]
  }
}

# 4. IAM Policy for the Function
resource "oci_identity_policy" "remediation_fn" {
  compartment_id = var.compartment_id
  name           = "${var.name_prefix}-remediation-fn-policy"
  description    = "Allows the remediation function to manage VNICs and NSGs."
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.remediation_fn.name} to manage vnics in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.remediation_fn.name} to use network-security-groups in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.remediation_fn.name} to read instances in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.remediation_fn.name} to use generative-ai-family in compartment id ${var.compartment_id}"
  ]
}
