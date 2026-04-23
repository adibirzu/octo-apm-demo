from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_unified_deploy_wrapper_exists() -> None:
    deploy_wrapper = ROOT / "deploy/deploy.sh"
    assert deploy_wrapper.exists(), "root unified deploy wrapper is missing"
    wrapper_text = deploy_wrapper.read_text(encoding="utf-8")
    assert "deploy-shop.sh" in wrapper_text
    assert "deploy-crm.sh" in wrapper_text


def test_bootstrap_uses_declared_ingress_service_port() -> None:
    bootstrap = read_text("deploy/bootstrap.sh")
    assert "number: ${port}" in bootstrap


def test_root_oke_manifests_use_shop_and_crm_hostnames() -> None:
    shop_manifest = read_text("deploy/k8s/oke/shop/deployment.yaml")
    crm_manifest = read_text("deploy/k8s/oke/crm/deployment.yaml")

    assert 'https://crm.${DNS_DOMAIN}' in shop_manifest
    assert 'https://shop.${DNS_DOMAIN}' in shop_manifest
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
    deploy_oke = read_text("deploy/oke/deploy-oke.sh")
    wizard_cli = read_text("deploy/wizard/src/octo_wizard/cli.py")
    current_status = read_text("site/operations/current-status.md")

    assert "DNS_DOMAIN=cyber-sec.ro" in deploy_wrapper
    assert "DNS_BASE_DOMAIN=cyber-sec.ro" in bootstrap
    assert "DNS_DOMAIN=cyber-sec.ro" in deploy_oke
    assert "cyber-sec.ro" in wizard_cli
    assert "shop.cyber-sec.ro" in current_status
    assert "crm.cyber-sec.ro" in current_status
    assert "Wix" in current_status
