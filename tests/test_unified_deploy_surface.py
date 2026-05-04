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
    assert 'default     = "shop.example.cloud"' in terraform_variables
    assert 'default     = "crm.example.cloud"' in terraform_variables


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

    assert "DNS_DOMAIN=cyber-sec.ro" in deploy_wrapper
    assert "DNS_BASE_DOMAIN=cyber-sec.ro" in bootstrap
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
    assert "DNS_DOMAIN=cyber-sec.ro" in deploy_oke
    assert "DNS_DOMAIN=cyber-sec.ro" in deployment_doc
    assert "deploy/bootstrap.sh" in new_tenancy
    assert "deploy/init-tenancy.sh" in new_tenancy
    assert "CROSS_SERVICE_E2E_ENABLED=1" in e2e_doc
    assert "SSO_E2E_ENABLED=1" in e2e_doc
    assert "FULL_PLATFORM_E2E_ENABLED=1" in e2e_doc
    assert "shop.cyber-sec.ro" in e2e_doc
    assert "crm.cyber-sec.ro" in e2e_doc
    assert "helm template" in deploy_readiness
    assert "helm lint" in deploy_readiness
    assert "cyber-sec.ro" in wizard_cli
    assert "shop.cyber-sec.ro" in readme
    assert "crm.cyber-sec.ro" in readme
    assert "shop.cyber-sec.ro" in site_index
    assert "crm.cyber-sec.ro" in site_index
    assert "shop.cyber-sec.ro" in current_status
    assert "crm.cyber-sec.ro" in current_status
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

    parsed = urlparse(RESOURCE_MANAGER_BUTTON_URL)
    assert parsed.scheme == "https"
    assert parsed.netloc == "cloud.oracle.com"
    assert parsed.path == "/resourcemanager/stacks/create"
    assert parse_qs(parsed.query)["zipUrl"] == [RESOURCE_MANAGER_ZIP_URL]

    for text in (readme, resource_manager_readme, deployment_options):
        assert "Deploy to Oracle Cloud" in text
        assert RESOURCE_MANAGER_BUTTON_URL in text

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

    assert "https://shop.cyber-sec.ro" in traffic_config
    assert "https://crm.cyber-sec.ro" in traffic_config
    assert "shop.${DNS_DOMAIN}" in load_control_profiles
    assert "crm.${DNS_DOMAIN}" in load_control_profiles
    assert "enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080" in load_control_api
    assert "enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080" in load_control_k8s
    assert "workflow-gateway.octo-drone-shop.svc.cluster.local:9090" in otel_gateway
    assert "http://enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080" in platform_status
    assert "--namespace octo-drone-shop" in rollout_validator
    assert "octo-drone-shop" in remediator_scale
    assert "octo-drone-shop" in remediator_restart

    assert "drone.octodemo.cloud" not in combined
    assert "backend.octodemo.cloud" not in combined
    assert "api.drone.octodemo.cloud" not in combined
    assert "octo-shop-prod" not in combined
    assert "octo-backend-prod" not in combined
