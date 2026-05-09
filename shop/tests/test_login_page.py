from __future__ import annotations

from pathlib import Path

import bcrypt

from server.database import SEED_USERS


ROOT = Path(__file__).resolve().parents[1]
ORDER_DEMO_PASSWORD = "OrderDemo2026!"
ORDER_TEST_USERS = {"shopper", "manager", "analyst", "support"}


def test_login_page_lists_order_test_users_and_removes_admin_shortcut() -> None:
    template = (ROOT / "server/templates/login.html").read_text(encoding="utf-8")

    assert "Order Test Users" in template
    assert "OrderDemo2026!" in template
    for username in ORDER_TEST_USERS:
        assert f'data-username="{username}"' in template

    assert 'href="/admin-page"' not in template
    assert "Open Admin" not in template


def test_login_page_propagates_browser_trace_context_to_login_api() -> None:
    template = (ROOT / "server/templates/login.html").read_text(encoding="utf-8")

    assert "octo-browser-trace-id" in template
    assert "traceparent" in template
    assert "X-Correlation-Id" in template
    assert "browser_trace_id: currentBrowserTraceId()" in template


def test_seeded_order_test_user_passwords_match_login_page() -> None:
    users = {user["username"]: user for user in SEED_USERS}

    for username in ORDER_TEST_USERS:
        assert bcrypt.checkpw(
            ORDER_DEMO_PASSWORD.encode("utf-8"),
            users[username]["password_hash"].encode("utf-8"),
        )
