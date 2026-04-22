###############################################################################
# KG-029 — Alarm: API Gateway 5xx rate > threshold in any 5m window.
# Fires the `octo-alarms` Notifications topic which the remediator
# listens on.
###############################################################################

variable "notifications_topic_ocid" {
  type        = string
  default     = ""
  description = "Topic OCID alarm fires into. Empty = alarm disabled."
}

variable "api_gateway_5xx_threshold_per_5m" {
  type    = number
  default = 50
}

resource "oci_monitoring_alarm" "api_gateway_5xx" {
  count = var.notifications_topic_ocid == "" ? 0 : 1

  compartment_id        = var.compartment_id
  display_name          = "octo-edge-gateway 5xx burst"
  metric_compartment_id = var.compartment_id
  namespace             = "oci_apigateway"
  query                 = "HttpResponses[5m]{responseStatusCodeCategory = \"5xx\"}.sum() > ${var.api_gateway_5xx_threshold_per_5m}"
  severity              = "CRITICAL"
  is_enabled            = true
  destinations          = [var.notifications_topic_ocid]

  body = "API Gateway ${var.display_name} returned ≥ ${var.api_gateway_5xx_threshold_per_5m} 5xx responses in 5m. Run-id: {annotation.run_id}. Trace exemplar: {annotation.trace_exemplar}."

  message_format = "PRETTY_JSON"
  repeat_notification_duration = "PT15M"
}
