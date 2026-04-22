import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.security.headers import _build_csp


def test_csp_allows_configured_rum_script_origin(monkeypatch):
    monkeypatch.setenv(
        "OCI_APM_RUM_ENDPOINT",
        "https://exampleapm123456.apm-agt.us-phoenix-1.oci.oraclecloud.com",
    )

    csp = _build_csp("test-nonce", None)

    assert "script-src 'self' 'nonce-test-nonce' https://static.oracle.com" in csp
    assert "https://exampleapm123456.apm-agt.us-phoenix-1.oci.oraclecloud.com" in csp


def test_html_templates_nonce_all_inline_scripts():
    template_dir = Path(__file__).resolve().parents[1] / "server" / "templates"
    templates = [
        "base.html",
        "dashboard.html",
        "login.html",
        "page.html",
        "services.html",
        "shop.html",
    ]

    for name in templates:
        content = (template_dir / name).read_text()
        script_tags = re.findall(r"<script\b[^>]*>", content)
        assert script_tags, f"{name} should contain at least one script tag"
        assert all('nonce="{{ csp_nonce }}"' in tag for tag in script_tags), (
            f"{name} must nonce all script tags"
        )
