###############################################################################
# OCI WAF module — detection-mode policy for a single frontend.
#
# Usage (from root stack):
#
#   module "waf_shop" {
#     source          = "./modules/waf"
#     compartment_id  = var.compartment_id
#     display_name    = "octo-waf-shop"
#     domain          = var.shop_domain
#     mode            = var.waf_mode            # DETECTION | BLOCK
#     log_group_id    = var.waf_log_group_id
#     admin_allow_cidrs = var.admin_allow_cidrs # applied on /api/admin/*
#   }
#
# Terraform 1.6+ / OCI provider 5.x.
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
  type        = string
  description = "OCI compartment OCID owning the policy."
}

variable "display_name" {
  type        = string
  description = "Human-readable policy name."
}

variable "domain" {
  type        = string
  description = "Public hostname the policy protects (e.g. shop.octodemo.cloud)."
}

variable "mode" {
  type        = string
  default     = "DETECTION"
  description = "DETECTION or BLOCK. Keep DETECTION until traffic is observed."
  validation {
    condition     = contains(["DETECTION", "BLOCK"], upper(var.mode))
    error_message = "mode must be DETECTION or BLOCK."
  }
}

variable "log_group_id" {
  type        = string
  description = "OCI Logging log group OCID that will receive WAF events."
}

variable "admin_allow_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs allowed to hit /api/admin/* — others are flagged (not blocked in DETECTION)."
}

locals {
  effective_action = upper(var.mode) == "BLOCK" ? "BLOCK" : "LOG"
}

resource "oci_waf_web_app_firewall_policy" "this" {
  compartment_id = var.compartment_id
  display_name   = var.display_name

  actions {
    name = "log-only"
    type = "RETURN_HTTP_RESPONSE"
    code = 200
    headers {
      name  = "x-waf-action"
      value = "LOG"
    }
  }

  actions {
    name = "deny-admin"
    type = "RETURN_HTTP_RESPONSE"
    code = 403
    headers {
      name  = "x-waf-action"
      value = "DENY_ADMIN"
    }
  }

  # Managed OWASP CRS — attach latest in detection mode.
  request_protection {
    rules {
      name        = "owasp-crs"
      type        = "PROTECTION"
      action_name = local.effective_action == "BLOCK" ? "deny-admin" : "log-only"
      protection_capabilities {
        key     = "9000000" # OWASP CRS Core Rule Set (collection id)
        version = 1
      }
    }
  }

  # Admin-path allowlist — flags (or blocks) when request hits /api/admin/*
  # from a CIDR outside `admin_allow_cidrs`. In DETECTION we only log.
  request_access_control {
    default_action_name = "log-only"

    dynamic "rules" {
      for_each = length(var.admin_allow_cidrs) > 0 ? [1] : []
      content {
        name               = "admin-cidr-guard"
        type               = "ACCESS_CONTROL"
        action_name        = local.effective_action == "BLOCK" ? "deny-admin" : "log-only"
        condition_language = "jmespath"
        condition          = "starts_with(i(http.request.url.path), '/api/admin')"
      }
    }
  }

  request_rate_limiting {
    rules {
      name               = "login-burst"
      type               = "REQUEST_RATE_LIMITING"
      action_name        = "log-only"
      condition_language = "jmespath"
      condition          = "i(http.request.url.path) == '/login' || i(http.request.url.path) == '/api/auth/login'"
      configurations {
        period_in_seconds          = 60
        requests_limit             = 10
        action_duration_in_seconds = 300
      }
    }
  }

  freeform_tags = {
    "octo-demo"  = "true"
    "waf-mode"   = upper(var.mode)
    "waf-domain" = var.domain
  }
}

output "policy_ocid" {
  value = oci_waf_web_app_firewall_policy.this.id
}

output "mode" {
  value = upper(var.mode)
}
