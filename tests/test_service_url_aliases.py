"""PR-3: canonical env var names for cross-service URLs.

Audit finding: Shop used ENTERPRISE_CRM_URL while CRM used OCTO_DRONE_SHOP_URL.
Standardize on SERVICE_CRM_URL / SERVICE_SHOP_URL and treat the legacy
names as deprecated aliases. Keep backward compatibility — DO NOT break
existing deployments.
"""

from __future__ import annotations

import importlib

import pytest


def _reload_config():
    import server.config as m

    importlib.reload(m)
    return m.Config()


@pytest.mark.portability
def test_service_crm_url_preferred_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_CRM_URL", "https://crm.tenant-a.example.invalid")
    monkeypatch.setenv("ENTERPRISE_CRM_URL", "https://crm.legacy.example.invalid")
    cfg = _reload_config()
    assert cfg.enterprise_crm_url == "https://crm.tenant-a.example.invalid", (
        "SERVICE_CRM_URL (canonical) must win over ENTERPRISE_CRM_URL (legacy)"
    )


@pytest.mark.portability
def test_legacy_enterprise_crm_url_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_CRM_URL", raising=False)
    monkeypatch.setenv("ENTERPRISE_CRM_URL", "https://crm.legacy.example.invalid")
    cfg = _reload_config()
    assert cfg.enterprise_crm_url == "https://crm.legacy.example.invalid"


@pytest.mark.portability
def test_neither_set_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_CRM_URL", raising=False)
    monkeypatch.delenv("ENTERPRISE_CRM_URL", raising=False)
    cfg = _reload_config()
    assert cfg.enterprise_crm_url == ""


@pytest.mark.portability
def test_legacy_only_emits_deprecation_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_CRM_URL", raising=False)
    monkeypatch.setenv("ENTERPRISE_CRM_URL", "https://crm.legacy.example.invalid")
    cfg = _reload_config()
    warnings = cfg.warn_deprecations()
    assert any("ENTERPRISE_CRM_URL" in w and "SERVICE_CRM_URL" in w for w in warnings)


@pytest.mark.portability
def test_canonical_name_does_not_emit_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_CRM_URL", "https://crm.tenant-a.example.invalid")
    monkeypatch.delenv("ENTERPRISE_CRM_URL", raising=False)
    cfg = _reload_config()
    assert cfg.warn_deprecations() == []
