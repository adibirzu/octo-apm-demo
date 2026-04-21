"""Regression: SERVICE_SHOP_URL is the canonical env var for the drone
shop URL (matches SERVICE_CRM_URL on the shop side). OCTO_DRONE_SHOP_URL
and MUSHOP_CLOUDNATIVE_URL remain accepted as deprecated aliases.
"""

from __future__ import annotations

import importlib

import pytest


def _reload_cfg():
    import server.config as m

    importlib.reload(m)
    return m.cfg


@pytest.mark.portability
def test_service_shop_url_preferred_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_SHOP_URL", "https://shop.tenant-a.example.invalid")
    monkeypatch.setenv("OCTO_DRONE_SHOP_URL", "https://shop.legacy.example.invalid")
    monkeypatch.setenv("MUSHOP_CLOUDNATIVE_URL", "https://shop.older.example.invalid")
    cfg = _reload_cfg()
    assert cfg.octo_drone_shop_url == "https://shop.tenant-a.example.invalid"


@pytest.mark.portability
def test_legacy_octo_drone_shop_url_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_SHOP_URL", raising=False)
    monkeypatch.setenv("OCTO_DRONE_SHOP_URL", "https://shop.legacy.example.invalid")
    monkeypatch.delenv("MUSHOP_CLOUDNATIVE_URL", raising=False)
    cfg = _reload_cfg()
    assert cfg.octo_drone_shop_url == "https://shop.legacy.example.invalid"


@pytest.mark.portability
def test_neither_canonical_nor_legacy_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SERVICE_SHOP_URL", "OCTO_DRONE_SHOP_URL", "MUSHOP_CLOUDNATIVE_URL"):
        monkeypatch.delenv(name, raising=False)
    cfg = _reload_cfg()
    assert cfg.octo_drone_shop_url == ""


@pytest.mark.portability
def test_external_orders_url_prefers_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTERNAL_ORDERS_URL", raising=False)
    monkeypatch.setenv("SERVICE_SHOP_URL", "https://shop.tenant-a.example.invalid")
    monkeypatch.delenv("OCTO_DRONE_SHOP_URL", raising=False)
    cfg = _reload_cfg()
    assert cfg.external_orders_url == "https://shop.tenant-a.example.invalid"


@pytest.mark.portability
def test_legacy_only_emits_deprecation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_SHOP_URL", raising=False)
    monkeypatch.setenv("OCTO_DRONE_SHOP_URL", "https://shop.legacy.example.invalid")
    cfg = _reload_cfg()
    warnings = cfg.warn_deprecations()
    assert any("SERVICE_SHOP_URL" in w and "OCTO_DRONE_SHOP_URL" in w for w in warnings)
