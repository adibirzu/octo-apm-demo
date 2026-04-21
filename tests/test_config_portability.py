"""Portability + security regression tests for server.config.Config.

Covers:
- No localhost fallback leaks into production IDCS redirects.
- validate() refuses to start when required tenancy config is missing in prod.
- Empty DNS_DOMAIN does not silently derive bogus public URLs.
"""

from __future__ import annotations

import importlib
import os
from typing import Iterator

import pytest


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Reset config-affecting env vars for each test and reimport config."""
    keys = [
        "DNS_DOMAIN",
        "ENVIRONMENT",
        "APP_ENV",
        "AUTH_TOKEN_SECRET",
        "AUTH_TOKEN_SECRET_FILE",
        "IDCS_DOMAIN_URL",
        "IDCS_CLIENT_ID",
        "IDCS_CLIENT_SECRET",
        "IDCS_CLIENT_SECRET_FILE",
        "IDCS_REDIRECT_URI",
        "IDCS_POST_LOGOUT_REDIRECT",
        "CRM_PUBLIC_URL",
        "ENTERPRISE_CRM_URL",
        "ORACLE_DSN",
        "ORACLE_PASSWORD",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    yield monkeypatch


def _fresh_config(env: pytest.MonkeyPatch):
    import server.config as config_module

    importlib.reload(config_module)
    return config_module.Config()


@pytest.mark.unit
class TestIdcsRedirectNoLocalhostLeak:
    def test_idcs_redirect_empty_when_dns_missing(self, env):
        """When DNS_DOMAIN is not set, redirect must be empty — never localhost."""
        cfg = _fresh_config(env)
        assert cfg.idcs_redirect_uri == "", (
            "idcs_redirect_uri must not fall back to http://localhost... — "
            "that silently breaks SSO in production"
        )

    def test_idcs_redirect_uses_dns_domain_when_set(self, env):
        env.setenv("DNS_DOMAIN", "tenant-a.example.invalid")
        cfg = _fresh_config(env)
        assert (
            cfg.idcs_redirect_uri
            == "https://shop.tenant-a.example.invalid/api/auth/sso/callback"
        )

    def test_idcs_redirect_explicit_override_wins(self, env):
        env.setenv("DNS_DOMAIN", "tenant-a.example.invalid")
        env.setenv(
            "IDCS_REDIRECT_URI", "https://custom.example.invalid/cb"
        )
        cfg = _fresh_config(env)
        assert cfg.idcs_redirect_uri == "https://custom.example.invalid/cb"

    def test_idcs_post_logout_redirect_is_relative_when_dns_missing(self, env):
        """Relative `/login` is safe (no host leak)."""
        cfg = _fresh_config(env)
        assert cfg.idcs_post_logout_redirect == "/login"


@pytest.mark.unit
class TestProdValidateRefusesMissingDns:
    def _prod_env(self, env: pytest.MonkeyPatch) -> None:
        env.setenv("ENVIRONMENT", "production")
        env.setenv("APP_ENV", "production")
        env.setenv("AUTH_TOKEN_SECRET", "x" * 32)

    def test_prod_with_idcs_but_no_dns_domain_fails(self, env):
        """Partial IDCS + no DNS_DOMAIN + production → hard fail, not localhost fallback."""
        self._prod_env(env)
        env.setenv("IDCS_DOMAIN_URL", "https://idcs.example.invalid")
        env.setenv("IDCS_CLIENT_ID", "abc")
        env.setenv("IDCS_CLIENT_SECRET", "def")
        cfg = _fresh_config(env)
        with pytest.raises(RuntimeError, match="IDCS|DNS_DOMAIN"):
            cfg.validate()

    def test_prod_with_full_idcs_and_dns_passes(self, env):
        self._prod_env(env)
        env.setenv("DNS_DOMAIN", "tenant-a.example.invalid")
        env.setenv("IDCS_DOMAIN_URL", "https://idcs.example.invalid")
        env.setenv("IDCS_CLIENT_ID", "abc")
        env.setenv("IDCS_CLIENT_SECRET", "def")
        cfg = _fresh_config(env)
        cfg.validate()  # must not raise


@pytest.mark.unit
class TestPublicUrlsNoFabrication:
    def test_shop_public_url_empty_without_dns(self, env):
        cfg = _fresh_config(env)
        assert cfg.shop_public_url == ""

    def test_crm_public_url_empty_without_dns_or_override(self, env):
        cfg = _fresh_config(env)
        assert cfg.crm_public_url == ""

    def test_cors_origins_empty_without_dns(self, env):
        cfg = _fresh_config(env)
        assert cfg.cors_origins_default == ""
