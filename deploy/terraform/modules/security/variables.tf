variable "compartment_id" {
  type        = string
  description = "Compartment OCID for security resources"
}

variable "vcn_id" {
  type        = string
  description = "VCN OCID for creating the Quarantine NSG"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for naming resources"
  default     = "octo-apm-demo"
}

variable "subnet_id" {
  type        = string
  description = "Subnet OCID to deploy the Function"
}

variable "log_group_id" {
  type        = string
  description = "Log Group OCID to send Function logs to"
}
