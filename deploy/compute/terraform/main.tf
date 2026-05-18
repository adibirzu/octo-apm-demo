locals {
  tags = merge({
    project    = "octo-apm-demo"
    surface    = "compute"
    managed-by = "terraform"
  }, var.tags)

  shop_hostname   = var.shop_hostname != "" ? var.shop_hostname : "shop.${var.dns_domain}"
  crm_hostname    = var.crm_hostname != "" ? var.crm_hostname : "crm.${var.dns_domain}"
  shop_public_url = var.enable_lb_https ? "https://${local.shop_hostname}" : "http://${local.shop_hostname}"
  crm_public_url  = var.enable_lb_https ? "https://${local.crm_hostname}" : "http://${local.crm_hostname}"
  name_prefix_api = replace(var.name_prefix, "-", "_")
  shop_app_image = var.shop_app_image != "" ? var.shop_app_image : (
    var.app_image_build_enabled ? "localhost/octo-drone-shop:${var.image_tag}" : "octo-drone-shop:${var.image_tag}"
  )
  crm_app_image = var.crm_app_image != "" ? var.crm_app_image : (
    var.app_image_build_enabled ? "localhost/enterprise-crm-portal:${var.image_tag}" : "enterprise-crm-portal:${var.image_tag}"
  )

  instances = {
    shop = {
      hostname         = local.shop_hostname
      backend_set_name = "shop"
      app_image        = local.shop_app_image
      app_name         = "octo-drone-shop"
      otel_service     = "octo-drone-shop"
      dockerfile       = "shop/Dockerfile"
    }
    crm = {
      hostname         = local.crm_hostname
      backend_set_name = "crm"
      app_image        = local.crm_app_image
      app_name         = "enterprise-crm-portal"
      otel_service     = "enterprise-crm-portal"
      dockerfile       = "crm/Dockerfile"
    }
  }

  compute_bootstrap_root = fileexists("${path.module}/bootstrap/install.sh") ? "${path.module}/bootstrap" : abspath("${path.module}/..")
  compute_bootstrap_file_names = [
    "install.sh",
    "app-compose.yml",
    "runtime.env.template",
    "synthetic-users-job.sh",
    "nginx/app.conf.template",
    "systemd/octo-compute.service",
    "systemd/octo-java-apm.service",
    "systemd/octo-podman.service",
    "systemd/octo-synthetic-users.service",
    "systemd/octo-synthetic-users.timer",
    "systemd/octo-workflow-gateway.service",
    "systemd/octo-tetragon.service",
  ]
  compute_bootstrap_files = {
    for rel_path in local.compute_bootstrap_file_names :
    rel_path => {
      path        = "/opt/octo/deploy/compute/${rel_path}"
      permissions = endswith(rel_path, ".sh") ? "0755" : "0644"
      content     = filebase64("${local.compute_bootstrap_root}/${rel_path}")
    }
  }

  existing_lb_subnet_id = var.existing_lb_subnet_id != "" ? var.existing_lb_subnet_id : var.existing_public_subnet_id

  vcn_id        = var.create_network ? oci_core_vcn.this[0].id : var.existing_vcn_id
  lb_subnet_id  = var.create_network ? oci_core_subnet.lb_public[0].id : local.existing_lb_subnet_id
  app_subnet_id = var.create_network ? oci_core_subnet.app_private[0].id : var.existing_app_private_subnet_id
  db_subnet_id = var.create_network ? oci_core_subnet.db_private[0].id : (
    var.existing_db_private_subnet_id != "" ? var.existing_db_private_subnet_id : var.existing_app_private_subnet_id
  )

  app_subnet_cidr = var.create_network ? var.app_private_subnet_cidr : var.app_private_cidr
  db_subnet_cidr = var.create_network ? var.db_private_subnet_cidr : (
    var.existing_db_private_cidr != "" ? var.existing_db_private_cidr : var.app_private_cidr
  )

  service_gateway_enabled       = var.create_network && var.create_service_gateway
  create_log_analytics_loggroup = var.enable_log_analytics && var.existing_log_analytics_log_group_id == ""
  effective_log_analytics_namespace = var.enable_log_analytics ? (
    var.log_analytics_namespace != "" ? var.log_analytics_namespace : (
      var.create_log_analytics_namespace ? oci_log_analytics_namespace.this[0].namespace : ""
    )
  ) : ""
  log_analytics_log_group_id = var.enable_log_analytics ? (
    var.existing_log_analytics_log_group_id != "" ? var.existing_log_analytics_log_group_id : oci_log_analytics_log_analytics_log_group.this[0].id
  ) : ""

  instance_image_ocid = var.instance_image_ocid != "" ? var.instance_image_ocid : data.oci_core_images.oracle_linux[0].images[0].id

  apm_endpoint        = var.create_apm_domain ? module.apm_domain[0].apm_data_upload_endpoint : ""
  apm_rum_endpoint    = var.create_apm_domain ? module.apm_domain[0].rum_endpoint : ""
  apm_public_datakey  = var.create_apm_domain ? module.apm_domain[0].apm_public_datakey : ""
  apm_private_datakey = var.create_apm_domain ? module.apm_domain[0].apm_private_datakey : ""
  shop_private_service_url = var.shop_private_service_url != "" ? var.shop_private_service_url : (
    var.create_network ? "http://shop.apps.octocompute.oraclevcn.com:8080" : "http://shop:8080"
  )
  crm_private_service_url = var.crm_private_service_url != "" ? var.crm_private_service_url : (
    var.create_network ? "http://crm.apps.octocompute.oraclevcn.com:8080" : "http://crm:8080"
  )

  runtime_env_values = {
    shop = {
      OCTO_COMPUTE_ROLE              = "shop"
      CONTAINER_RUNTIME              = var.container_runtime
      APP_IMAGE                      = local.shop_app_image
      APP_IMAGE_PULL_POLICY          = var.app_image_pull_policy
      APP_IMAGE_BUILD_ENABLED        = tostring(var.enable_first_boot_deploy && var.app_image_build_enabled)
      APP_IMAGE_BUILD_CONTEXT        = "/opt/octo/repo"
      APP_IMAGE_DOCKERFILE           = "shop/Dockerfile"
      OCIR_REGISTRY                  = var.ocir_registry
      OCIR_USERNAME                  = var.ocir_username
      OCIR_AUTH_TOKEN                = var.ocir_auth_token
      APP_NAME                       = "octo-drone-shop"
      APP_RUNTIME                    = "compute"
      OTEL_SERVICE_NAME              = "octo-drone-shop"
      SERVICE_INSTANCE_ID            = "${var.name_prefix}-shop"
      DNS_DOMAIN                     = var.dns_domain
      SHOP_PUBLIC_URL                = local.shop_public_url
      OCTO_PUBLIC_HOSTNAME           = local.shop_hostname
      CORS_ALLOWED_ORIGINS           = "${local.shop_public_url},${local.crm_public_url}"
      ENVIRONMENT                    = "production"
      DEMO_STACK_NAME                = var.name_prefix
      APP_TOPOLOGY_PROFILE           = can(regex("private-demo", var.name_prefix)) ? "private-demo" : ""
      SERVICE_NAMESPACE              = "octo"
      PORT                           = "8080"
      APP_PORT                       = "8080"
      APP_CONTAINER_UID              = tostring(var.shop_container_uid)
      APP_CONTAINER_GID              = tostring(var.shop_container_gid)
      OCI_COMPARTMENT_ID             = var.compartment_id
      OCI_GENAI_ENDPOINT             = var.oci_genai_endpoint
      OCI_GENAI_MODEL_ID             = var.oci_genai_model_id
      LLMETRY_ENABLED                = "true"
      LLMETRY_STORE_ENABLED          = "true"
      LLMETRY_CAPTURE_CONTENT        = tostring(var.llmetry_capture_content)
      LANGFUSE_ENABLED               = tostring(var.langfuse_enabled)
      LANGFUSE_HOST                  = var.langfuse_host
      LANGFUSE_PROJECT_NAME          = var.langfuse_project_name
      LANGFUSE_PUBLIC_KEY            = var.langfuse_public_key
      LANGFUSE_SECRET_KEY            = var.langfuse_secret_key
      LANGFUSE_OTEL_EXPORT_ENABLED   = "true"
      LANGFUSE_TIMEOUT_SECONDS       = "2.0"
      LANGFUSE_INGESTION_VERSION     = "4"
      SERVICE_CRM_URL                = local.crm_private_service_url
      CRM_PUBLIC_URL                 = local.crm_public_url
      CRM_BASE_URL                   = local.crm_public_url
      SERVICE_SHOP_URL               = ""
      INTERNAL_SERVICE_KEY           = var.internal_service_key
      AUTH_TOKEN_SECRET              = var.auth_token_secret
      APP_SECRET_KEY                 = ""
      BOOTSTRAP_ADMIN_PASSWORD       = ""
      ORACLE_DSN                     = var.oracle_dsn
      ORACLE_USER                    = "ADMIN"
      ORACLE_PASSWORD                = var.atp_admin_password
      ORACLE_WALLET_PASSWORD         = var.atp_wallet_password
      ORACLE_WALLET_DIR              = "/opt/oracle/wallet"
      ATP_OCID                       = module.atp.atp_id
      DATABASE_OBSERVABILITY_ENABLED = "true"
      OCI_AUTH_MODE                  = "instance_principal"
      OCI_APM_ENDPOINT               = local.apm_endpoint
      OCI_APM_PRIVATE_DATAKEY        = local.apm_private_datakey
      OCI_APM_PUBLIC_DATAKEY         = local.apm_public_datakey
      OCI_APM_RUM_ENDPOINT           = local.apm_rum_endpoint
      OCI_APM_WEB_APPLICATION        = "octo-drone-shop-web"
      OCI_APM_RUM_PUBLIC_DATAKEY     = local.apm_public_datakey
      OTEL_TRACES_SAMPLER            = "always_on"
      OTEL_PYTHON_LOG_CORRELATION    = "true"
      OTLP_LOG_EXPORT_ENABLED        = "false"
      OCI_LOG_GROUP_ID               = module.logging.log_group_id
      OCI_LOG_ID                     = module.logging.log_app_id
      OCI_LOG_CHAOS_AUDIT_ID         = module.logging.log_chaos_audit_id
      OCI_LOG_SECURITY_ID            = module.logging.log_security_id
      IDCS_DOMAIN_URL                = ""
      IDCS_CLIENT_ID                 = ""
      IDCS_CLIENT_SECRET             = ""
    }
    crm = {
      OCTO_COMPUTE_ROLE              = "crm"
      CONTAINER_RUNTIME              = var.container_runtime
      APP_IMAGE                      = local.crm_app_image
      APP_IMAGE_PULL_POLICY          = var.app_image_pull_policy
      APP_IMAGE_BUILD_ENABLED        = tostring(var.enable_first_boot_deploy && var.app_image_build_enabled)
      APP_IMAGE_BUILD_CONTEXT        = "/opt/octo/repo"
      APP_IMAGE_DOCKERFILE           = "crm/Dockerfile"
      OCIR_REGISTRY                  = var.ocir_registry
      OCIR_USERNAME                  = var.ocir_username
      OCIR_AUTH_TOKEN                = var.ocir_auth_token
      APP_NAME                       = "enterprise-crm-portal"
      APP_RUNTIME                    = "compute"
      OTEL_SERVICE_NAME              = "enterprise-crm-portal"
      SERVICE_INSTANCE_ID            = "${var.name_prefix}-crm"
      DNS_DOMAIN                     = var.dns_domain
      SHOP_PUBLIC_URL                = local.shop_public_url
      OCTO_PUBLIC_HOSTNAME           = local.crm_hostname
      CORS_ALLOWED_ORIGINS           = "${local.shop_public_url},${local.crm_public_url}"
      ENVIRONMENT                    = "production"
      DEMO_STACK_NAME                = var.name_prefix
      APP_TOPOLOGY_PROFILE           = can(regex("private-demo", var.name_prefix)) ? "private-demo" : ""
      SERVICE_NAMESPACE              = "octo"
      PORT                           = "8080"
      APP_PORT                       = "8080"
      APP_CONTAINER_UID              = tostring(var.crm_container_uid)
      APP_CONTAINER_GID              = tostring(var.crm_container_gid)
      OCI_COMPARTMENT_ID             = var.compartment_id
      OCI_GENAI_ENDPOINT             = ""
      OCI_GENAI_MODEL_ID             = ""
      LLMETRY_ENABLED                = "false"
      LLMETRY_STORE_ENABLED          = "false"
      LLMETRY_CAPTURE_CONTENT        = "false"
      LANGFUSE_ENABLED               = "false"
      LANGFUSE_HOST                  = ""
      LANGFUSE_PROJECT_NAME          = ""
      LANGFUSE_PUBLIC_KEY            = ""
      LANGFUSE_SECRET_KEY            = ""
      LANGFUSE_OTEL_EXPORT_ENABLED   = "false"
      LANGFUSE_TIMEOUT_SECONDS       = "2.0"
      LANGFUSE_INGESTION_VERSION     = "4"
      SERVICE_CRM_URL                = ""
      CRM_PUBLIC_URL                 = ""
      CRM_BASE_URL                   = local.crm_public_url
      SERVICE_SHOP_URL               = local.shop_private_service_url
      INTERNAL_SERVICE_KEY           = var.internal_service_key
      AUTH_TOKEN_SECRET              = ""
      APP_SECRET_KEY                 = var.app_secret_key
      BOOTSTRAP_ADMIN_PASSWORD       = var.bootstrap_admin_password
      ORACLE_DSN                     = var.oracle_dsn
      ORACLE_USER                    = "ADMIN"
      ORACLE_PASSWORD                = var.atp_admin_password
      ORACLE_WALLET_PASSWORD         = var.atp_wallet_password
      ORACLE_WALLET_DIR              = "/opt/oracle/wallet"
      ATP_OCID                       = module.atp.atp_id
      DATABASE_OBSERVABILITY_ENABLED = "true"
      OCI_AUTH_MODE                  = "instance_principal"
      OCI_APM_ENDPOINT               = local.apm_endpoint
      OCI_APM_PRIVATE_DATAKEY        = local.apm_private_datakey
      OCI_APM_PUBLIC_DATAKEY         = local.apm_public_datakey
      OCI_APM_RUM_ENDPOINT           = local.apm_rum_endpoint
      OCI_APM_WEB_APPLICATION        = "octo-drone-shop-web"
      OCI_APM_RUM_PUBLIC_DATAKEY     = local.apm_public_datakey
      OTEL_TRACES_SAMPLER            = "always_on"
      OTEL_PYTHON_LOG_CORRELATION    = "true"
      OTLP_LOG_EXPORT_ENABLED        = "false"
      OCI_LOG_GROUP_ID               = module.logging.log_group_id
      OCI_LOG_ID                     = module.logging.log_app_id
      OCI_LOG_CHAOS_AUDIT_ID         = module.logging.log_chaos_audit_id
      OCI_LOG_SECURITY_ID            = module.logging.log_security_id
      IDCS_DOMAIN_URL                = ""
      IDCS_CLIENT_ID                 = ""
      IDCS_CLIENT_SECRET             = ""
    }
  }

  runtime_env_content = {
    for role, values in local.runtime_env_values :
    role => join("\n", [for key, value in values : "${key}='${replace(tostring(value), "'", "'\\''")}'"])
  }

  stack_monitoring_agent_ids = var.enable_stack_monitoring_standard ? {
    for role, agent_data in data.oci_management_agent_management_agents.app :
    role => try(agent_data.management_agents[0].id, "")
  } : {}
  stack_monitoring_atp_management_agent_id = var.stack_monitoring_atp_management_agent_id != "" ? var.stack_monitoring_atp_management_agent_id : try(local.stack_monitoring_agent_ids["shop"], "")
  stack_monitoring_plugin_id               = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_agent_plugin ? try(data.oci_management_agent_management_agent_plugins.stack_monitoring[0].management_agent_plugins[0].id, "") : ""
  stack_monitoring_named_credential_type   = join("", ["DBTCPS", "CREDS", "ADB"])
  atp_low_connection_string                = try(module.atp.atp_connection_strings[0].all_connection_strings["LOW"], "")
  atp_stack_monitoring_service_name        = try(split("/", local.atp_low_connection_string)[1], var.oracle_dsn)
  stack_monitoring_create_secret_vault = var.enable_stack_monitoring_standard && var.create_stack_monitoring_secrets && (
    var.stack_monitoring_atp_db_user_secret_id == "" ||
    var.stack_monitoring_atp_db_password_secret_id == ""
  )
  stack_monitoring_atp_ssl_secret_id         = var.stack_monitoring_atp_ssl_secret_id
  stack_monitoring_atp_db_user_secret_id     = var.stack_monitoring_atp_db_user_secret_id != "" ? var.stack_monitoring_atp_db_user_secret_id : try(oci_vault_secret.stack_monitoring_atp_db_user[0].id, "")
  stack_monitoring_atp_db_password_secret_id = var.stack_monitoring_atp_db_password_secret_id != "" ? var.stack_monitoring_atp_db_password_secret_id : try(oci_vault_secret.stack_monitoring_atp_db_password[0].id, "")
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "oracle_linux" {
  count = var.instance_image_ocid == "" ? 1 : 0

  compartment_id           = var.compartment_id
  operating_system         = var.instance_operating_system
  operating_system_version = var.instance_operating_system_version
  shape                    = var.instance_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

data "oci_core_services" "all" {
  count = local.service_gateway_enabled ? 1 : 0

  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

locals {
  availability_domain = var.availability_domain_name != "" ? var.availability_domain_name : data.oci_identity_availability_domains.ads.availability_domains[0].name
}

resource "terraform_data" "network_selection_guard" {
  input = {
    create_network                 = var.create_network
    existing_vcn_id                = var.existing_vcn_id
    existing_lb_subnet_id          = local.existing_lb_subnet_id
    existing_app_private_subnet_id = var.existing_app_private_subnet_id
    existing_db_private_subnet_id  = var.existing_db_private_subnet_id
  }

  lifecycle {
    precondition {
      condition = var.create_network || (
        var.existing_vcn_id != "" &&
        local.existing_lb_subnet_id != "" &&
        var.existing_app_private_subnet_id != ""
      )
      error_message = "When create_network=false, existing_vcn_id, existing_lb_subnet_id, and existing_app_private_subnet_id are required. existing_db_private_subnet_id is optional and falls back to the app subnet."
    }
  }
}

resource "terraform_data" "lb_tls_guard" {
  count = var.enable_lb_https ? 1 : 0

  input = {
    enable_lb_https = var.enable_lb_https
  }

  lifecycle {
    precondition {
      condition     = var.lb_certificate_public_certificate != "" && var.lb_certificate_private_key != ""
      error_message = "enable_lb_https=true requires lb_certificate_public_certificate and lb_certificate_private_key."
    }
  }
}

resource "terraform_data" "log_analytics_guard" {
  count = var.enable_log_analytics ? 1 : 0

  input = {
    enable_log_analytics                = var.enable_log_analytics
    log_analytics_namespace             = var.log_analytics_namespace
    create_log_analytics_namespace      = var.create_log_analytics_namespace
    existing_log_analytics_log_group_id = var.existing_log_analytics_log_group_id
  }

  lifecycle {
    precondition {
      condition     = var.log_analytics_namespace != "" || var.existing_log_analytics_log_group_id != ""
      error_message = "enable_log_analytics=true requires log_analytics_namespace or existing_log_analytics_log_group_id. Set create_log_analytics_namespace=true to onboard a new namespace using log_analytics_namespace."
    }
  }
}

resource "terraform_data" "first_boot_deploy_guard" {
  count = var.enable_first_boot_deploy ? 1 : 0

  input = {
    enable_first_boot_deploy = var.enable_first_boot_deploy
    app_image_build_enabled  = var.app_image_build_enabled
  }

  lifecycle {
    precondition {
      condition = (
        var.internal_service_key != "" &&
        var.auth_token_secret != "" &&
        var.app_secret_key != "" &&
        var.bootstrap_admin_password != ""
      )
      error_message = "enable_first_boot_deploy=true requires internal_service_key, auth_token_secret, app_secret_key, and bootstrap_admin_password."
    }

    precondition {
      condition = var.app_image_build_enabled || (
        var.shop_app_image != "" &&
        var.crm_app_image != ""
      )
      error_message = "When app_image_build_enabled=false, shop_app_image and crm_app_image must be set to pullable images."
    }
  }
}

resource "terraform_data" "dns_records_guard" {
  count = var.create_dns_records ? 1 : 0

  input = {
    create_dns_records  = var.create_dns_records
    dns_zone_name_or_id = var.dns_zone_name_or_id
  }

  lifecycle {
    precondition {
      condition     = var.create_load_balancer && var.dns_zone_name_or_id != ""
      error_message = "create_dns_records=true requires create_load_balancer=true and dns_zone_name_or_id."
    }
  }
}

resource "oci_core_vcn" "this" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-vcn"
  cidr_block     = var.vcn_cidr
  dns_label      = "octocompute"
  freeform_tags  = local.tags
}

resource "oci_core_internet_gateway" "this" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-igw"
  enabled        = true
  freeform_tags  = local.tags
}

resource "oci_core_nat_gateway" "this" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-nat"
  freeform_tags  = local.tags
}

resource "oci_core_service_gateway" "this" {
  count          = local.service_gateway_enabled ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-sgw"
  freeform_tags  = local.tags

  services {
    service_id = data.oci_core_services.all[0].services[0].id
  }
}

resource "oci_core_route_table" "lb_public" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-lb-public-rt"
  freeform_tags  = local.tags

  route_rules {
    network_entity_id = oci_core_internet_gateway.this[0].id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
}

resource "oci_core_route_table" "app_private" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-app-private-rt"
  freeform_tags  = local.tags

  route_rules {
    network_entity_id = oci_core_nat_gateway.this[0].id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    description       = "Private app egress for OS updates, GitHub clone, and image pulls."
  }

  dynamic "route_rules" {
    for_each = local.service_gateway_enabled ? [1] : []
    content {
      network_entity_id = oci_core_service_gateway.this[0].id
      destination       = data.oci_core_services.all[0].services[0].cidr_block
      destination_type  = "SERVICE_CIDR_BLOCK"
      description       = "Private access to OCI services for agents, Stack Monitoring, OPSI, DB Management, OCIR, and Logging."
    }
  }
}

resource "oci_core_route_table" "db_private" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-db-private-rt"
  freeform_tags  = local.tags

  dynamic "route_rules" {
    for_each = local.service_gateway_enabled ? [1] : []
    content {
      network_entity_id = oci_core_service_gateway.this[0].id
      destination       = data.oci_core_services.all[0].services[0].cidr_block
      destination_type  = "SERVICE_CIDR_BLOCK"
      description       = "Private access to OCI services for DB Management, OPSI, and Stack Monitoring."
    }
  }
}

resource "oci_core_security_list" "lb_public" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-lb-public-sl"
  freeform_tags  = local.tags

  dynamic "ingress_security_rules" {
    for_each = var.enable_lb_http ? var.public_web_cidrs : []
    content {
      protocol = "6"
      source   = ingress_security_rules.value
      tcp_options {
        min = 80
        max = 80
      }
    }
  }

  dynamic "ingress_security_rules" {
    for_each = var.enable_lb_https ? var.public_web_cidrs : []
    content {
      protocol = "6"
      source   = ingress_security_rules.value
      tcp_options {
        min = 443
        max = 443
      }
    }
  }

  egress_security_rules {
    protocol    = "6"
    destination = var.app_private_subnet_cidr
    tcp_options {
      min = 8080
      max = 8080
    }
  }
}

resource "oci_core_security_list" "app_private" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-app-private-sl"
  freeform_tags  = local.tags

  ingress_security_rules {
    protocol = "6"
    source   = var.public_lb_subnet_cidr
    tcp_options {
      min = 8080
      max = 8080
    }
  }

  ingress_security_rules {
    protocol = "6"
    source   = var.app_private_subnet_cidr
    tcp_options {
      min = 8080
      max = 8080
    }
  }

  dynamic "ingress_security_rules" {
    for_each = var.admin_ssh_cidrs
    content {
      protocol = "6"
      source   = ingress_security_rules.value
      tcp_options {
        min = 22
        max = 22
      }
    }
  }

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_security_list" "db_private" {
  count          = var.create_network ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-db-private-sl"
  freeform_tags  = local.tags

  ingress_security_rules {
    protocol = "6"
    source   = var.app_private_subnet_cidr
    tcp_options {
      min = 1521
      max = 1522
    }
  }

  dynamic "ingress_security_rules" {
    for_each = var.enable_database_management_private_endpoint || var.enable_operations_insights_private_endpoint ? [1] : []
    content {
      protocol = "6"
      source   = var.db_private_subnet_cidr
      tcp_options {
        min = 1521
        max = 1522
      }
    }
  }

  dynamic "egress_security_rules" {
    for_each = local.service_gateway_enabled ? [1] : []
    content {
      protocol         = "all"
      destination      = data.oci_core_services.all[0].services[0].cidr_block
      destination_type = "SERVICE_CIDR_BLOCK"
    }
  }
}

resource "oci_core_subnet" "lb_public" {
  count                      = var.create_network ? 1 : 0
  compartment_id             = var.compartment_id
  vcn_id                     = local.vcn_id
  display_name               = "${var.name_prefix}-lb-public-subnet"
  dns_label                  = "lb"
  cidr_block                 = var.public_lb_subnet_cidr
  route_table_id             = oci_core_route_table.lb_public[0].id
  security_list_ids          = [oci_core_security_list.lb_public[0].id]
  prohibit_public_ip_on_vnic = false
  freeform_tags              = local.tags
}

resource "oci_core_subnet" "app_private" {
  count                      = var.create_network ? 1 : 0
  compartment_id             = var.compartment_id
  vcn_id                     = local.vcn_id
  display_name               = "${var.name_prefix}-app-private-subnet"
  dns_label                  = "apps"
  cidr_block                 = var.app_private_subnet_cidr
  route_table_id             = oci_core_route_table.app_private[0].id
  security_list_ids          = [oci_core_security_list.app_private[0].id]
  prohibit_public_ip_on_vnic = true
  freeform_tags              = local.tags
}

resource "oci_core_subnet" "db_private" {
  count                      = var.create_network ? 1 : 0
  compartment_id             = var.compartment_id
  vcn_id                     = local.vcn_id
  display_name               = "${var.name_prefix}-db-private-subnet"
  dns_label                  = "db"
  cidr_block                 = var.db_private_subnet_cidr
  route_table_id             = oci_core_route_table.db_private[0].id
  security_list_ids          = [oci_core_security_list.db_private[0].id]
  prohibit_public_ip_on_vnic = true
  freeform_tags              = local.tags
}

resource "oci_core_network_security_group" "lb" {
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-lb-nsg"
  freeform_tags  = local.tags
  depends_on     = [terraform_data.network_selection_guard]
}

resource "oci_core_network_security_group" "app" {
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-app-nsg"
  freeform_tags  = local.tags
  depends_on     = [terraform_data.network_selection_guard]
}

resource "oci_core_network_security_group" "db" {
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-db-nsg"
  freeform_tags  = local.tags
  depends_on     = [terraform_data.network_selection_guard]
}

resource "oci_core_network_security_group" "service_endpoints" {
  count          = var.enable_database_management_private_endpoint || var.enable_operations_insights_private_endpoint ? 1 : 0
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${var.name_prefix}-svc-endpoints-nsg"
  freeform_tags  = local.tags
  depends_on     = [terraform_data.network_selection_guard]
}

resource "oci_core_network_security_group_security_rule" "lb_https" {
  for_each                  = var.enable_lb_https ? toset(var.public_web_cidrs) : []
  network_security_group_id = oci_core_network_security_group.lb.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "lb_http" {
  for_each                  = var.enable_lb_http ? toset(var.public_web_cidrs) : []
  network_security_group_id = oci_core_network_security_group.lb.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

resource "oci_core_network_security_group_security_rule" "lb_to_app" {
  network_security_group_id = oci_core_network_security_group.lb.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.app.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  description               = "Load Balancer can reach app containers only on port 8080."

  tcp_options {
    destination_port_range {
      min = 8080
      max = 8080
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_from_lb" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.lb.id
  source_type               = "NETWORK_SECURITY_GROUP"
  description               = "Only the public Load Balancer can reach app containers from the public edge."

  tcp_options {
    destination_port_range {
      min = 8080
      max = 8080
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_private_to_app" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.app.id
  source_type               = "NETWORK_SECURITY_GROUP"
  description               = "Shop and CRM private cross-service calls."

  tcp_options {
    destination_port_range {
      min = 8080
      max = 8080
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_ssh" {
  for_each                  = toset(var.admin_ssh_cidrs)
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "Optional private SSH path through Bastion, VPN, FastConnect, or DRG."

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_egress_all" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "Private app egress through NAT and Service Gateway routes."
}

resource "oci_core_network_security_group_security_rule" "db_from_app" {
  network_security_group_id = oci_core_network_security_group.db.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.app.id
  source_type               = "NETWORK_SECURITY_GROUP"
  description               = "ATP private endpoint accepts SQL*Net/TCPS only from app hosts."

  tcp_options {
    destination_port_range {
      min = 1521
      max = 1522
    }
  }
}

resource "oci_core_network_security_group_security_rule" "db_from_service_endpoints" {
  count                     = var.enable_database_management_private_endpoint || var.enable_operations_insights_private_endpoint ? 1 : 0
  network_security_group_id = oci_core_network_security_group.db.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = oci_core_network_security_group.service_endpoints[0].id
  source_type               = "NETWORK_SECURITY_GROUP"
  description               = "Optional private endpoints for Database Management and Operations Insights."

  tcp_options {
    destination_port_range {
      min = 1521
      max = 1522
    }
  }
}

resource "oci_core_network_security_group_security_rule" "db_egress_to_oci_services" {
  count                     = local.service_gateway_enabled ? 1 : 0
  network_security_group_id = oci_core_network_security_group.db.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = data.oci_core_services.all[0].services[0].cidr_block
  destination_type          = "SERVICE_CIDR_BLOCK"
  description               = "Private DB subnet egress is limited to OCI Services Network through the Service Gateway."
}

resource "oci_core_network_security_group_security_rule" "service_endpoints_to_db" {
  count                     = var.enable_database_management_private_endpoint || var.enable_operations_insights_private_endpoint ? 1 : 0
  network_security_group_id = oci_core_network_security_group.service_endpoints[0].id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination               = oci_core_network_security_group.db.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  description               = "DB Management and OPSI private endpoint egress to the ATP private endpoint."

  tcp_options {
    destination_port_range {
      min = 1521
      max = 1522
    }
  }
}

resource "oci_load_balancer_load_balancer" "public" {
  count                        = var.create_load_balancer ? 1 : 0
  compartment_id               = var.compartment_id
  display_name                 = "${var.name_prefix}-lb"
  shape                        = var.lb_shape
  is_private                   = false
  subnet_ids                   = [local.lb_subnet_id]
  network_security_group_ids   = [oci_core_network_security_group.lb.id]
  is_request_id_enabled        = true
  request_id_header            = "X-Request-ID"
  freeform_tags                = local.tags
  is_delete_protection_enabled = var.lb_delete_protection_enabled

  dynamic "shape_details" {
    for_each = lower(var.lb_shape) == "flexible" ? [1] : []
    content {
      minimum_bandwidth_in_mbps = var.lb_min_bandwidth_mbps
      maximum_bandwidth_in_mbps = var.lb_max_bandwidth_mbps
    }
  }

  depends_on = [terraform_data.network_selection_guard]
}

resource "oci_load_balancer_backend_set" "app" {
  for_each         = var.create_load_balancer ? local.instances : {}
  load_balancer_id = oci_load_balancer_load_balancer.public[0].id
  name             = each.value.backend_set_name
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol          = "HTTP"
    port              = 8080
    url_path          = "/ready"
    return_code       = 200
    interval_ms       = 10000
    timeout_in_millis = 3000
    retries           = 3
  }
}

resource "oci_load_balancer_backend" "app" {
  for_each         = var.create_load_balancer ? local.instances : {}
  load_balancer_id = oci_load_balancer_load_balancer.public[0].id
  backendset_name  = oci_load_balancer_backend_set.app[each.key].name
  ip_address       = oci_core_instance.app[each.key].private_ip
  port             = 8080
  weight           = 1
}

resource "oci_load_balancer_load_balancer_routing_policy" "host" {
  count                      = var.create_load_balancer ? 1 : 0
  load_balancer_id           = oci_load_balancer_load_balancer.public[0].id
  name                       = "host_routing"
  condition_language_version = "V1"

  rules {
    name      = "crm_host"
    condition = "any(http.request.headers[(i 'Host')] eq (i '${local.crm_hostname}'))"

    actions {
      name             = "FORWARD_TO_BACKENDSET"
      backend_set_name = oci_load_balancer_backend_set.app["crm"].name
    }
  }

  rules {
    name      = "shop_host"
    condition = "any(http.request.headers[(i 'Host')] eq (i '${local.shop_hostname}'))"

    actions {
      name             = "FORWARD_TO_BACKENDSET"
      backend_set_name = oci_load_balancer_backend_set.app["shop"].name
    }
  }
}

resource "oci_load_balancer_certificate" "public" {
  count              = var.create_load_balancer && var.enable_lb_https ? 1 : 0
  load_balancer_id   = oci_load_balancer_load_balancer.public[0].id
  certificate_name   = "${var.name_prefix}-cert"
  public_certificate = var.lb_certificate_public_certificate
  private_key        = var.lb_certificate_private_key
  ca_certificate     = var.lb_certificate_ca_certificate == "" ? null : var.lb_certificate_ca_certificate
  passphrase         = var.lb_certificate_passphrase == "" ? null : var.lb_certificate_passphrase

  depends_on = [terraform_data.lb_tls_guard]
}

resource "oci_load_balancer_listener" "http" {
  count                    = var.create_load_balancer && var.enable_lb_http ? 1 : 0
  load_balancer_id         = oci_load_balancer_load_balancer.public[0].id
  name                     = "http"
  default_backend_set_name = oci_load_balancer_backend_set.app["shop"].name
  port                     = 80
  protocol                 = "HTTP"
  routing_policy_name      = oci_load_balancer_load_balancer_routing_policy.host[0].name
}

resource "oci_load_balancer_listener" "https" {
  count                    = var.create_load_balancer && var.enable_lb_https ? 1 : 0
  load_balancer_id         = oci_load_balancer_load_balancer.public[0].id
  name                     = "https"
  default_backend_set_name = oci_load_balancer_backend_set.app["shop"].name
  port                     = 443
  protocol                 = "HTTP"
  routing_policy_name      = oci_load_balancer_load_balancer_routing_policy.host[0].name

  ssl_configuration {
    certificate_name        = oci_load_balancer_certificate.public[0].certificate_name
    protocols               = ["TLSv1.2", "TLSv1.3"]
    server_order_preference = "ENABLED"
  }
}

resource "oci_dns_rrset" "app" {
  for_each = var.create_dns_records && var.create_load_balancer ? local.instances : {}

  zone_name_or_id = var.dns_zone_name_or_id
  domain          = each.value.hostname
  rtype           = "A"

  items {
    domain = each.value.hostname
    rdata  = oci_load_balancer_load_balancer.public[0].ip_address_details[0].ip_address
    rtype  = "A"
    ttl    = var.dns_record_ttl
  }

  depends_on = [terraform_data.dns_records_guard]
}

module "atp" {
  source                      = "../../terraform/modules/atp"
  compartment_id              = var.compartment_id
  display_name                = "${var.name_prefix}-atp"
  db_name                     = "OCTOATP"
  compute_count               = var.atp_compute_count
  data_storage_size_in_gbs    = var.atp_storage_size_gbs
  is_auto_scaling_enabled     = var.atp_auto_scaling_enabled
  admin_password              = var.atp_admin_password
  wallet_password             = var.atp_wallet_password
  whitelisted_ips             = var.atp_whitelisted_ips
  subnet_id                   = local.db_subnet_id
  nsg_ids                     = [oci_core_network_security_group.db.id]
  private_endpoint_label      = var.atp_private_endpoint_label
  is_mtls_connection_required = true
  database_management_status  = var.enable_database_management ? "ENABLED" : ""
  operations_insights_status  = var.enable_operations_insights ? "ENABLED" : ""
  tags                        = local.tags
  depends_on                  = [terraform_data.network_selection_guard]
}

resource "oci_database_management_db_management_private_endpoint" "this" {
  count                     = var.enable_database_management_private_endpoint ? 1 : 0
  compartment_id            = var.compartment_id
  name                      = "${local.name_prefix_api}_dbman_pe"
  description               = "Private endpoint for OCTO ATP Database Management."
  subnet_id                 = local.db_subnet_id
  nsg_ids                   = [oci_core_network_security_group.service_endpoints[0].id]
  is_dns_resolution_enabled = true
  freeform_tags             = local.tags
}

resource "oci_opsi_operations_insights_private_endpoint" "this" {
  count               = var.enable_operations_insights_private_endpoint ? 1 : 0
  compartment_id      = var.compartment_id
  display_name        = "${var.name_prefix}-opsi-pe"
  description         = "Private endpoint for OCTO ATP Operations Insights."
  vcn_id              = local.vcn_id
  subnet_id           = local.db_subnet_id
  nsg_ids             = [oci_core_network_security_group.service_endpoints[0].id]
  is_used_for_rac_dbs = false
  freeform_tags       = local.tags
}

resource "oci_kms_vault" "stack_monitoring" {
  count          = local.stack_monitoring_create_secret_vault ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-stack-monitoring-vault"
  vault_type     = "DEFAULT"
  freeform_tags  = local.tags
}

resource "oci_kms_key" "stack_monitoring" {
  count               = local.stack_monitoring_create_secret_vault ? 1 : 0
  compartment_id      = var.compartment_id
  display_name        = "${var.name_prefix}-stack-monitoring-key"
  management_endpoint = oci_kms_vault.stack_monitoring[0].management_endpoint
  protection_mode     = "SOFTWARE"
  freeform_tags       = local.tags

  depends_on = [time_sleep.stack_monitoring_vault_dns]

  key_shape {
    algorithm = "AES"
    length    = 32
  }
}

resource "time_sleep" "stack_monitoring_vault_dns" {
  count = local.stack_monitoring_create_secret_vault ? 1 : 0

  create_duration = "${var.stack_monitoring_vault_dns_wait_seconds}s"

  depends_on = [oci_kms_vault.stack_monitoring]
}

resource "oci_vault_secret" "stack_monitoring_atp_db_user" {
  count          = var.enable_stack_monitoring_standard && var.create_stack_monitoring_secrets && var.stack_monitoring_atp_db_user_secret_id == "" ? 1 : 0
  compartment_id = var.compartment_id
  vault_id       = oci_kms_vault.stack_monitoring[0].id
  key_id         = oci_kms_key.stack_monitoring[0].id
  secret_name    = "${var.name_prefix}-atp-db-user"
  description    = "ATP username consumed by OCI Stack Monitoring."
  freeform_tags  = local.tags

  secret_content {
    content_type = "BASE64"
    content      = base64encode("ADMIN")
  }
}

resource "oci_vault_secret" "stack_monitoring_atp_db_password" {
  count          = var.enable_stack_monitoring_standard && var.create_stack_monitoring_secrets && var.stack_monitoring_atp_db_password_secret_id == "" ? 1 : 0
  compartment_id = var.compartment_id
  vault_id       = oci_kms_vault.stack_monitoring[0].id
  key_id         = oci_kms_key.stack_monitoring[0].id
  secret_name    = "${var.name_prefix}-atp-db-password"
  description    = "ATP ADMIN password consumed by OCI Stack Monitoring."
  freeform_tags  = local.tags

  secret_content {
    content_type = "BASE64"
    content      = base64encode(var.atp_admin_password)
  }
}

module "logging" {
  source             = "../../terraform/modules/logging"
  compartment_id     = var.compartment_id
  retention_duration = var.logging_retention_days
}

resource "oci_logging_log" "os" {
  display_name       = "${var.name_prefix}-os"
  log_group_id       = module.logging.log_group_id
  log_type           = "CUSTOM"
  is_enabled         = true
  retention_duration = var.logging_retention_days
}

resource "oci_logging_log" "app_stdout" {
  display_name       = "${var.name_prefix}-app-stdout"
  log_group_id       = module.logging.log_group_id
  log_type           = "CUSTOM"
  is_enabled         = true
  retention_duration = var.logging_retention_days
}

resource "oci_logging_log" "waf" {
  count              = var.create_load_balancer && var.enable_waf && var.enable_waf_logging ? 1 : 0
  display_name       = "${var.name_prefix}-waf"
  log_group_id       = module.logging.log_group_id
  log_type           = "SERVICE"
  is_enabled         = true
  retention_duration = var.logging_retention_days

  configuration {
    compartment_id = var.compartment_id
    source {
      category    = "all"
      resource    = oci_waf_web_app_firewall.lb[0].id
      service     = "waf"
      source_type = "OCISERVICE"
    }
  }
}

resource "oci_log_analytics_namespace" "this" {
  count = var.enable_log_analytics && var.create_log_analytics_namespace ? 1 : 0

  compartment_id = var.tenancy_ocid
  namespace      = var.log_analytics_namespace
  is_onboarded   = true

  depends_on = [terraform_data.log_analytics_guard]
}

resource "oci_log_analytics_log_analytics_log_group" "this" {
  count          = local.create_log_analytics_loggroup ? 1 : 0
  compartment_id = var.compartment_id
  namespace      = local.effective_log_analytics_namespace
  display_name   = "${var.name_prefix}-logs"
  description    = "Log Analytics group for OCTO app, host, container, and WAF logs."
  freeform_tags  = local.tags

  depends_on = [terraform_data.log_analytics_guard]
}

resource "oci_identity_policy" "service_connector_log_analytics" {
  count          = var.enable_log_analytics ? 1 : 0
  compartment_id = var.compartment_id
  name           = "${var.name_prefix}-sch-log-analytics"
  description    = "Allow Service Connector Hub to upload OCTO logs to Log Analytics."
  statements = [
    "Allow any-user to {LOG_ANALYTICS_LOG_GROUP_UPLOAD_LOGS} in compartment id ${var.compartment_id} where all {request.principal.type='serviceconnector', target.loganalytics-log-group.id='${local.log_analytics_log_group_id}', request.principal.compartment.id='${var.compartment_id}'}",
  ]
}

resource "oci_sch_service_connector" "log_analytics_app" {
  count          = var.enable_log_analytics && var.enable_log_analytics_connectors ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-la-app"
  description    = "Route OCTO application SDK logs into Log Analytics."
  freeform_tags  = local.tags

  source {
    kind = "logging"
    log_sources {
      compartment_id = var.compartment_id
      log_group_id   = module.logging.log_group_id
      log_id         = module.logging.log_app_id
    }
  }

  target {
    kind         = "loggingAnalytics"
    log_group_id = local.log_analytics_log_group_id
  }

  depends_on = [oci_identity_policy.service_connector_log_analytics]
}

resource "oci_sch_service_connector" "log_analytics_os" {
  count          = var.enable_log_analytics && var.enable_log_analytics_connectors ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-la-os"
  description    = "Route OCTO OS and Oracle Cloud Agent custom logs into Log Analytics."
  freeform_tags  = local.tags

  source {
    kind = "logging"
    log_sources {
      compartment_id = var.compartment_id
      log_group_id   = module.logging.log_group_id
      log_id         = oci_logging_log.os.id
    }
  }

  target {
    kind         = "loggingAnalytics"
    log_group_id = local.log_analytics_log_group_id
  }

  depends_on = [oci_identity_policy.service_connector_log_analytics]
}

resource "oci_sch_service_connector" "log_analytics_container" {
  count          = var.enable_log_analytics && var.enable_log_analytics_connectors ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-la-container"
  description    = "Route OCTO Podman/Docker stdout logs into Log Analytics."
  freeform_tags  = local.tags

  source {
    kind = "logging"
    log_sources {
      compartment_id = var.compartment_id
      log_group_id   = module.logging.log_group_id
      log_id         = oci_logging_log.app_stdout.id
    }
  }

  target {
    kind         = "loggingAnalytics"
    log_group_id = local.log_analytics_log_group_id
  }

  depends_on = [oci_identity_policy.service_connector_log_analytics]
}

resource "oci_sch_service_connector" "log_analytics_waf" {
  count          = var.enable_log_analytics && var.enable_log_analytics_connectors && var.create_load_balancer && var.enable_waf && var.enable_waf_logging ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-la-waf"
  description    = "Route OCTO WAF logs into Log Analytics."
  freeform_tags  = local.tags

  source {
    kind = "logging"
    log_sources {
      compartment_id = var.compartment_id
      log_group_id   = module.logging.log_group_id
      log_id         = oci_logging_log.waf[0].id
    }
  }

  target {
    kind         = "loggingAnalytics"
    log_group_id = local.log_analytics_log_group_id
  }

  depends_on = [oci_identity_policy.service_connector_log_analytics]
}

module "apm_domain" {
  source                       = "../../terraform/modules/apm_domain"
  count                        = var.create_apm_domain ? 1 : 0
  compartment_id               = var.compartment_id
  display_name                 = "${var.name_prefix}-apm"
  web_application_display_name = "octo-drone-shop-web"
}

module "waf_compute" {
  source            = "../../terraform/modules/waf"
  count             = var.create_load_balancer && var.enable_waf ? 1 : 0
  compartment_id    = var.compartment_id
  display_name      = "${var.name_prefix}-waf-policy"
  domain            = var.dns_domain
  mode              = var.waf_mode
  log_group_id      = module.logging.log_group_id
  admin_allow_cidrs = var.admin_web_cidrs
}

resource "oci_waf_web_app_firewall" "lb" {
  count                      = var.create_load_balancer && var.enable_waf ? 1 : 0
  compartment_id             = var.compartment_id
  display_name               = "${var.name_prefix}-lb-waf"
  backend_type               = "LOAD_BALANCER"
  load_balancer_id           = oci_load_balancer_load_balancer.public[0].id
  web_app_firewall_policy_id = module.waf_compute[0].policy_ocid
  freeform_tags              = local.tags
}

resource "oci_stack_monitoring_config" "standard_license_auto_assign" {
  count          = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_configs ? 1 : 0
  compartment_id = var.compartment_id
  config_type    = "LICENSE_AUTO_ASSIGN"
  display_name   = "${var.name_prefix}-stack-monitoring-standard-license"
  is_enabled     = true
  license        = "STANDARD_EDITION"
  resource_type  = "HOST"
}

resource "oci_stack_monitoring_config" "host_auto_promote" {
  count          = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_configs ? 1 : 0
  compartment_id = var.compartment_id
  config_type    = "AUTO_PROMOTE"
  display_name   = "${var.name_prefix}-stack-monitoring-host-auto-promote"
  is_enabled     = true
  resource_type  = "HOST"

  depends_on = [oci_stack_monitoring_config.standard_license_auto_assign]
}

data "oci_management_agent_management_agent_plugins" "stack_monitoring" {
  count          = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_agent_plugin ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "Stack Monitoring"
  platform_type  = ["LINUX"]
  state          = "ACTIVE"
}

resource "terraform_data" "stack_monitoring_agent_guard" {
  count = var.enable_stack_monitoring_standard ? 1 : 0

  input = local.stack_monitoring_agent_ids

  lifecycle {
    precondition {
      condition = length([
        for role, agent_id in local.stack_monitoring_agent_ids : role
        if agent_id != ""
      ]) == length(local.instances)
      error_message = "Stack Monitoring Standard requires active OCI Management Agents for both Compute hosts."
    }
  }
}

resource "oci_management_agent_management_agent" "stack_monitoring_plugin" {
  for_each = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_agent_plugin ? local.stack_monitoring_agent_ids : {}

  managed_agent_id  = each.value
  deploy_plugins_id = [local.stack_monitoring_plugin_id]

  timeouts {
    create = "30m"
    update = "30m"
  }

  lifecycle {
    precondition {
      condition     = each.value != ""
      error_message = "Cannot deploy the Stack Monitoring plugin until the Compute host Management Agent is active."
    }
    precondition {
      condition     = local.stack_monitoring_plugin_id != ""
      error_message = "Could not resolve the Linux Management Agent plugin named 'Stack Monitoring'."
    }
  }

  depends_on = [terraform_data.stack_monitoring_agent_guard]
}

resource "oci_stack_monitoring_monitored_resource" "host" {
  for_each = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_host_registration ? local.stack_monitoring_agent_ids : {}

  compartment_id      = var.compartment_id
  name                = "${var.name_prefix}-${each.key}"
  type                = "host"
  display_name        = "${var.name_prefix}-${each.key}"
  host_name           = each.key
  management_agent_id = each.value
  license             = "STANDARD_EDITION"
  freeform_tags = merge(local.tags, {
    role = each.key
    type = "host"
  })

  properties {
    name  = "osName"
    value = var.instance_operating_system
  }

  properties {
    name  = "osVersion"
    value = var.instance_operating_system_version
  }

  lifecycle {
    precondition {
      condition     = each.value != ""
      error_message = "Cannot create a Stack Monitoring host resource until the Compute host Management Agent is active."
    }
  }

  depends_on = [
    oci_management_agent_management_agent.stack_monitoring_plugin,
    oci_stack_monitoring_config.standard_license_auto_assign,
  ]
}

module "stack_monitoring_atp" {
  source                  = "../../terraform/modules/stack_monitoring"
  count                   = var.enable_stack_monitoring_standard && var.enable_stack_monitoring_atp_registration ? 1 : 0
  compartment_id          = var.compartment_id
  autonomous_db_id        = module.atp.atp_id
  monitored_resource_name = "${var.name_prefix}-atp"
  management_agent_id     = local.stack_monitoring_atp_management_agent_id
  database_connection_details = {
    protocol      = var.stack_monitoring_atp_ssl_secret_id == "" ? "TCP" : "TCPS"
    port          = 1522
    service_name  = local.atp_stack_monitoring_service_name
    ssl_secret_id = local.stack_monitoring_atp_ssl_secret_id == "" ? null : local.stack_monitoring_atp_ssl_secret_id
  }
  credential_name = oci_management_agent_named_credential.stack_monitoring_atp[0].name

  depends_on = [oci_stack_monitoring_config.host_auto_promote, oci_management_agent_named_credential.stack_monitoring_atp, oci_management_agent_management_agent.stack_monitoring_plugin]
}

resource "oci_management_agent_named_credential" "stack_monitoring_atp" {
  count               = var.enable_stack_monitoring_standard && (var.enable_stack_monitoring_atp_registration || var.create_stack_monitoring_secrets) ? 1 : 0
  management_agent_id = local.stack_monitoring_atp_management_agent_id
  name                = "${local.name_prefix_api}_atp_creds"
  type                = local.stack_monitoring_named_credential_type
  description         = "ATP credentials for OCTO Stack Monitoring."
  freeform_tags       = local.tags

  properties {
    name           = "DBUserName"
    value          = local.stack_monitoring_atp_db_user_secret_id
    value_category = "SECRET_IDENTIFIER"
  }

  properties {
    name           = "DBPassword"
    value          = local.stack_monitoring_atp_db_password_secret_id
    value_category = "SECRET_IDENTIFIER"
  }

  properties {
    name           = "DBRole"
    value          = "NORMAL"
    value_category = "ALLOWED_VALUE"
  }

  properties {
    name           = "ADBDatabase"
    value          = module.atp.atp_id
    value_category = "ADB_IDENTIFIER"
  }

  lifecycle {
    precondition {
      condition     = local.stack_monitoring_atp_management_agent_id != ""
      error_message = "A Management Agent is required before creating the ATP Stack Monitoring named credential."
    }
    precondition {
      condition = (
        local.stack_monitoring_atp_db_user_secret_id != "" &&
        local.stack_monitoring_atp_db_password_secret_id != ""
      )
      error_message = "ATP Stack Monitoring DB user/password Vault secret OCIDs are required."
    }
  }
}

data "oci_management_agent_management_agents" "app" {
  for_each = var.enable_stack_monitoring_standard ? local.instances : {}

  compartment_id   = var.compartment_id
  host_id          = oci_core_instance.app[each.key].id
  state            = "ACTIVE"
  wait_for_host_id = var.management_agent_wait_seconds

  depends_on = [time_sleep.management_agent_registration]
}

resource "time_sleep" "management_agent_registration" {
  count = var.enable_stack_monitoring_standard ? 1 : 0

  create_duration = "${var.management_agent_initial_wait_seconds}s"
  triggers = {
    shop_instance_id = oci_core_instance.app["shop"].id
    crm_instance_id  = oci_core_instance.app["crm"].id
  }

  depends_on = [oci_core_instance.app]
}

resource "oci_identity_dynamic_group" "compute" {
  count          = var.create_compute_instance_principal_policies ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = "${var.name_prefix}-instances"
  description    = "OCTO private Compute demo hosts"
  matching_rule  = "ANY {instance.id = '${oci_core_instance.app["shop"].id}', instance.id = '${oci_core_instance.app["crm"].id}'}"
}

resource "oci_identity_policy" "compute" {
  count          = var.create_compute_instance_principal_policies ? 1 : 0
  compartment_id = var.compartment_id
  name           = "${var.name_prefix}-instances"
  description    = "Least-privilege access for OCTO Compute app instances"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.compute[0].name} to read repos in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.compute[0].name} to use log-content in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.compute[0].name} to use apm-domains in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.compute[0].name} to use metrics in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.compute[0].name} to use management-agents in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.compute[0].name} to read autonomous-database-family in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.compute[0].name} to read secret-family in compartment id ${var.compartment_id}",
  ]
}

resource "oci_logging_unified_agent_configuration" "os_logs" {
  count          = var.enable_unified_agent_log_collection && var.create_compute_instance_principal_policies ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-os-logs"
  description    = "Collect OS, cloud-init, Podman, Docker, and OCTO install logs from the two private Compute instances."
  is_enabled     = true

  group_association {
    group_list = [oci_identity_dynamic_group.compute[0].id]
  }

  service_configuration {
    configuration_type = "LOGGING"

    destination {
      log_object_id = oci_logging_log.os.id
    }

    sources {
      source_type = "LOG_TAIL"
      name        = "octo-os"
      paths = [
        "/var/log/messages",
        "/var/log/syslog",
        "/var/log/cloud-init.log",
        "/var/log/cloud-init-output.log",
        "/var/log/octo/*.log",
        "/var/log/tetragon/tetragon.log",
      ]

      parser {
        parser_type = "NONE"
      }
    }
  }
}

resource "oci_logging_unified_agent_configuration" "container_stdout" {
  count          = var.enable_unified_agent_log_collection && var.create_compute_instance_principal_policies ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = "${var.name_prefix}-container-stdout"
  description    = "Collect Podman and Docker container stdout/stderr from OCTO app containers."
  is_enabled     = true

  group_association {
    group_list = [oci_identity_dynamic_group.compute[0].id]
  }

  service_configuration {
    configuration_type = "LOGGING"

    destination {
      log_object_id = oci_logging_log.app_stdout.id
    }

    sources {
      source_type = "LOG_TAIL"
      name        = "octo-container-json"
      paths = [
        "/var/lib/containers/storage/overlay-containers/*/userdata/ctr.log",
        "/var/lib/docker/containers/*/*.log",
      ]

      parser {
        parser_type = "JSON"
      }
    }
  }
}

resource "oci_core_instance" "app" {
  for_each       = local.instances
  compartment_id = var.compartment_id
  availability_domain = each.key == "shop" && var.shop_availability_domain_name != "" ? var.shop_availability_domain_name : (
    each.key == "crm" && var.crm_availability_domain_name != "" ? var.crm_availability_domain_name : local.availability_domain
  )
  display_name = "${var.name_prefix}-${each.key}"
  shape        = var.instance_shape
  freeform_tags = merge(local.tags, {
    role = each.key
  })

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gbs
  }

  create_vnic_details {
    display_name     = "${var.name_prefix}-${each.key}-vnic"
    subnet_id        = local.app_subnet_id
    assign_public_ip = false
    nsg_ids          = [oci_core_network_security_group.app.id]
    hostname_label   = each.key
  }

  source_details {
    source_type             = "image"
    source_id               = local.instance_image_ocid
    boot_volume_size_in_gbs = var.boot_volume_size_gbs
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64gzip(templatefile("${path.module}/cloud-init/compute.yaml.tftpl", {
      role                     = each.key
      repo_url                 = var.repo_url
      repo_ref                 = var.repo_ref
      dns_domain               = var.dns_domain
      public_hostname          = each.value.hostname
      enable_first_boot_deploy = var.enable_first_boot_deploy
      runtime_env              = "      ${replace(local.runtime_env_content[each.key], "\n", "\n      ")}"
      compute_bootstrap_files  = local.compute_bootstrap_files
    }))
  }

  agent_config {
    is_management_disabled = false
    is_monitoring_disabled = false

    plugins_config {
      name          = "Compute Instance Monitoring"
      desired_state = "ENABLED"
    }
    plugins_config {
      name          = "Custom Logs Monitoring"
      desired_state = "ENABLED"
    }
    plugins_config {
      name          = "Compute Instance Run Command"
      desired_state = "ENABLED"
    }
    plugins_config {
      name          = "Management Agent"
      desired_state = "ENABLED"
    }
  }

  lifecycle {
    ignore_changes = [metadata["user_data"]]
  }
}

# ── Security Automation (eBPF + Auto-Remediation) ─────────────
module "security_automation" {
  source         = "../../terraform/modules/security"
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  subnet_id      = local.app_subnet_id
  log_group_id   = var.existing_log_analytics_log_group_id != "" ? var.existing_log_analytics_log_group_id : oci_log_analytics_log_analytics_log_group.this[0].id
  name_prefix    = var.name_prefix
}
