"""Session gate coverage for internal simulation automation."""

from __future__ import annotations

from types import SimpleNamespace

from starlette.requests import Request

from server.middleware import session_gate


def _request(path: str, key: str = "") -> Request:
    headers = []
    if key:
        headers.append((b"x-internal-service-key", key.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "scheme": "https",
            "server": ("admin.example.test", 443),
            "client": ("198.51.100.10", 50123),
        }
    )


def test_internal_key_allows_drone_shop_simulation_proxy(monkeypatch) -> None:
    monkeypatch.setattr(session_gate, "cfg", SimpleNamespace(drone_shop_internal_key="shared-secret"))

    request = _request("/api/simulate/drone-shop/demo-storyboard", "shared-secret")

    assert session_gate._is_internal_drone_shop_simulation(request) is True


def test_internal_key_does_not_bypass_other_admin_apis(monkeypatch) -> None:
    monkeypatch.setattr(session_gate, "cfg", SimpleNamespace(drone_shop_internal_key="shared-secret"))

    request = _request("/api/simulate/create-customer", "shared-secret")

    assert session_gate._is_internal_drone_shop_simulation(request) is False


def test_missing_or_wrong_internal_key_does_not_bypass(monkeypatch) -> None:
    monkeypatch.setattr(session_gate, "cfg", SimpleNamespace(drone_shop_internal_key="shared-secret"))

    assert session_gate._is_internal_drone_shop_simulation(
        _request("/api/simulate/drone-shop/attack-lab", "wrong")
    ) is False
    assert session_gate._is_internal_drone_shop_simulation(
        _request("/api/simulate/drone-shop/attack-lab")
    ) is False
