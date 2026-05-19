"""Phase 7 Plan 04 — RED tests for shared `_admin_host` helper extraction.

These tests pin the behavioral contract that the host-bound admin enforcement
primitives currently embedded in `crm/server/modules/coordinator.py` (lines
~300-361) must be extracted verbatim into a single shared module
`crm/server/modules/_admin_host.py`. Coordinator (and, in plan 05, the new
stress_test module) imports from that shared helper rather than re-implementing.

Pattern reference: per `.planning/phases/07-.../07-PATTERNS.md` §Authentication
("do NOT re-implement `_require_admin_host`") and §RESEARCH §Anti-Patterns §4.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

# Make `server.*` importable (mirrors crm/tests/conftest.py).
REPO_ROOT = Path(__file__).resolve().parents[1]
CRM_ROOT = REPO_ROOT / "crm"
if str(CRM_ROOT) not in sys.path:
    sys.path.insert(0, str(CRM_ROOT))

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient


# ── Module-shape contract ────────────────────────────────────────────────


def test_admin_host_module_exports_helpers() -> None:
    """The shared helper module exposes the three helpers + two constants."""
    from server.modules._admin_host import (  # noqa: F401
        _ADMIN_SURFACE,
        _LOCAL_HOSTS,
        _configured_admin_hosts,
        _request_host,
        _require_admin_host,
    )

    assert _ADMIN_SURFACE == "admin.octodemo.cloud"
    assert _LOCAL_HOSTS == {"localhost", "127.0.0.1", "::1", "testserver"}
    assert callable(_request_host)
    assert callable(_configured_admin_hosts)
    assert callable(_require_admin_host)


# ── _request_host parsing ────────────────────────────────────────────────


def _build_request(headers: dict[str, str]) -> Request:
    """Build a minimal Starlette Request with the supplied headers."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "scheme": "http",
        "root_path": "",
        "app": None,
    }
    return Request(scope)


def test_admin_host_request_host_strips_port() -> None:
    from server.modules._admin_host import _request_host

    req = _build_request({"host": "admin.example.com:8443"})
    assert _request_host(req) == "admin.example.com"


def test_admin_host_request_host_uses_xff_first() -> None:
    from server.modules._admin_host import _request_host

    req = _build_request(
        {"x-forwarded-host": "admin.example.com", "host": "backend.internal"}
    )
    assert _request_host(req) == "admin.example.com"


def test_admin_host_request_host_handles_ipv6_brackets() -> None:
    from server.modules._admin_host import _request_host

    req = _build_request({"host": "[::1]:8080"})
    assert _request_host(req) == "::1"


# ── _require_admin_host policy ───────────────────────────────────────────


def test_admin_host_local_hosts_pass() -> None:
    from server.modules._admin_host import _require_admin_host

    req = _build_request({"host": "localhost"})
    assert _require_admin_host(req) == "localhost"


def test_admin_host_admin_surface_passes() -> None:
    from server.modules._admin_host import _require_admin_host

    req = _build_request({"host": "admin.octodemo.cloud"})
    assert _require_admin_host(req) == "admin.octodemo.cloud"


def test_admin_host_unknown_host_403() -> None:
    from server.modules._admin_host import _require_admin_host

    req = _build_request({"host": "evil.example.com"})
    with pytest.raises(HTTPException) as exc_info:
        _require_admin_host(req)
    assert exc_info.value.status_code == 403


def test_admin_host_dns_domain_env_extends_allowlist(monkeypatch) -> None:
    """When `cfg.dns_domain` is set, both `admin.<dns>` and `crm.<dns>` pass."""
    from server.modules import _admin_host as helper

    monkeypatch.setattr(
        helper,
        "cfg",
        SimpleNamespace(
            dns_domain="octodemo.cloud",
            crm_base_url="https://admin.octodemo.cloud",
        ),
    )

    req_admin = _build_request({"host": "admin.octodemo.cloud"})
    req_crm = _build_request({"host": "crm.octodemo.cloud"})
    assert helper._require_admin_host(req_admin) == "admin.octodemo.cloud"
    assert helper._require_admin_host(req_crm) == "crm.octodemo.cloud"


# ── Structural: coordinator must import, not re-implement ────────────────


def test_coordinator_still_imports_admin_host_helpers() -> None:
    """coordinator.py source must contain `from server.modules._admin_host import`.

    This is the structural anti-drift guard: if a future change copy-pastes the
    helpers back into coordinator.py, this test fails.
    """
    coordinator_src = (CRM_ROOT / "server/modules/coordinator.py").read_text(
        encoding="utf-8"
    )
    assert "from server.modules._admin_host import" in coordinator_src


# ── Regression: existing Phase 5 admin-host contract on coordinator endpoint ──


def test_coordinator_admin_host_regression_403() -> None:
    """Phase 5 contract: POST /api/admin/coordinator/query from a non-admin
    host returns 403. This must remain bit-identical after the refactor.
    """
    from server.modules import coordinator

    app = FastAPI()

    async def _session_injector(request, call_next):
        request.state.current_user = {"user_id": 1, "username": "admin", "role": "admin"}
        return await call_next(request)

    app.middleware("http")(_session_injector)
    app.include_router(coordinator.router)
    client = TestClient(app)

    response = client.post(
        "/api/admin/coordinator/query",
        headers={"host": "evil.example.com"},
        json={"message": "Show admin users", "page": "admin"},
    )
    assert response.status_code == 403
    assert "admin.octodemo.cloud" in response.json()["detail"]
