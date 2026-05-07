from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_langfuse_compute_surface_exists() -> None:
    assert (ROOT / "deploy/compute/langfuse/langfuse-compose.yml").exists()
    assert (ROOT / "deploy/compute/langfuse/langfuse.env.template").exists()
    assert (ROOT / "deploy/compute/systemd/octo-langfuse.service").exists()


def test_langfuse_compose_keeps_public_port_separate() -> None:
    compose = (ROOT / "deploy/compute/langfuse/langfuse-compose.yml").read_text(encoding="utf-8")

    assert "langfuse/langfuse:3" in compose
    assert "langfuse/langfuse-worker:3" in compose
    assert "postgres:16" in compose
    assert "clickhouse/clickhouse-server" in compose
    assert "127.0.0.1:${LANGFUSE_WEB_PORT:-33000}:3000" in compose
    assert "8080" not in compose


def test_langfuse_env_template_does_not_commit_secret_values() -> None:
    env_template = (ROOT / "deploy/compute/langfuse/langfuse.env.template").read_text(encoding="utf-8")

    for key in [
        "NEXTAUTH_SECRET",
        "SALT",
        "ENCRYPTION_KEY",
        "POSTGRES_PASSWORD",
        "CLICKHOUSE_PASSWORD",
        "REDIS_AUTH",
        "MINIO_ROOT_PASSWORD",
        "LANGFUSE_S3_UPLOAD_SECRET_ACCESS_KEY",
    ]:
        assert f"{key}=\n" in env_template


def test_compute_runtime_exposes_langfuse_export_settings_without_values() -> None:
    runtime_template = (ROOT / "deploy/compute/runtime.env.template").read_text(encoding="utf-8")
    render = (ROOT / "deploy/compute/render-runtime-env.sh").read_text(encoding="utf-8")
    compose = (ROOT / "deploy/compute/app-compose.yml").read_text(encoding="utf-8")
    install = (ROOT / "deploy/compute/install.sh").read_text(encoding="utf-8")
    compute_tf = (ROOT / "deploy/compute/terraform/main.tf").read_text(encoding="utf-8")
    compute_schema = (ROOT / "deploy/compute/terraform/schema.yaml").read_text(encoding="utf-8")

    for key in [
        "LLMETRY_ENABLED",
        "LLMETRY_STORE_ENABLED",
        "LLMETRY_CAPTURE_CONTENT",
        "LANGFUSE_ENABLED",
        "LANGFUSE_HOST",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_OTEL_EXPORT_ENABLED",
    ]:
        assert key in runtime_template
        assert key in render
        assert key in compose
        assert key in install

    for key in [
        "oci_genai_endpoint",
        "oci_genai_model_id",
        "llmetry_capture_content",
        "langfuse_enabled",
        "langfuse_host",
        "langfuse_public_key",
        "langfuse_secret_key",
    ]:
        assert key in compute_tf
        assert key in compute_schema

    assert "LANGFUSE_PUBLIC_KEY=\n" in runtime_template
    assert "LANGFUSE_SECRET_KEY=\n" in runtime_template
    assert "OCI_GENAI_ENDPOINT" in runtime_template
    assert "OCI_GENAI_MODEL_ID" in runtime_template
