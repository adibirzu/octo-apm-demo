from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent / "server"


def test_base_configures_same_origin_w3c_rum_trace_headers() -> None:
    template = (ROOT / "templates/base.html").read_text(encoding="utf-8")

    assert "traceSupportingEndpoints" in template
    assert 'headers: ["W3C"]' in template
    assert "octoHostPattern" in template
    assert "headers: []" not in template
    assert "hostPattern: '.*'" not in template


def test_app_fetch_delegates_to_rum_instrumented_fetch() -> None:
    app_js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    observability_js = (ROOT / "static/js/observability.js").read_text(encoding="utf-8")

    assert "window.octoFetch" in app_js
    assert "window.__nativeFetch || window.fetch.bind(window)" not in app_js
    assert "window.octoFetch = async function" in observability_js
    assert "window.__nativeFetch = async function" not in observability_js


def test_login_emits_sanitized_rum_actions() -> None:
    template = (ROOT / "templates/login.html").read_text(encoding="utf-8")

    assert "auth.login.submit" in template
    assert "auth.login.result" in template
    assert "window.octoRumEvent('auth.login.submit', { auth_method: 'password' })" in template
    assert "role: data.user && data.user.role ? data.user.role : 'unknown'" in template
    assert "window.octoRumEvent('auth.login.submit', {username" not in template
    assert "window.octoRumEvent('auth.login.result', {username" not in template
