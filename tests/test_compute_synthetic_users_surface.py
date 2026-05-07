"""Compute deployment surface for synthetic user and order generation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compute_runtime_env_exposes_synthetic_user_settings() -> None:
    template = (ROOT / "deploy/compute/runtime.env.template").read_text()
    render = (ROOT / "deploy/compute/render-runtime-env.sh").read_text()
    install = (ROOT / "deploy/compute/install.sh").read_text()

    for name in (
        "SYNTHETIC_USERS_ENABLED",
        "SYNTHETIC_USER_EMAIL_DOMAIN",
        "SYNTHETIC_USER_COUNT",
        "SYNTHETIC_USER_ORDER_COUNT",
        "SYNTHETIC_USER_DELETE_AFTER_DAYS",
    ):
        assert name in template
        assert name in render
        assert name in install

    assert "oracle.com" not in template.lower()


def test_synthetic_user_timer_and_job_are_installed() -> None:
    service = ROOT / "deploy/compute/systemd/octo-synthetic-users.service"
    timer = ROOT / "deploy/compute/systemd/octo-synthetic-users.timer"
    job = ROOT / "deploy/compute/synthetic-users-job.sh"
    install = (ROOT / "deploy/compute/install.sh").read_text()

    assert service.exists()
    assert timer.exists()
    assert job.exists()
    assert "octo-synthetic-users.service" in timer.read_text()
    assert "ExecStart=/usr/local/bin/octo-synthetic-users" in service.read_text()
    assert "octo-synthetic-users.timer" in install
    assert "synthetic-users-job.sh" in install


def test_resource_manager_compute_package_includes_synthetic_user_assets() -> None:
    package = (ROOT / "deploy/compute/stack-package.sh").read_text()
    terraform = (ROOT / "deploy/compute/terraform/main.tf").read_text()

    for name in (
        "synthetic-users-job.sh",
        "systemd/octo-synthetic-users.service",
        "systemd/octo-synthetic-users.timer",
    ):
        assert name in package
        assert name in terraform
