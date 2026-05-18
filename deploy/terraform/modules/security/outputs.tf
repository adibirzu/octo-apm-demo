output "quarantine_nsg_id" {
  value       = oci_core_network_security_group.quarantine.id
  description = "The OCID of the Quarantine NSG."
}

output "remediation_topic_id" {
  value       = oci_ons_notification_topic.remediation.topic_id
  description = "The OCID of the Notification Topic that triggers the remediation function."
}
