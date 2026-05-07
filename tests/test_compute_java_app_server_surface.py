"""Compute deployment surface for the Java APM app-server sidecar."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compute_runtime_env_exposes_java_apm_sidecar_settings() -> None:
    template = (ROOT / "deploy/compute/runtime.env.template").read_text()
    render = (ROOT / "deploy/compute/render-runtime-env.sh").read_text()
    install = (ROOT / "deploy/compute/install.sh").read_text()

    for name in (
        "JAVA_APM_ENABLED",
        "JAVA_APM_SERVICE_URL",
        "JAVA_APM_IMAGE",
        "JAVA_APM_PORT",
        "PAYMENT_GATEWAY_SIMULATION_ENABLED",
        "PAYMENT_PROVIDER",
    ):
        assert name in template
        assert name in render
        assert name in install


def test_podman_java_apm_systemd_unit_is_present() -> None:
    unit = ROOT / "deploy/compute/systemd/octo-java-apm.service"

    assert unit.exists()
    content = unit.read_text()
    assert "octo-java-apm" in content
    assert "JAVA_APM_IMAGE" in content
    assert "PORT=$${JAVA_APM_PORT:-18080}" in content


def test_resource_manager_compute_package_includes_java_apm_unit() -> None:
    package = (ROOT / "deploy/compute/stack-package.sh").read_text()
    terraform = (ROOT / "deploy/compute/terraform/main.tf").read_text()

    assert "systemd/octo-java-apm.service" in package
    assert "systemd/octo-java-apm.service" in terraform


def test_java_entrypoint_enables_oci_apm_app_server_metrics() -> None:
    entrypoint = (ROOT / "services/apm-java-demo/entrypoint.sh").read_text()

    for flag in (
        "-Dcom.oracle.apm.agent.resource.appserver=true",
        "-Dcom.oracle.apm.agent.resource.appserver.name=${APM_SERVICE_NAME}",
        "-Dcom.oracle.apm.agent.metric.collect.wait.for.appserver=false",
    ):
        assert flag in entrypoint


def test_compute_hosts_install_java_apm_build_prerequisites() -> None:
    install = (ROOT / "deploy/compute/install.sh").read_text()
    cloud_init = (ROOT / "deploy/compute/terraform/cloud-init/compute.yaml.tftpl").read_text()
    compute_readme = (ROOT / "deploy/compute/README.md").read_text()
    getting_started = (ROOT / "site/getting-started/compute-deployment.md").read_text()

    for name in (
        "curl",
        "git",
        "rsync",
        "unzip",
        "tar",
        "gzip",
        "make",
        "podman",
        "java-21-openjdk-devel",
        "maven",
        "maven-openjdk21",
    ):
        assert name in install
        assert name in cloud_init
        assert name in compute_readme
        assert name in getting_started

    assert "select_java_21" in install
    assert "java-21-openjdk" in install
    assert "grep -q '\"21\\.'" in install


def test_container_builds_use_registry_qualified_base_images() -> None:
    java_dockerfile = (ROOT / "services/apm-java-demo/Dockerfile").read_text()
    shop_dockerfile = (ROOT / "shop/Dockerfile").read_text()
    crm_dockerfile = (ROOT / "crm/Dockerfile").read_text()

    assert "FROM docker.io/library/maven:3.9-eclipse-temurin-21 AS builder" in java_dockerfile
    assert "FROM docker.io/library/eclipse-temurin:21-jre" in java_dockerfile
    assert "ARG PYTHON_BASE=docker.io/library/python:3.12-slim" in shop_dockerfile
    assert "FROM docker.io/library/python:3.11-slim AS builder" in crm_dockerfile
    assert "FROM docker.io/library/python:3.11-slim" in crm_dockerfile
