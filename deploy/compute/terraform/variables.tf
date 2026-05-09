variable "tenancy_ocid" {
  type        = string
  description = "Root tenancy OCID. Needed for dynamic groups."
}

variable "oci_profile" {
  type        = string
  default     = "DEFAULT"
  description = "OCI CLI config profile used by the Terraform OCI provider."
}

variable "compartment_id" {
  type        = string
  description = "Compartment OCID that owns the Compute, ATP, APM, and Logging resources."
}

variable "name_prefix" {
  type        = string
  default     = "octo-compute"
  description = "Prefix for all production-demo Compute resources."
}

variable "repo_url" {
  type    = string
  default = "https://github.com/adibirzu/octo-apm-demo.git"
}

variable "repo_ref" {
  type        = string
  default     = "main"
  description = "Git branch/tag cloned by cloud-init on each instance."
}

variable "enable_first_boot_deploy" {
  type        = bool
  default     = false
  description = "Render runtime.env, install the ATP wallet, build/pull the selected app image, and start the app during cloud-init."
}

variable "container_runtime" {
  type        = string
  default     = "podman"
  description = "Container runtime used by install.sh."
  validation {
    condition     = contains(["podman", "docker"], var.container_runtime)
    error_message = "container_runtime must be podman or docker."
  }
}

variable "app_image_build_enabled" {
  type        = bool
  default     = true
  description = "When first-boot deploy is enabled, build Shop/CRM images locally from repo_url instead of pulling from OCIR."
}

variable "image_tag" {
  type        = string
  default     = "stack"
  description = "Tag used for generated local images or default OCIR image coordinates."
}

variable "shop_app_image" {
  type        = string
  default     = ""
  description = "Shop container image. Empty uses localhost/octo-drone-shop:<image_tag> when app_image_build_enabled=true."
}

variable "crm_app_image" {
  type        = string
  default     = ""
  description = "CRM container image. Empty uses localhost/enterprise-crm-portal:<image_tag> when app_image_build_enabled=true."
}

variable "app_image_pull_policy" {
  type        = string
  default     = "if-not-present"
  description = "Image pull policy consumed by the Podman systemd unit: always, if-not-present, or never."
  validation {
    condition     = contains(["always", "if-not-present", "never"], var.app_image_pull_policy)
    error_message = "app_image_pull_policy must be always, if-not-present, or never."
  }
}

variable "shop_container_uid" {
  type        = number
  default     = 10001
  description = "Linux UID used by the Shop container image. Used to grant read access to the ATP wallet."
}

variable "shop_container_gid" {
  type        = number
  default     = 10001
  description = "Linux GID used by the Shop container image. Used to grant read access to the ATP wallet."
}

variable "crm_container_uid" {
  type        = number
  default     = 1000
  description = "Linux UID used by the CRM container image. Used to grant read access to the ATP wallet."
}

variable "crm_container_gid" {
  type        = number
  default     = 1000
  description = "Linux GID used by the CRM container image. Used to grant read access to the ATP wallet."
}

variable "ocir_registry" {
  type        = string
  default     = ""
  description = "Optional OCIR registry, e.g. eu-frankfurt-1.ocir.io."
}

variable "ocir_username" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional OCIR username for private image pulls."
}

variable "ocir_auth_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional OCIR auth token for private image pulls."
}

variable "internal_service_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Shared service key for Shop/CRM internal API calls. Required when enable_first_boot_deploy=true."
}

variable "auth_token_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Shop auth token signing secret. Required when enable_first_boot_deploy=true."
}

variable "app_secret_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "CRM application secret key. Required when enable_first_boot_deploy=true."
}

variable "bootstrap_admin_password" {
  type        = string
  default     = ""
  sensitive   = true
  description = "CRM bootstrap admin password. Required when enable_first_boot_deploy=true."
}

variable "oracle_dsn" {
  type        = string
  default     = "octoatp_low"
  description = "TNS alias in the generated ATP wallet."
}

variable "shop_private_service_url" {
  type        = string
  default     = ""
  description = "Optional private URL CRM uses to reach Shop. Empty uses the created VCN DNS name."
}

variable "crm_private_service_url" {
  type        = string
  default     = ""
  description = "Optional private URL Shop uses to reach CRM. Empty uses the created VCN DNS name."
}

variable "oci_genai_endpoint" {
  type        = string
  default     = ""
  description = "Optional OCI GenAI inference endpoint used by the Drone Shop assistant."
}

variable "oci_genai_model_id" {
  type        = string
  default     = ""
  description = "Optional OCI GenAI model ID used by the Drone Shop assistant."
}

variable "llmetry_capture_content" {
  type        = bool
  default     = false
  description = "When true, export redacted assistant prompt/response previews. Default false stores only hashes, lengths, and token counts."
}

variable "langfuse_enabled" {
  type        = bool
  default     = false
  description = "Enable optional Langfuse OTLP export for assistant LLMetry when project keys are supplied."
}

variable "langfuse_host" {
  type        = string
  default     = ""
  description = "Optional Langfuse base URL for OTLP export, for example https://langfuse.example.test."
}

variable "langfuse_project_name" {
  type        = string
  default     = ""
  description = "Optional logical project name attached to assistant LLMetry spans/logs. Empty derives from the Shop public hostname."
}

variable "langfuse_public_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional Langfuse project public key for OTLP export."
}

variable "langfuse_secret_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional Langfuse project secret key for OTLP export."
}

variable "dns_domain" {
  type        = string
  description = "Base DNS domain. Public hosts are shop.<domain> and crm.<domain>."
}

variable "shop_hostname" {
  type        = string
  default     = ""
  description = "Optional full public hostname for Drone Shop. Empty uses shop.<dns_domain>."
}

variable "crm_hostname" {
  type        = string
  default     = ""
  description = "Optional full public hostname for Enterprise CRM. Empty uses crm.<dns_domain>."
}

variable "create_dns_records" {
  type        = bool
  default     = false
  description = "Create A records for the resolved Shop and CRM hostnames pointing at the Load Balancer public IP."
}

variable "create_compute_instance_principal_policies" {
  type        = bool
  default     = true
  description = "Create the tenancy-level dynamic group and compartment policy used by Compute instance principals. Disable when the operator lacks tenancy IAM privileges and install wallets/secrets manually."
}

variable "dns_zone_name_or_id" {
  type        = string
  default     = ""
  description = "OCI DNS public zone name or OCID used when create_dns_records=true."
}

variable "dns_record_ttl" {
  type        = number
  default     = 60
  description = "TTL for created Shop/CRM DNS A records."
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key installed on both Compute instances."
}

variable "availability_domain_name" {
  type        = string
  default     = ""
  description = "Optional AD name. Empty uses the first AD returned by OCI."
}

variable "shop_availability_domain_name" {
  type        = string
  default     = ""
  description = "Optional AD override for the Shop instance. Empty uses availability_domain_name or the first AD returned by OCI."
}

variable "crm_availability_domain_name" {
  type        = string
  default     = ""
  description = "Optional AD override for the CRM instance. Empty uses availability_domain_name or the first AD returned by OCI."
}

variable "instance_image_ocid" {
  type        = string
  default     = ""
  description = "Oracle Linux image OCID for the Compute instances. Empty discovers the latest Oracle Linux image matching instance_shape."
}

variable "instance_operating_system" {
  type        = string
  default     = "Oracle Linux"
  description = "Operating system used when instance_image_ocid is empty."
}

variable "instance_operating_system_version" {
  type        = string
  default     = "9"
  description = "Operating system version used when instance_image_ocid is empty."
}

variable "instance_shape" {
  type    = string
  default = "VM.Standard.E5.Flex"
}

variable "instance_ocpus" {
  type    = number
  default = 2
}

variable "instance_memory_gbs" {
  type    = number
  default = 16
}

variable "boot_volume_size_gbs" {
  type        = number
  default     = 500
  description = "Boot volume size for each application VM. Keep at least 500 GB for local image builds, APM agents, logs, and demo data."

  validation {
    condition     = var.boot_volume_size_gbs >= 500
    error_message = "boot_volume_size_gbs must be at least 500."
  }
}

variable "vcn_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "create_network" {
  type        = bool
  default     = true
  description = "Create a new VCN with public LB, private app, and private DB subnets plus gateways, routes, security lists, and NSGs."
}

variable "existing_vcn_id" {
  type        = string
  default     = ""
  description = "Existing VCN OCID used when create_network=false."
}

variable "existing_lb_subnet_id" {
  type        = string
  default     = ""
  description = "Existing public subnet OCID for the OCI Load Balancer when create_network=false. Must route to an Internet Gateway."
}

variable "existing_public_subnet_id" {
  type        = string
  default     = ""
  description = "Deprecated alias for existing_lb_subnet_id, kept for older Resource Manager forms."
}

variable "existing_app_private_subnet_id" {
  type        = string
  default     = ""
  description = "Existing private app subnet OCID for the Shop and CRM instances when create_network=false."
}

variable "existing_db_private_subnet_id" {
  type        = string
  default     = ""
  description = "Existing private DB subnet OCID for the ATP private endpoint when create_network=false. Empty falls back to existing_app_private_subnet_id."
}

variable "public_lb_subnet_cidr" {
  type        = string
  default     = "10.42.10.0/24"
  description = "CIDR for the public Load Balancer subnet when create_network=true."
}

variable "public_subnet_cidr" {
  type        = string
  default     = "10.42.10.0/24"
  description = "Deprecated alias retained for docs/tests; use public_lb_subnet_cidr."
}

variable "app_private_subnet_cidr" {
  type        = string
  default     = "10.42.20.0/24"
  description = "CIDR for the private app subnet when create_network=true."
}

variable "db_private_subnet_cidr" {
  type        = string
  default     = "10.42.30.0/24"
  description = "CIDR for the private DB subnet when create_network=true."
}

variable "app_private_cidr" {
  type        = string
  default     = "10.42.20.0/24"
  description = "Existing private app subnet CIDR used for security rules when create_network=false."
}

variable "existing_db_private_cidr" {
  type        = string
  default     = ""
  description = "Existing private DB subnet CIDR used for security-list rules when create_network=false. Empty falls back to app_private_cidr."
}

variable "create_service_gateway" {
  type        = bool
  default     = true
  description = "Create a Service Gateway route for private OCI service access used by agents, Stack Monitoring, OPSI, DB Management, OCIR, and Logging."
}

variable "admin_ssh_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs allowed to SSH to the instances. Keep empty until your admin IP is known."
}

variable "public_web_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "admin_web_cidrs" {
  type        = list(string)
  default     = []
  description = "Optional CIDRs used by the WAF policy for future admin-path rules."
}

variable "create_load_balancer" {
  type        = bool
  default     = true
  description = "Create the public OCI Load Balancer in front of the private Shop and CRM instances."
}

variable "enable_lb_http" {
  type        = bool
  default     = true
  description = "Create an HTTP listener on the public Load Balancer. Keep enabled for first smoke tests or redirect later at the edge."
}

variable "enable_lb_https" {
  type        = bool
  default     = false
  description = "Create an HTTPS listener on the public Load Balancer. Requires lb_certificate_public_certificate and lb_certificate_private_key."
}

variable "lb_shape" {
  type        = string
  default     = "flexible"
  description = "OCI Load Balancer shape."
}

variable "lb_min_bandwidth_mbps" {
  type    = number
  default = 10
}

variable "lb_max_bandwidth_mbps" {
  type    = number
  default = 100
}

variable "lb_delete_protection_enabled" {
  type        = bool
  default     = false
  description = "Enable delete protection on the public Load Balancer after the demo is stable."
}

variable "lb_certificate_public_certificate" {
  type        = string
  default     = ""
  sensitive   = true
  description = "PEM public certificate chain for the optional HTTPS Load Balancer listener."
}

variable "lb_certificate_private_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "PEM private key for the optional HTTPS Load Balancer listener."
}

variable "lb_certificate_ca_certificate" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional PEM CA certificate chain for the Load Balancer certificate."
}

variable "lb_certificate_passphrase" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional private key passphrase for the Load Balancer certificate."
}

variable "enable_waf" {
  type        = bool
  default     = true
  description = "Attach OCI Web Application Firewall to the public Load Balancer."
}

variable "waf_mode" {
  type        = string
  default     = "DETECTION"
  description = "OCI WAF mode: DETECTION or BLOCK. Use DETECTION until normal traffic has been observed."
  validation {
    condition     = contains(["DETECTION", "BLOCK"], upper(var.waf_mode))
    error_message = "waf_mode must be DETECTION or BLOCK."
  }
}

variable "enable_waf_logging" {
  type        = bool
  default     = true
  description = "Create a WAF service log for the Load Balancer WAF attachment."
}

variable "atp_admin_password" {
  type        = string
  sensitive   = true
  description = "ATP ADMIN password. Stored in Terraform state by OCI provider requirements."
  validation {
    condition     = length(var.atp_admin_password) >= 12 && length(var.atp_admin_password) <= 30
    error_message = "atp_admin_password must be 12-30 chars."
  }
}

variable "atp_wallet_password" {
  type        = string
  sensitive   = true
  description = "Password used when OCI generates the ATP wallet zip."
  validation {
    condition     = length(var.atp_wallet_password) >= 8
    error_message = "atp_wallet_password must be at least 8 chars."
  }
}

variable "atp_compute_count" {
  type        = number
  default     = 2
  description = "ATP ECPU count for the dedicated Autonomous Transaction Processing database."
  validation {
    condition     = var.atp_compute_count >= 2
    error_message = "atp_compute_count must be at least 2 ECPUs."
  }
}

variable "atp_storage_size_gbs" {
  type        = number
  default     = 20
  description = "ATP storage size in GB. Use 0 to fall back to the module TB-sized default."
  validation {
    condition     = var.atp_storage_size_gbs == 0 || var.atp_storage_size_gbs >= 20
    error_message = "atp_storage_size_gbs must be 0 or at least 20."
  }
}

variable "atp_auto_scaling_enabled" {
  type        = bool
  default     = true
  description = "Enable ATP ECPU auto scaling."
}

variable "atp_whitelisted_ips" {
  type        = list(string)
  default     = []
  description = "Optional ATP CIDR allowlist for public endpoints. Ignored by the compute stack because ATP uses a private endpoint."
}

variable "atp_private_endpoint_label" {
  type        = string
  default     = "octoatp"
  description = "DNS label for the ATP private endpoint."
}

variable "enable_database_management" {
  type        = bool
  default     = true
  description = "Enable OCI Database Management for the ATP when supported in the target tenancy."
}

variable "enable_operations_insights" {
  type        = bool
  default     = true
  description = "Enable OCI Operations Insights for the ATP when supported in the target tenancy."
}

variable "enable_database_management_private_endpoint" {
  type        = bool
  default     = true
  description = "Create a Database Management private endpoint in the DB subnet."
}

variable "enable_operations_insights_private_endpoint" {
  type        = bool
  default     = true
  description = "Create an Operations Insights private endpoint in the DB subnet."
}

variable "create_apm_domain" {
  type    = bool
  default = true
}

variable "logging_retention_days" {
  type    = number
  default = 30
  validation {
    condition     = var.logging_retention_days >= 1 && var.logging_retention_days <= 180
    error_message = "logging_retention_days must be 1-180."
  }
}

variable "enable_log_analytics" {
  type        = bool
  default     = false
  description = "Create Service Connector Hub pipelines from OCI Logging into Log Analytics. Requires an onboarded Log Analytics namespace or existing LA log group."
}

variable "enable_log_analytics_connectors" {
  type        = bool
  default     = true
  description = "Create Service Connector Hub routes into Log Analytics when enable_log_analytics=true. Disable when service-connector-count quota is exhausted but the LA log group should still be created."
}

variable "create_log_analytics_namespace" {
  type        = bool
  default     = false
  description = "Onboard the tenancy to OCI Log Analytics with log_analytics_namespace when enable_log_analytics=true."
}

variable "log_analytics_namespace" {
  type        = string
  default     = ""
  description = "Log Analytics namespace used when creating the OCTO Log Analytics log group."
}

variable "existing_log_analytics_log_group_id" {
  type        = string
  default     = ""
  description = "Existing Log Analytics log group OCID. If empty and enable_log_analytics=true, the stack creates one using log_analytics_namespace."
}

variable "enable_stack_monitoring_standard" {
  type        = bool
  default     = true
  description = "Enable Stack Monitoring Standard license auto-assignment and HOST auto-promotion for the Compute instances."
}

variable "enable_stack_monitoring_configs" {
  type        = bool
  default     = true
  description = "Create Stack Monitoring Standard license auto-assign and HOST auto-promote configs. Disable when the tenancy already has these configs or the operator lacks config privileges."
}

variable "enable_stack_monitoring_agent_plugin" {
  type        = bool
  default     = true
  description = "Deploy the OCI Management Agent Stack Monitoring plugin to both Compute hosts. Required for host auto-promote to produce Stack Monitoring host telemetry."
}

variable "enable_unified_agent_log_collection" {
  type        = bool
  default     = true
  description = "Create OCI Logging unified-agent configs for host and container logs. Requires create_compute_instance_principal_policies=true because the configs target the dynamic group."
}

variable "enable_stack_monitoring_host_registration" {
  type        = bool
  default     = false
  description = "Create Stack Monitoring host resources explicitly instead of relying only on HOST auto-promote. Requires tenant entitlement for host monitored-resource creation; leave false if OCI returns 'Tenant is not permitted'."
}

variable "enable_stack_monitoring_atp_registration" {
  type        = bool
  default     = false
  description = "Register the ATP as a Stack Monitoring database resource. Requires tenant entitlement for database monitored resources; keep false when OCI returns 'Tenant is not permitted'."
}

variable "stack_monitoring_atp_management_agent_id" {
  type        = string
  default     = ""
  description = "Optional existing OCI Management Agent OCID used to register the ATP in Stack Monitoring. Leave empty to wait for the shop Compute host's Management Agent."
}

variable "management_agent_wait_seconds" {
  type        = number
  default     = 1800
  description = "Seconds Terraform should wait for the first Compute host Management Agent to register before creating the ATP Stack Monitoring resource."
  validation {
    condition     = var.management_agent_wait_seconds >= 300 && var.management_agent_wait_seconds <= 3600
    error_message = "management_agent_wait_seconds must be between 300 and 3600."
  }
}

variable "management_agent_initial_wait_seconds" {
  type        = number
  default     = 180
  description = "Initial delay after Compute creation before Terraform queries Management Agent inventory. This avoids OCI eventual-consistency races during a one-shot Resource Manager apply."
  validation {
    condition     = var.management_agent_initial_wait_seconds >= 0 && var.management_agent_initial_wait_seconds <= 900
    error_message = "management_agent_initial_wait_seconds must be between 0 and 900."
  }
}

variable "create_stack_monitoring_secrets" {
  type        = bool
  default     = false
  description = "Create OCI Vault secrets for ATP Stack Monitoring wallet and DB credentials when existing secret OCIDs are not supplied."
}

variable "stack_monitoring_atp_ssl_secret_id" {
  type        = string
  default     = ""
  description = "Existing OCI Vault secret OCID containing the ATP wallet zip for Stack Monitoring TCPS. Leave empty to create one."
}

variable "stack_monitoring_atp_db_user_secret_id" {
  type        = string
  default     = ""
  description = "Existing OCI Vault secret OCID containing the ATP DB username for Stack Monitoring. Leave empty to create one."
}

variable "stack_monitoring_atp_db_password_secret_id" {
  type        = string
  default     = ""
  description = "Existing OCI Vault secret OCID containing the ATP DB password for Stack Monitoring. Leave empty to create one."
}

variable "stack_monitoring_vault_dns_wait_seconds" {
  type        = number
  default     = 600
  description = "Delay after creating the Stack Monitoring Vault before creating the KMS key, to allow the regional vault management endpoint DNS name to propagate."
  validation {
    condition     = var.stack_monitoring_vault_dns_wait_seconds >= 0 && var.stack_monitoring_vault_dns_wait_seconds <= 600
    error_message = "stack_monitoring_vault_dns_wait_seconds must be between 0 and 600."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
