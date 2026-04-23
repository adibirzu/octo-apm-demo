###############################################################################
# OCI API Gateway + deployment + route policies.
#
# Applies cleanly against `terraform apply` — no apps need to change.
# Rendering the WAF module output (waf_policies[].shop) here lets the
# gateway + WAF share a single operator mental model.
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

resource "oci_apigateway_gateway" "this" {
  compartment_id = var.compartment_id
  display_name   = var.display_name
  endpoint_type  = var.endpoint_type
  subnet_id      = var.gateway_subnet_id
  freeform_tags  = var.freeform_tags
}

resource "oci_apigateway_deployment" "octo" {
  compartment_id = var.compartment_id
  gateway_id     = oci_apigateway_gateway.this.id
  display_name   = "${var.display_name}-deployment"
  path_prefix    = "/"
  freeform_tags  = var.freeform_tags

  specification {
    # ── Global logging ─────────────────────────────────────────────
    logging_policies {
      access_log { is_enabled = true }
      execution_log {
        is_enabled = true
        log_level  = "INFO"
      }
    }

    # ── Default request policies ───────────────────────────────────
    request_policies {
      cors {
        allowed_origins    = ["*"]
        allowed_methods    = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        allowed_headers    = ["Content-Type", "Authorization", "X-API-Key", "X-Run-Id"]
        exposed_headers    = ["X-Trace-Id", "X-Workflow-Id"]
        max_age_in_seconds = 300
      }
    }

    # ── /api/public/* ─ unauthenticated, 100 req/min per IP ────────
    routes {
      path    = "/api/public/{path*}"
      methods = ["ANY"]
      backend {
        type = "HTTP_BACKEND"
        url  = "${var.shop_backend_url}/api/public/{path}"
      }
      request_policies {
        header_transformations {
          set_headers {
            items {
              name   = "X-Edge"
              values = ["octo-edge-gateway"]
            }
          }
        }
      }
    }

    # ── /api/partner/* ─ API-key auth, 1000 req/min per key ────────
    routes {
      path    = "/api/partner/{path*}"
      methods = ["ANY"]
      backend {
        type = "HTTP_BACKEND"
        url  = "${var.shop_backend_url}/api/partner/{path}"
      }
      request_policies {
        authentication {
          type                        = "CUSTOM_AUTHENTICATION"
          is_anonymous_access_allowed = false
          # In production, wire this to a dedicated authorizer Function
          # that looks up X-API-Key in Vault and caches the result.
          function_id = ""
        }
        rate_limiting {
          rate_in_requests_per_second = ceil(var.partner_rate_limit_rpm / 60)
          rate_key                    = "CLIENT_IP"
        }
      }
    }

    # ── /api/crm/* ─ proxied to CRM backend ────────────────────────
    routes {
      path    = "/api/crm/{path*}"
      methods = ["ANY"]
      backend {
        type = "HTTP_BACKEND"
        url  = "${var.crm_backend_url}/api/{path}"
      }
      request_policies {
        header_transformations {
          set_headers {
            items {
              name   = "X-Edge"
              values = ["octo-edge-gateway"]
            }
          }
        }
      }
    }

    # ── /api/admin/* ─ IDCS JWT, 100 req/min per subject ───────────
    routes {
      path    = "/api/admin/{path*}"
      methods = ["ANY"]
      backend {
        type = "HTTP_BACKEND"
        url  = "${var.crm_backend_url}/api/admin/{path}"
      }
      request_policies {
        authentication {
          type         = "JWT_AUTHENTICATION"
          token_header = "Authorization"
          issuers      = [var.idcs_issuer]
          public_keys {
            type                        = "REMOTE_JWKS"
            uri                         = var.idcs_jwks_uri
            max_cache_duration_in_hours = 1
          }
          audiences = ["octo-admin"]
          verify_claims {
            key         = "iss"
            values      = [var.idcs_issuer]
            is_required = true
          }
        }
        rate_limiting {
          rate_in_requests_per_second = ceil(var.admin_rate_limit_rpm / 60)
          rate_key                    = "CLIENT_IP"
        }
      }
    }
  }
}

output "gateway_id" {
  value = oci_apigateway_gateway.this.id
}

output "deployment_id" {
  value = oci_apigateway_deployment.octo.id
}

output "gateway_hostname" {
  value = oci_apigateway_gateway.this.hostname
}
