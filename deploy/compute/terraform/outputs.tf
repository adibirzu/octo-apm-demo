output "instance_ips" {
  value = {
    shop = {
      public_ip  = ""
      private_ip = try(oci_core_instance.app["shop"].private_ip, "")
      hostname   = local.shop_hostname
    }
    crm = {
      public_ip  = ""
      private_ip = try(oci_core_instance.app["crm"].private_ip, "")
      hostname   = local.crm_hostname
    }
  }
}

output "instance_ids" {
  value = {
    shop = oci_core_instance.app["shop"].id
    crm  = oci_core_instance.app["crm"].id
  }
  description = "Private Compute instance OCIDs for OCI Run Command based app promotion."
}

output "deployment_compartment_id" {
  value       = var.compartment_id
  description = "Compartment OCID used by post-deployment OCI CLI helpers."
}

output "network" {
  value = {
    vcn_id           = local.vcn_id
    lb_subnet_id     = local.lb_subnet_id
    app_subnet_id    = local.app_subnet_id
    db_subnet_id     = local.db_subnet_id
    app_nsg_id       = oci_core_network_security_group.app.id
    lb_nsg_id        = oci_core_network_security_group.lb.id
    db_nsg_id        = oci_core_network_security_group.db.id
    service_gateway  = local.service_gateway_enabled ? oci_core_service_gateway.this[0].id : ""
    nat_gateway      = var.create_network ? oci_core_nat_gateway.this[0].id : ""
    internet_gateway = var.create_network ? oci_core_internet_gateway.this[0].id : ""
  }
}

output "load_balancer" {
  value = var.create_load_balancer ? {
    id         = oci_load_balancer_load_balancer.public[0].id
    ip_address = length(oci_load_balancer_load_balancer.public[0].ip_address_details) > 0 ? oci_load_balancer_load_balancer.public[0].ip_address_details[0].ip_address : ""
    hostnames = {
      shop = local.shop_hostname
      crm  = local.crm_hostname
    }
    listeners = {
      http  = var.enable_lb_http
      https = var.enable_lb_https
    }
    waf_id = var.enable_waf ? try(oci_waf_web_app_firewall.lb[0].id, "") : ""
  } : null
}

output "dns_records" {
  value = var.create_dns_records ? {
    for name, record in oci_dns_rrset.app :
    name => {
      fqdn = record.domain
      type = record.rtype
      ttl  = var.dns_record_ttl
    }
  } : {}
}

output "instance_image" {
  value = {
    image_ocid               = local.instance_image_ocid
    operating_system         = var.instance_operating_system
    operating_system_version = var.instance_operating_system_version
  }
}

output "atp" {
  value = {
    id                  = module.atp.atp_id
    db_name             = module.atp.atp_db_name
    service_console_url = module.atp.atp_service_console_url
    private_endpoint    = module.atp.atp_private_endpoint
  }
}

output "atp_wallet_content_base64" {
  value       = module.atp.atp_wallet_content_base64
  sensitive   = true
  description = "Decode locally and copy wallet.zip contents to /opt/octo/wallet on both instances."
}

output "logging" {
  value = {
    log_group_id       = module.logging.log_group_id
    app_log_id         = module.logging.log_app_id
    chaos_audit_log_id = module.logging.log_chaos_audit_id
    security_log_id    = module.logging.log_security_id
    os_log_id          = oci_logging_log.os.id
    app_stdout_log_id  = oci_logging_log.app_stdout.id
    waf_log_id         = var.create_load_balancer && var.enable_waf && var.enable_waf_logging ? try(oci_logging_log.waf[0].id, "") : ""
  }
}

output "apm" {
  value = var.create_apm_domain ? {
    domain_id    = module.apm_domain[0].apm_domain_id
    endpoint     = module.apm_domain[0].apm_data_upload_endpoint
    rum_endpoint = module.apm_domain[0].rum_endpoint
  } : null
}

output "apm_public_datakey" {
  value     = var.create_apm_domain ? module.apm_domain[0].apm_public_datakey : ""
  sensitive = true
}

output "apm_private_datakey" {
  value     = var.create_apm_domain ? module.apm_domain[0].apm_private_datakey : ""
  sensitive = true
}

output "stack_monitoring" {
  value = {
    standard_enabled            = var.enable_stack_monitoring_standard
    configs_enabled             = var.enable_stack_monitoring_configs
    agent_plugin_enabled        = var.enable_stack_monitoring_agent_plugin
    agent_ids                   = local.stack_monitoring_agent_ids
    plugin_resource_ids         = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_agent_plugin ? { for role, agent in oci_management_agent_management_agent.stack_monitoring_plugin : role => agent.id } : {}
    host_registration_enabled   = var.enable_stack_monitoring_host_registration
    host_resource_ids           = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_host_registration ? { for role, resource in oci_stack_monitoring_monitored_resource.host : role => resource.id } : {}
    atp_registration_enabled    = var.enable_stack_monitoring_atp_registration
    atp_resource_id             = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_atp_registration ? try(module.stack_monitoring_atp[0].monitored_resource_id, "") : ""
    atp_management_agent_id     = var.enable_stack_monitoring_standard ? local.stack_monitoring_atp_management_agent_id : ""
    host_auto_promote_config_id = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_configs ? try(oci_stack_monitoring_config.host_auto_promote[0].id, "") : ""
    database_management_enabled = var.enable_database_management
    operations_insights_enabled = var.enable_operations_insights
    db_management_endpoint_id   = var.enable_database_management_private_endpoint ? oci_database_management_db_management_private_endpoint.this[0].id : ""
    opsi_endpoint_id            = var.enable_operations_insights_private_endpoint ? oci_opsi_operations_insights_private_endpoint.this[0].id : ""
  }
}

output "crm_admin_username" {
  value       = "admin"
  description = "Bootstrap CRM local admin username. The password is the sensitive bootstrap_admin_password variable supplied by the operator."
}

output "log_analytics" {
  value = {
    enabled            = var.enable_log_analytics
    connectors_enabled = var.enable_log_analytics_connectors
    namespace          = local.effective_log_analytics_namespace
    log_group_id       = local.log_analytics_log_group_id
    connectors = var.enable_log_analytics && var.enable_log_analytics_connectors ? {
      app       = oci_sch_service_connector.log_analytics_app[0].id
      os        = oci_sch_service_connector.log_analytics_os[0].id
      container = oci_sch_service_connector.log_analytics_container[0].id
      waf       = var.create_load_balancer && var.enable_waf && var.enable_waf_logging ? try(oci_sch_service_connector.log_analytics_waf[0].id, "") : ""
    } : {}
  }
}

output "runtime_env_hints" {
  value = {
    shop = {
      app_name            = "octo-drone-shop"
      otel_service_name   = "octo-drone-shop"
      service_instance_id = "${var.name_prefix}-shop"
      service_crm_url     = try("http://${oci_core_instance.app["crm"].private_ip}:8080", "")
      shop_public_url     = local.shop_public_url
      crm_public_url      = local.crm_public_url
      cors_allowed_origins = join(",", [
        local.shop_public_url,
        local.crm_public_url,
      ])
    }
    crm = {
      app_name            = "enterprise-crm-portal"
      otel_service_name   = "enterprise-crm-portal"
      service_instance_id = "${var.name_prefix}-crm"
      shop_public_url     = local.shop_public_url
      crm_base_url        = local.crm_public_url
      service_shop_url    = try("http://${oci_core_instance.app["shop"].private_ip}:8080", "")
      cors_allowed_origins = join(",", [
        local.shop_public_url,
        local.crm_public_url,
      ])
    }
  }
}
