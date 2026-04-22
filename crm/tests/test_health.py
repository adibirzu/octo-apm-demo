"""Minimal health check test to satisfy pre-push hook."""

from pathlib import Path


def test_config_loads():
    """Verify config module imports and instantiates."""
    from server.config import Config
    cfg = Config()
    assert cfg is not None


def test_favicon_is_wired_in_template_and_route() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    base_template = (repo_root / "server" / "templates" / "base.html").read_text()
    main_module = (repo_root / "server" / "main.py").read_text()

    assert 'rel="icon"' in base_template
    assert "/static/img/octo-icon.png" in base_template
    assert '"/favicon.ico"' in main_module
    assert "async def favicon()" in main_module
