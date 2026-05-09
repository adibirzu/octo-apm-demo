import subprocess
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_MANAGER_ZIP_URL = "https://github.com/adibirzu/octo-apm-demo/releases/download/resource-manager-stack/octo-stack.zip"
RESOURCE_MANAGER_BUTTON_URL = (
    "https://cloud.oracle.com/resourcemanager/stacks/create"
    f"?zipUrl={RESOURCE_MANAGER_ZIP_URL}"
)
COMPUTE_RESOURCE_MANAGER_ZIP_URL = (
    "https://github.com/adibirzu/octo-apm-demo/releases/download/"
    "compute-resource-manager-stack-20260504/octo-compute-stack.zip"
)
COMPUTE_RESOURCE_MANAGER_BUTTON_URL = (
    "https://cloud.oracle.com/resourcemanager/stacks/create"
    f"?zipUrl={COMPUTE_RESOURCE_MANAGER_ZIP_URL}"
)


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_unified_deploy_wrapper_exists() -> None:
    deploy_wrapper = ROOT / "deploy/deploy.sh"
    assert deploy_wrapper.exists(), "root unified deploy wrapper is missing"
    wrapper_text = deploy_wrapper.read_text(encoding="utf-8")
    assert "deploy-shop.sh" in wrapper_text
    assert "deploy-crm.sh" in wrapper_text
    assert '"app"' in wrapper_text


def test_bootstrap_uses_declared_ingress_service_port() -> None:
    bootstrap = read_text("deploy/bootstrap.sh")
    assert "number: ${port}" in bootstrap


def test_root_oke_manifests_use_shop_and_crm_hostnames() -> None:
    shop_manifest = read_text("deploy/k8s/oke/shop/deployment.yaml")
    crm_manifest = read_text("deploy/k8s/oke/crm/deployment.yaml")

    assert 'https://crm.${DNS_DOMAIN}' in shop_manifest
    assert 'shop.${DNS_DOMAIN}' in shop_manifest
    assert (
        'http://enterprise-crm-portal.${K8S_NAMESPACE_CRM}.svc.cluster.local:8080'
        in shop_manifest
    )

    assert 'https://crm.${DNS_DOMAIN}' in crm_manifest
    assert (
        'http://octo-drone-shop.${K8S_NAMESPACE_SHOP}.svc.cluster.local:8080'
        in crm_manifest
    )

    combined = shop_manifest + crm_manifest
    assert "imagePullSecrets:" in shop_manifest
    assert "imagePullSecrets:" in crm_manifest
    assert "name: ocir-pull-secret" in combined
    assert "backend.${DNS_DOMAIN}" not in combined
    assert "drone.${DNS_DOMAIN}" not in combined


def test_resource_manager_and_root_tf_defaults_match_live_host_pattern() -> None:
    resource_manager_variables = read_text("deploy/resource-manager/variables.tf")
    terraform_variables = read_text("deploy/terraform/variables.tf")

    assert 'default = "shop.example.invalid"' in resource_manager_variables
    assert 'default = "crm.example.invalid"' in resource_manager_variables
    assert 'default     = "shop.example.test"' in terraform_variables
    assert 'default     = "crm.example.test"' in terraform_variables


def test_oke_assets_use_unified_namespaces_and_hostnames() -> None:
    deploy_oke = read_text("deploy/oke/deploy-oke.sh")
    namespaces = read_text("deploy/k8s/oke/common/namespaces.yaml")
    network_policies = read_text("deploy/k8s/oke/common/network-policies.yaml")

    assert "octo-drone-shop" in namespaces
    assert "enterprise-crm" in namespaces
    assert "octo-shop-prod" not in namespaces
    assert "octo-backend-prod" not in namespaces

    combined = deploy_oke + network_policies
    assert "drone.${DNS_DOMAIN}" not in combined
    assert "backend.${DNS_DOMAIN}" not in combined


def test_default_profile_docs_and_examples_target_cyber_sec_ro() -> None:
    deploy_wrapper = read_text("deploy/deploy.sh")
    bootstrap = read_text("deploy/bootstrap.sh")
    destroy = read_text("deploy/destroy.sh")
    deploy_crm = read_text("deploy/deploy-crm.sh")
    deploy_readiness = read_text("site/operations/deploy-readiness.md")
    deployment_doc = read_text("site/operations/deployment.md")
    e2e_doc = read_text("site/testing/e2e.md")
    init_tenancy = read_text("deploy/init-tenancy.sh")
    ensure_apm = read_text("deploy/oci/ensure_apm.sh")
    ensure_stack_monitoring = read_text("deploy/oci/ensure_stack_monitoring.sh")
    deploy_oke = read_text("deploy/oke/deploy-oke.sh")
    new_tenancy = read_text("site/getting-started/new-tenancy.md")
    readme = read_text("README.md")
    site_index = read_text("site/index.md")
    wizard_cli = read_text("deploy/wizard/src/octo_wizard/cli.py")
    current_status = read_text("site/operations/current-status.md")

    assert "DNS_DOMAIN=example.test" in deploy_wrapper
    assert "DNS_BASE_DOMAIN=example.test" in bootstrap
    assert "CERTIFICATE_CONTENT_WITH_PRIVATE_KEY" in bootstrap
    assert "TLS_SECRET_NAME" in bootstrap
    assert "HTTPS" in bootstrap
    assert "--delete-shared-ingress" in destroy
    assert "Shared ingress controller is preserved by default." in destroy
    assert "OCI_LOG_CHAOS_AUDIT_ID" in init_tenancy
    assert "OCI_LOG_SECURITY_ID" in init_tenancy
    assert "print_apm_exports" in ensure_apm
    assert "stack-monitoring resource create" in ensure_stack_monitoring
    assert "MANAGEMENT_AGENT_ID" in ensure_stack_monitoring
    assert 'CONTAINER="${K8S_CONTAINER:-app}"' in deploy_crm
    assert 'SERVICE_SHOP_URL="${SERVICE_SHOP_URL:-http://octo-drone-shop.' in deploy_crm
    assert "DNS_DOMAIN=example.test" in deploy_oke
    assert "DNS_DOMAIN=example.test" in deployment_doc
    assert "deploy/bootstrap.sh" in new_tenancy
    assert "deploy/init-tenancy.sh" in new_tenancy
    assert "CROSS_SERVICE_E2E_ENABLED=1" in e2e_doc
    assert "SSO_E2E_ENABLED=1" in e2e_doc
    assert "FULL_PLATFORM_E2E_ENABLED=1" in e2e_doc
    assert "shop.example.test" in e2e_doc
    assert "crm.example.test" in e2e_doc
    assert "helm template" in deploy_readiness
    assert "helm lint" in deploy_readiness
    assert "example.test" in wizard_cli
    assert "shop.example.test" in readme
    assert "crm.example.test" in readme
    assert "shop.example.test" in site_index
    assert "crm.example.test" in site_index
    assert "shop.example.test" in current_status
    assert "crm.example.test" in current_status
    assert "octo-apm-demo-atp" in current_status
    assert "deploy.sh" in current_status


def test_bootstrap_detects_external_dns_authority_and_falls_back_to_manual() -> None:
    bootstrap = read_text("deploy/bootstrap.sh")

    assert "dig +short NS" in bootstrap
    assert "Public delegation for ${DNS_BASE_DOMAIN} is not using the OCI DNS zone." in bootstrap
    assert "Switching effective DNS mode to manual." in bootstrap
    assert "terraform -chdir=\"${SCRIPT_DIR}/terraform\" output -json \"${output_name}\"" in bootstrap
    assert "log_group_id" in bootstrap
    assert '|| "${code}" == "308"' in bootstrap


def test_service_rollouts_can_verify_via_ingress_ip_before_dns_cutover() -> None:
    deploy_shop = read_text("deploy/deploy-shop.sh")
    deploy_crm = read_text("deploy/deploy-crm.sh")

    for script in (deploy_shop, deploy_crm):
        assert "--resolve" in script
        assert "Verifying via ingress IP" in script
        assert "ingress-nginx-controller" in script


def test_verify_script_renders_helm_templates_instead_of_parsing_go_templates_raw() -> None:
    verify = read_text("deploy/verify.sh")

    assert "Script help" in verify
    assert "--help" in verify
    assert "Resource Manager stack package" in verify
    assert "stack-package.sh" in verify
    assert "terraform -chdir=\"${rm_stack_tmp}\" init -backend=false" in verify
    assert "terraform -chdir=\"${rm_stack_tmp}\" validate" in verify
    assert "helm template octo-apm-demo" in verify
    assert "helm lint" in verify
    assert "secrets.create=true" in verify
    assert "kubectl apply --dry-run=client" in verify
    assert 'deploy/helm/*/templates/*' in verify
    assert "terraform validate" in verify
    assert "deploy/wizard/tests/test_plan.py" in verify
    assert "services/load-control" in verify


def test_deploy_scripts_show_help_without_running_preflight() -> None:
    scripts = sorted((ROOT / "deploy").rglob("*.sh"))
    assert scripts

    for script in scripts:
        result = subprocess.run(
            ["bash", str(script), "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
            check=False,
        )

        assert result.returncode == 0, f"{script.relative_to(ROOT)} --help failed:\n{result.stdout}"
        assert "Usage:" in result.stdout, f"{script.relative_to(ROOT)} --help did not print usage"


def test_resource_manager_deploy_button_and_docs_publish_zip_url() -> None:
    readme = read_text("README.md")
    resource_manager_readme = read_text("deploy/resource-manager/README.md")
    deployment_options = read_text("site/getting-started/deployment-options.md")
    compute_readme = read_text("deploy/compute/README.md")
    compute_doc = read_text("site/getting-started/compute-deployment.md")

    parsed = urlparse(RESOURCE_MANAGER_BUTTON_URL)
    assert parsed.scheme == "https"
    assert parsed.netloc == "cloud.oracle.com"
    assert parsed.path == "/resourcemanager/stacks/create"
    assert parse_qs(parsed.query)["zipUrl"] == [RESOURCE_MANAGER_ZIP_URL]

    for text in (readme, resource_manager_readme, deployment_options):
        assert "Deploy to Oracle Cloud" in text
        assert RESOURCE_MANAGER_BUTTON_URL in text

    for text in (readme, compute_readme, compute_doc, deployment_options):
        assert "Deploy Full Compute Stack to Oracle Cloud" in text or "Deploy Full Private Compute Stack to Oracle Cloud" in text
        assert COMPUTE_RESOURCE_MANAGER_BUTTON_URL in text

    workflow_path = ROOT / ".github/workflows/resource-manager-stack.yml"
    if workflow_path.exists():
        release_workflow = workflow_path.read_text(encoding="utf-8")
        assert "deploy/resource-manager/**" in release_workflow
        assert "deploy/terraform/**" in release_workflow
        assert "./deploy/resource-manager/stack-package.sh" in release_workflow
        assert "resource-manager-stack" in release_workflow
        assert "gh release upload" in release_workflow
        assert "octo-stack.zip" in release_workflow


def test_resource_manager_package_is_self_contained() -> None:
    subprocess.run(
        ["bash", "deploy/resource-manager/stack-package.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=True,
    )

    stack_zip = ROOT / "deploy/resource-manager/build/octo-stack.zip"
    with zipfile.ZipFile(stack_zip) as package:
        names = set(package.namelist())
        main_tf = package.read("main.tf").decode("utf-8")

    assert {"main.tf", "variables.tf", "schema.yaml", "modules-shared/main.tf"} <= names
    assert any(name.startswith("modules-shared/modules/waf/") for name in names)
    assert any(name.startswith("modules-shared/modules/apm_domain/") for name in names)
    assert "modules-shared/backend.tf" not in names
    assert 'source = "./modules-shared"' in main_tf
    assert 'source = "../terraform"' not in main_tf


def test_compute_resource_manager_package_is_self_contained() -> None:
    subprocess.run(
        ["bash", "deploy/compute/stack-package.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=True,
    )

    stack_zip = ROOT / "deploy/compute/build/octo-compute-stack.zip"
    with zipfile.ZipFile(stack_zip) as package:
        names = set(package.namelist())
        main_tf = package.read("main.tf").decode("utf-8")
        provider_tf = package.read("provider.tf").decode("utf-8")
        schema = package.read("schema.yaml").decode("utf-8")

    assert {"main.tf", "variables.tf", "outputs.tf", "schema.yaml", "cloud-init/compute.yaml.tftpl"} <= names
    assert {
        "bootstrap/install.sh",
        "bootstrap/app-compose.yml",
        "bootstrap/runtime.env.template",
        "bootstrap/nginx/app.conf.template",
        "bootstrap/systemd/octo-compute.service",
        "bootstrap/systemd/octo-podman.service",
        "bootstrap/systemd/octo-workflow-gateway.service",
    } <= names
    for module in ("atp", "apm_domain", "logging", "stack_monitoring", "waf"):
        assert any(name.startswith(f"modules-shared/modules/{module}/") for name in names)
    assert 'provider "oci" {}' in provider_tf
    assert 'source = "./modules-shared/modules/' in main_tf
    assert 'source = "../../terraform/modules/' not in main_tf
    assert "existing_app_private_subnet_id" in schema
    assert "enable_waf" in schema
    assert "enable_log_analytics" in schema


def test_helm_chart_avoids_partial_sso_and_validates_managed_secrets() -> None:
    shop_deployment = read_text("deploy/helm/octo-apm-demo/templates/shop-deployment.yaml")
    crm_deployment = read_text("deploy/helm/octo-apm-demo/templates/crm-deployment.yaml")
    secrets_template = read_text("deploy/helm/octo-apm-demo/templates/secrets.yaml")

    combined_deployments = shop_deployment + crm_deployment
    assert "IDCS_REDIRECT_URI" not in combined_deployments
    assert "IDCS_POST_LOGOUT_REDIRECT" not in combined_deployments

    assert "secrets.data.atp.dsn is required when secrets.create=true" in secrets_template
    assert "secrets.data.atp.username is required when secrets.create=true" in secrets_template
    assert "secrets.data.atp.password is required when secrets.create=true" in secrets_template
    assert "secrets.data.atp.walletPassword is required when secrets.create=true" in secrets_template
    assert "secrets.data.auth.internalServiceKey is required when secrets.create=true" in secrets_template
    assert "secrets.atpWallet or secrets.atpWalletB64 is required when secrets.create=true" in secrets_template
    assert "secrets.data.auth.tokenSecret is required when shop.enabled=true" in secrets_template
    assert "secrets.data.ociConfig.compartmentId is required when shop.enabled=true" in secrets_template
    assert "secrets.data.auth.appSecretKey is required when crm.enabled=true" in secrets_template
    assert "secrets.data.auth.bootstrapAdminPassword is required when crm.enabled=true" in secrets_template


def test_bootstrap_normalizes_ocir_pull_secret_username_to_current_namespace() -> None:
    bootstrap = read_text("deploy/bootstrap.sh")
    init_tenancy = read_text("deploy/init-tenancy.sh")

    assert "read_remote_ocir_pull_credentials" in bootstrap
    assert "REMOTE_BUILD_HOST" in bootstrap
    assert "BatchMode=yes" in bootstrap
    assert "ConnectTimeout=5" in bootstrap
    for script in (bootstrap, init_tenancy):
        assert "normalize_ocir_username_namespace" in script
        assert 'expected_namespace="${OCIR_NAMESPACE:-${OCIR_TENANCY:-}}"' in script
        assert 'OCIR_USERNAME="${expected_namespace}/${suffix}"' in script
        assert 'OCIR_USERNAME="${expected_namespace}/${OCIR_USERNAME}"' in script


def test_bootstrap_starts_atp_and_oke_manifests_do_not_partially_configure_sso() -> None:
    bootstrap = read_text("deploy/bootstrap.sh")
    shop_manifest = read_text("deploy/k8s/oke/shop/deployment.yaml")
    crm_manifest = read_text("deploy/k8s/oke/crm/deployment.yaml")

    assert "ensure_autonomous_database_available" in bootstrap
    assert "ATP is STOPPED — starting" in bootstrap
    assert "--wait-for-state AVAILABLE" in bootstrap
    assert "IDCS_REDIRECT_URI" not in shop_manifest
    assert "IDCS_POST_LOGOUT_REDIRECT" not in shop_manifest
    assert "IDCS_REDIRECT_URI" not in crm_manifest


def test_bootstrap_recovers_stopped_managed_workers_before_ingress_apply() -> None:
    bootstrap = read_text("deploy/bootstrap.sh")

    assert "ensure_ingress_controller_ready" in bootstrap
    assert "start_stopped_real_nodes_for_ingress" in bootstrap
    assert "Starting stopped OKE worker" in bootstrap
    assert "oci compute instance action" in bootstrap
    assert "--wait-for-state RUNNING" in bootstrap
    assert "kubectl wait --for=condition=Ready" in bootstrap
    assert "ingress controller service ${service_name} has no endpoints" in bootstrap


def test_unified_wrapper_and_atp_helper_recover_preserved_runtime_dependencies() -> None:
    deploy_wrapper = read_text("deploy/deploy.sh")
    ensure_atp = read_text("deploy/oci/ensure_atp.sh")

    assert "ATP is STOPPED — starting" in deploy_wrapper
    assert "Shared ingress is not healthy." in deploy_wrapper
    assert "ATP is STOPPED — starting" in ensure_atp


def test_platform_service_defaults_and_manifests_follow_shop_crm_contract() -> None:
    load_control_profiles = read_text("services/load-control/src/octo_load_control/profiles.py")
    load_control_executor = read_text("services/load-control/src/octo_load_control/executor.py")
    load_control_api = read_text("services/load-control/src/octo_load_control/api.py")
    load_control_k8s = read_text("services/load-control/k8s/deployment.yaml")
    traffic_config = read_text("tools/traffic-generator/octo_traffic/config.py")
    traffic_k8s = read_text("tools/traffic-generator/k8s/deployment.yaml")
    browser_runner = read_text("services/browser-runner/src/config.ts")
    browser_job = read_text("services/browser-runner/k8s/job.yaml")
    async_worker = read_text("services/async-worker/src/octo_async_worker/config.py")
    async_worker_handler = read_text("services/async-worker/src/octo_async_worker/handlers/order_sync.py")
    async_worker_k8s = read_text("services/async-worker/k8s/deployment.yaml")
    otel_gateway = read_text("services/otel-gateway/config/otel-collector.yaml")
    platform_status = read_text("shop/server/modules/platform_status.py")
    remediator_scale = read_text("services/remediator/src/octo_remediator/playbooks/scale_hpa.py")
    remediator_restart = read_text("services/remediator/src/octo_remediator/playbooks/restart_deployment.py")
    rollout_validator = read_text("tools/rollout-validator/validate.py")

    combined = "\n".join(
        [
            load_control_profiles,
            load_control_executor,
            load_control_api,
            load_control_k8s,
            traffic_config,
            traffic_k8s,
            browser_runner,
            browser_job,
            async_worker,
            async_worker_handler,
            async_worker_k8s,
            otel_gateway,
            platform_status,
            remediator_scale,
            remediator_restart,
            rollout_validator,
        ]
    )

    assert "https://shop.example.test" in traffic_config
    assert "https://crm.example.test" in traffic_config
    assert "shop.${DNS_DOMAIN}" in load_control_profiles
    assert "crm.${DNS_DOMAIN}" in load_control_profiles
    assert "enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080" in load_control_api
    assert "enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080" in load_control_k8s
    assert "workflow-gateway.octo-drone-shop.svc.cluster.local:9090" in otel_gateway
    assert "http://enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080" in platform_status
    assert "--namespace octo-drone-shop" in rollout_validator
    assert "octo-drone-shop" in remediator_scale
    assert "octo-drone-shop" in remediator_restart

    assert "drone.example.test" not in combined
    assert "backend.example.test" not in combined
    assert "api.drone.example.test" not in combined
    assert "octo-shop-prod" not in combined
    assert "octo-backend-prod" not in combined


def test_two_instance_compute_surface_is_offline_validated_and_observable() -> None:
    compute_readme = read_text("deploy/compute/README.md")
    compute_doc = read_text("site/getting-started/compute-deployment.md")
    deployment_options = read_text("site/getting-started/deployment-options.md")
    compute_tf = read_text("deploy/compute/terraform/main.tf")
    compute_outputs = read_text("deploy/compute/terraform/outputs.tf")
    compute_schema = read_text("deploy/compute/terraform/schema.yaml")
    compute_variables = read_text("deploy/compute/terraform/variables.tf")
    compose = read_text("deploy/compute/app-compose.yml")
    deploy_apps = read_text("deploy/compute/deploy-apps.sh")
    install = read_text("deploy/compute/install.sh")
    runtime_template = read_text("deploy/compute/runtime.env.template")
    podman_unit = read_text("deploy/compute/systemd/octo-podman.service")
    docker_unit = read_text("deploy/compute/systemd/octo-compute.service")
    cloud_init = read_text("deploy/compute/terraform/cloud-init/compute.yaml.tftpl")
    stack_package = read_text("deploy/compute/stack-package.sh")
    validate = read_text("deploy/compute/validate.sh")
    deployment_verify = read_text("deploy/compute/verify-deployment.sh")
    verify = read_text("deploy/verify.sh")
    mkdocs = read_text("mkdocs.yml")

    assert "Two-instance Compute" in deployment_options
    assert "getting-started/compute-deployment.md" in mkdocs
    assert "public LB/WAF, private Shop and CRM Compute instances, private ATP" in read_text("README.md")

    assert "oci_core_instance" in compute_tf
    assert "for_each       = local.instances" in compute_tf
    assert "assign_public_ip = false" in compute_tf
    assert "oci_core_subnet\" \"lb_public" in compute_tf
    assert "oci_core_subnet\" \"app_private" in compute_tf
    assert "oci_core_subnet\" \"db_private" in compute_tf
    assert "oci_core_internet_gateway" in compute_tf
    assert "oci_core_nat_gateway" in compute_tf
    assert "oci_core_service_gateway" in compute_tf
    assert "oci_core_route_table\" \"app_private" in compute_tf
    assert "oci_core_security_list\" \"db_private" in compute_tf
    assert "oci_core_network_security_group\" \"lb" in compute_tf
    assert "oci_core_network_security_group\" \"app" in compute_tf
    assert "oci_core_network_security_group\" \"db" in compute_tf
    assert "oci_load_balancer_load_balancer" in compute_tf
    assert "oci_load_balancer_load_balancer_routing_policy" in compute_tf
    assert "oci_waf_web_app_firewall" in compute_tf
    assert "module \"atp\"" in compute_tf
    assert "private_endpoint_label" in compute_tf
    assert "database_management_status" in compute_tf
    assert "operations_insights_status" in compute_tf
    assert "oci_database_management_db_management_private_endpoint" in compute_tf
    assert "oci_opsi_operations_insights_private_endpoint" in compute_tf
    assert "module \"apm_domain\"" in compute_tf
    assert "module \"logging\"" in compute_tf
    assert "oci_log_analytics_log_analytics_log_group" in compute_tf
    assert "oci_sch_service_connector" in compute_tf
    assert "oci_logging_unified_agent_configuration" in compute_tf
    assert "Custom Logs Monitoring" in compute_tf
    assert "Compute Instance Monitoring" in compute_tf
    assert "Management Agent" in compute_tf
    assert 'oci_management_agent_management_agent" "stack_monitoring_plugin' in compute_tf
    assert "enable_stack_monitoring_agent_plugin" in compute_tf
    assert "enable_stack_monitoring_host_registration" in compute_tf
    assert "connectors_enabled" in compute_outputs
    assert "configs_enabled" in compute_outputs
    assert "LICENSE_AUTO_ASSIGN" in compute_tf
    assert "AUTO_PROMOTE" in compute_tf
    assert "crm_admin_username" in compute_outputs
    assert 'output "instance_ids"' in compute_outputs
    assert 'output "deployment_compartment_id"' in compute_outputs
    assert "octo-compute-os" in compute_readme
    assert "octo-compute-app-stdout" in compute_readme
    assert "private app subnet" in compute_readme
    assert "private DB subnet" in compute_readme
    assert "Service Gateway" in compute_readme
    assert "Log Analytics" in compute_readme
    assert "configure-lb-certificate.sh" in compute_readme
    assert "verify-deployment.sh" in compute_readme
    assert "CRM Local Admin Login" in compute_readme

    assert "compute-resource-manager-stack" in stack_package + compute_readme
    assert "octo-compute-stack.zip" in stack_package
    assert "bootstrap/install.sh" in stack_package
    assert "modules/waf" in stack_package
    for key in (
        "create_network",
        "existing_vcn_id",
        "existing_lb_subnet_id",
        "existing_app_private_subnet_id",
        "existing_db_private_subnet_id",
        "shop_availability_domain_name",
        "crm_availability_domain_name",
        "shop_hostname",
        "crm_hostname",
        "create_compute_instance_principal_policies",
        "public_lb_subnet_cidr",
        "app_private_subnet_cidr",
        "db_private_subnet_cidr",
        "enable_log_analytics",
        "enable_log_analytics_connectors",
        "enable_stack_monitoring_agent_plugin",
        "enable_stack_monitoring_configs",
        "enable_unified_agent_log_collection",
        "enable_stack_monitoring_host_registration",
        "boot_volume_size_gbs",
    ):
        assert key in compute_schema

    assert 'default     = 500' in compute_variables
    assert "boot_volume_size_gbs must be at least 500" in compute_variables
    assert "minimum: 500" in compute_schema

    assert "APP_RUNTIME: compute" in compose
    assert "OTEL_TRACES_SAMPLER" in compose
    assert "OCI_APM_PRIVATE_DATAKEY" in compose
    assert "OCI_LOG_ID" in compose
    assert "SHOP_PUBLIC_URL" in compose
    assert "CORS_ALLOWED_ORIGINS" in compose
    assert "WORKFLOW_API_BASE_URL" in compose
    assert "WORKFLOW_PUBLIC_API_BASE_URL" in compose
    assert "SELECTAI_PROFILE_NAME" in compose
    assert "workflow-gateway:" in compose
    assert "CONTAINER_RUNTIME=podman" in runtime_template
    assert "WORKFLOW_GATEWAY_ENABLED=false" in runtime_template
    assert "WORKFLOW_PUBLIC_API_BASE_URL=/api/workflow-gateway" in runtime_template
    assert "CONTAINER_ENV_FILE=/opt/octo/container.env" in runtime_template
    assert "render_container_env_file" in install
    assert "--env-file /opt/octo/container.env" in podman_unit
    assert "octo-workflow-gateway" in read_text("deploy/compute/systemd/octo-workflow-gateway.service")
    assert "--env-file /opt/octo/container.env" in docker_unit
    assert "--env-file /opt/octo/runtime.env" not in podman_unit + docker_unit
    assert "systemd units use container-runtime env file" in validate
    assert "podman" in cloud_init
    assert "compute_bootstrap_files" in compute_tf
    assert "bootstrap/install.sh" in compute_tf
    assert 'var.shop_hostname != "" ? var.shop_hostname : "shop.${var.dns_domain}"' in compute_tf
    assert 'var.crm_hostname != "" ? var.crm_hostname : "crm.${var.dns_domain}"' in compute_tf
    assert 'ignore_changes = [metadata["user_data"]]' in compute_tf
    assert "atp_compute_count" in compute_schema
    assert "SHOP_AVAILABILITY_DOMAIN" in read_text("deploy/compute/check-oci-limits.sh")
    assert "/opt/octo/deploy/compute/install.sh" in cloud_init
    assert "oracleApmTraceId" in compute_doc
    assert "OpenTelemetry as the APM application agent" in compute_doc

    assert "--check" in install
    assert "CONTAINER_RUNTIME" in install
    assert "podman login" in install
    assert "octo-podman.service" in install
    assert "docker compose -f" in install
    assert "ENABLE_HOST_NGINX" in install
    assert "oracle-cloud-agent.service" in install
    assert "$${APP_IMAGE}" in podman_unit
    assert '"${APP_IMAGE}"' not in podman_unit
    assert "configure-lb-certificate.sh" in validate
    assert "verify-deployment.sh" in validate
    assert "deploy-apps.sh" in validate
    assert "terraform -chdir=\"${SCRIPT_DIR}/terraform\" validate" in validate
    assert "Resource Manager package terraform validates" in validate
    assert "deploy/compute/validate.sh" in verify
    assert "Load Balancer backend set" in deployment_verify
    assert "Load Balancer is ACTIVE" in deployment_verify
    assert "Log Analytics Service Connectors are disabled in Terraform outputs" in deployment_verify
    assert "Stack Monitoring HOST auto-promote config is disabled in Terraform outputs" in deployment_verify
    assert "resolves to Load Balancer IP" in deployment_verify
    assert "APM domain is ACTIVE" in deployment_verify
    assert "ATP database is AVAILABLE" in deployment_verify
    assert "Database Management private endpoint is ACTIVE" in deployment_verify
    assert "Operations Insights private endpoint is ACTIVE" in deployment_verify
    assert "Log Analytics Service Connector" in deployment_verify
    assert "Management Agent for" in deployment_verify
    assert "Stack Monitoring HOST auto-promote" in deployment_verify
    assert "--require-https" in deployment_verify
    assert "--skip-dns" in deployment_verify
    assert "--outputs-json" in deployment_verify
    assert "verify-deployment.sh" in compute_doc
    assert "deploy-apps.sh" in compute_doc

    assert "instance-agent command create" in deploy_apps
    assert "command-execution get" in deploy_apps
    assert "--outputs-json" in deploy_apps
    assert "--apply" in deploy_apps
    assert "--role" in deploy_apps
    assert "--shop-instance-id" in deploy_apps
    assert "--crm-instance-id" in deploy_apps
    assert "APP_IMAGE_PULL_POLICY" in deploy_apps
    assert "APP_IMAGE_BUILD_ENABLED" in deploy_apps
    assert "re-executing deployment script with sudo" in deploy_apps
    assert "sudo -n /usr/bin/env bash" in deploy_apps
    assert "/opt/octo/deploy/compute/install.sh --check" in deploy_apps
    assert "systemctl restart octo-compute.service" in deploy_apps
    assert "bootstrap_admin_password" not in deploy_apps.lower()
    assert "OCI_APM_PRIVATE_DATAKEY" not in deploy_apps
