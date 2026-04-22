from __future__ import annotations

from pathlib import Path

import pytest


def _config_module():
    import server.config as config_module

    return config_module


def test_config_reads_secret_from_file(monkeypatch, tmp_path) -> None:
    secret_file = tmp_path / "app-secret.txt"
    secret_file.write_text("from-file\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_SECRET_KEY_FILE", str(secret_file))

    cfg = _config_module().Config()
    assert cfg.app_secret_key == "from-file"


def test_config_prefers_explicit_secret_over_file(monkeypatch, tmp_path) -> None:
    secret_file = tmp_path / "app-secret.txt"
    secret_file.write_text("from-file\n", encoding="utf-8")

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_SECRET_KEY", "from-env")
    monkeypatch.setenv("APP_SECRET_KEY_FILE", str(secret_file))

    cfg = _config_module().Config()
    assert cfg.app_secret_key == "from-env"


def test_postgres_urls_are_normalized(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://crm:secret@db.internal:5432/crm")
    monkeypatch.delenv("DATABASE_SYNC_URL", raising=False)
    monkeypatch.delenv("ORACLE_DSN", raising=False)

    cfg = _config_module().Config()
    assert cfg.use_postgres is True
    assert cfg.database_url == "postgresql+asyncpg://crm:secret@db.internal:5432/crm"
    assert cfg.database_sync_url == "postgresql://crm:secret@db.internal:5432/crm"


def test_cors_allowed_origins_strip_wildcards_and_slashes(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "*, https://crm.example.cloud/, https://shop.example.cloud ,https://crm.example.cloud/",
    )

    cfg = _config_module().Config()
    assert cfg.cors_allowed_origins == [
        "https://crm.example.cloud",
        "https://shop.example.cloud",
    ]


def test_idcs_redirect_uri_is_derived_from_crm_base_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRM_BASE_URL", "https://crm.example.cloud")
    monkeypatch.setenv("IDCS_DOMAIN_URL", "https://idcs.example.cloud")
    monkeypatch.setenv("IDCS_CLIENT_ID", "client-id")
    monkeypatch.setenv("IDCS_CLIENT_SECRET", "client-secret")
    monkeypatch.delenv("IDCS_REDIRECT_URI", raising=False)

    cfg = _config_module().Config()
    assert cfg.idcs_redirect_uri == "https://crm.example.cloud/api/auth/sso/callback"
    assert cfg.idcs_configured is True


def test_validate_requires_bootstrap_admin_password_in_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET_KEY", "signed-secret")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD_FILE", raising=False)

    cfg = _config_module().Config()
    with pytest.raises(RuntimeError, match="BOOTSTRAP_ADMIN_PASSWORD"):
        cfg.validate()


def test_login_template_does_not_expose_default_password() -> None:
    template = (
        Path(__file__).resolve().parent.parent
        / "server"
        / "templates"
        / "login.html"
    ).read_text(encoding="utf-8")

    assert "admin123" not in template
