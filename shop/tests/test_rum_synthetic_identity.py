"""RUM synthetic user identity wiring tests."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shop_rum_template_sets_username_before_browser_agent_loads() -> None:
    template = (ROOT / "server/templates/base.html").read_text()

    assert "octoSyntheticUserEmail" in template
    assert "window.apmrum.username" in template
    assert template.index("window.apmrum.username") < template.index("apmrum.min.js")


def test_rum_advanced_script_emits_synthetic_user_domain_not_raw_email() -> None:
    script = (ROOT / "server/static/js/rum-advanced.js").read_text()

    assert "synthetic_user_domain" in script
    assert "synthetic_user_enabled" in script
    assert "synthetic_user_email" not in script
