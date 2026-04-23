###############################################################################
# OCI API Gateway module — edge for octo-apm-demo.
#
# Fronts shop + CRM with route-aware policies:
#   - /api/public/*   — no auth, 100 req/min per source IP
#   - /api/partner/*  — API key in X-API-Key, 1000 req/min per key
#   - /api/admin/*    — IDCS bearer, 100 req/min per subject
#
# Access logs + execution logs land in a dedicated log group; the
# la_pipeline_app_logs pattern in deploy/terraform/main.tf fans them
# into Log Analytics under a new source (octo-edge-gateway-json).
###############################################################################

variable "compartment_id" {
  type        = string
  description = "Compartment OCID that owns the API Gateway + deployment."
}

variable "display_name" {
  type    = string
  default = "octo-edge-gateway"
}

variable "endpoint_type" {
  type    = string
  default = "PUBLIC"
}

variable "gateway_subnet_id" {
  type        = string
  description = "Subnet OCID for the gateway's network interface."
}

variable "shop_backend_url" {
  type        = string
  description = "Upstream URL for /api/* shop traffic (e.g. https://drone.${DNS_DOMAIN} or an LB OCID)."
}

variable "crm_backend_url" {
  type        = string
  description = "Upstream URL for /api/crm/* traffic."
}

variable "log_group_id" {
  type        = string
  description = "OCI Logging log group OCID for API Gateway access + execution logs."
}

variable "public_rate_limit_rpm" {
  type    = number
  default = 100
}

variable "partner_rate_limit_rpm" {
  type    = number
  default = 1000
}

variable "admin_rate_limit_rpm" {
  type    = number
  default = 100
}

variable "partner_auth_function_id" {
  type        = string
  default     = ""
  description = "OCI Functions OCID of the authorizer that validates X-API-Key for /api/partner/*. Empty = no custom auth block emitted (rate-limit only)."
}

variable "idcs_jwks_uri" {
  type        = string
  description = "IDCS JWKS endpoint — used by the admin route's jwt_authentication policy."
  default     = ""
}

variable "idcs_issuer" {
  type        = string
  description = "IDCS issuer URL for JWT validation."
  default     = ""
}

variable "freeform_tags" {
  type    = map(string)
  default = {}
}
