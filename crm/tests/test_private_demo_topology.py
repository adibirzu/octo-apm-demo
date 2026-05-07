"""Regression tests for the compact private-demo topology surface."""

from __future__ import annotations

import importlib

import pytest


def _reload_integrations():
    import server.config as config_module
    import server.modules.integrations as integrations_module

    importlib.reload(config_module)
    return importlib.reload(integrations_module)


@pytest.mark.portability
def test_private_demo_topology_lists_only_current_app_servers_and_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_STACK_NAME", "octo-demo")
    monkeypatch.setenv("SERVICE_INSTANCE_ID", "octo-demo-crm")
    monkeypatch.setenv("SHOP_PUBLIC_URL", "https://shop.example.test")
    monkeypatch.setenv("CRM_BASE_URL", "https://admin.example.test")
    monkeypatch.setenv("SERVICE_SHOP_URL", "http://shop.internal.example:8080")
    monkeypatch.setenv("ORACLE_DSN", "octoatp_low")

    integrations = _reload_integrations()

    dependencies = integrations._configured_dependencies()

    assert [dep["name"] for dep in dependencies] == [
        "drone-shop-portal",
        "crm-admin-portal",
        "octo-apm-atp",
    ]
    assert dependencies[0]["url"] == "https://shop.example.test"
    assert dependencies[0]["probe_url"] == "http://shop.internal.example:8080"
    assert dependencies[1]["url"] == "https://admin.example.test"
    assert dependencies[2]["connection_name"] == "octoatp_low"
    assert all("seven" not in dep["name"] for dep in dependencies)
    assert all("platform" not in dep["name"] for dep in dependencies)
