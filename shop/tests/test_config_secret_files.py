from __future__ import annotations

import importlib


def test_shop_config_reads_secret_from_file(monkeypatch, tmp_path) -> None:
    secret_file = tmp_path / "auth-token.txt"
    secret_file.write_text("super-secret-token\n", encoding="utf-8")

    monkeypatch.delenv("AUTH_TOKEN_SECRET", raising=False)
    monkeypatch.setenv("AUTH_TOKEN_SECRET_FILE", str(secret_file))

    import server.config as config_module

    config_module = importlib.reload(config_module)
    try:
        assert config_module.cfg.auth_token_secret == "super-secret-token"
    finally:
        monkeypatch.delenv("AUTH_TOKEN_SECRET_FILE", raising=False)
        importlib.reload(config_module)


def test_shop_config_prefers_explicit_secret_over_file(monkeypatch, tmp_path) -> None:
    secret_file = tmp_path / "idcs-secret.txt"
    secret_file.write_text("from-file\n", encoding="utf-8")

    monkeypatch.setenv("IDCS_CLIENT_SECRET", "from-env")
    monkeypatch.setenv("IDCS_CLIENT_SECRET_FILE", str(secret_file))

    import server.config as config_module

    config_module = importlib.reload(config_module)
    try:
        assert config_module.cfg.idcs_client_secret == "from-env"
    finally:
        monkeypatch.delenv("IDCS_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("IDCS_CLIENT_SECRET_FILE", raising=False)
        importlib.reload(config_module)
