from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_oke_langfuse_assets_exist() -> None:
    assert (ROOT / "deploy/oke/deploy-langfuse.sh").exists()
    assert (ROOT / "deploy/oke/langfuse/README.md").exists()
    assert (ROOT / "deploy/k8s/oke/langfuse/langfuse.yaml").exists()


def test_oke_langfuse_script_enforces_project_vcn_and_checks_rights() -> None:
    script = _read("deploy/oke/deploy-langfuse.sh")

    assert "TARGET_VCN_ID" in script
    assert "ALLOW_DIFFERENT_VCN" in script
    assert '."vcn-id"==$vcn' in script
    assert "kubectl auth can-i create deployments" in script
    assert "kubectl auth can-i create persistentvolumeclaims" in script
    assert "OCI_CLI_CONNECTION_TIMEOUT" in script
    assert "oci_cmd ce cluster create-kubeconfig" in script
    assert "No ACTIVE OKE cluster was found in TARGET_VCN_ID" in script


def test_oke_langfuse_manifest_is_low_resource_and_observable() -> None:
    manifest = _read("deploy/k8s/oke/langfuse/langfuse.yaml")

    for workload in [
        "langfuse-web",
        "langfuse-worker",
        "langfuse-postgres",
        "langfuse-clickhouse",
        "langfuse-redis",
        "langfuse-minio",
    ]:
        assert workload in manifest

    assert 'app.kubernetes.io/part-of: octo-demo-observability' in manifest
    assert 'prometheus.io/scrape: "true"' in manifest
    assert 'service.beta.kubernetes.io/oci-load-balancer-shape-flex-min: "${OCI_LB_SHAPE_FLEX_MIN}"' in manifest
    assert 'service.beta.kubernetes.io/oci-load-balancer-shape-flex-max: "${OCI_LB_SHAPE_FLEX_MAX}"' in manifest
    assert 'cpu: "250m"' in manifest
    assert 'memory: "512Mi"' in manifest
    assert 'NODE_OPTIONS: "--max-old-space-size=512"' in manifest
    assert 'LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: "langfuse"' in manifest
    assert 'value: "UTC"' in manifest
    assert 'storage: "${LANGFUSE_CLICKHOUSE_STORAGE}"' in manifest
    assert "NetworkPolicy" in manifest
    assert "/api/public/health" in manifest


def test_oke_shop_can_receive_langfuse_project_name_secret() -> None:
    shop = _read("deploy/k8s/oke/shop/deployment.yaml")

    assert "LANGFUSE_PROJECT_NAME" in shop
    assert "langfuse-project-name" in shop
