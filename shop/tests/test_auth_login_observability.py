from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.database import SEED_USERS
from server.modules import auth as auth_module


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _Rows:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)


class _FakeDb:
    def __init__(self) -> None:
        self.audit_logs: list[dict[str, Any]] = []
        self.last_login_updates: list[int] = []
        user = next(item for item in SEED_USERS if item["username"] == "shopper")
        self.user = {
            "id": 41,
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "password_hash": user["password_hash"],
            "is_active": 1,
        }

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Rows:
        sql = str(statement)
        params = params or {}

        if "FROM users WHERE lower(username)" in sql:
            if str(params.get("username", "")).lower() == "shopper":
                return _Rows([self.user])
            return _Rows()

        if "UPDATE users SET last_login" in sql:
            self.last_login_updates.append(int(params["id"]))
            return _Rows()

        if "INSERT INTO audit_logs" in sql:
            self.audit_logs.append(params)
            return _Rows()

        return _Rows()


class _FakeDbContext:
    def __init__(self, db: _FakeDb) -> None:
        self.db = db

    async def __aenter__(self) -> _FakeDb:
        return self.db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _DummySpan:
    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}

    def __enter__(self) -> "_DummySpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value


class _DummyTracer:
    def __init__(self) -> None:
        self.span = _DummySpan()

    def start_as_current_span(self, name: str) -> _DummySpan:
        return self.span


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [
            (b"user-agent", b"pytest"),
            (b"x-correlation-id", b"abc123abc123abc123abc123abc123ab"),
        ],
        "client": ("198.51.100.10", 12345),
    }
    return Request(scope)


def test_login_success_writes_audit_and_trace_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    tracer = _DummyTracer()
    monkeypatch.setattr(auth_module, "get_db", lambda: _FakeDbContext(db))
    monkeypatch.setattr(auth_module, "get_tracer", lambda: tracer)
    monkeypatch.setattr(auth_module, "issue_token", lambda **_: "signed-token")
    monkeypatch.setattr(auth_module, "login_rate_limited", lambda _source_ip: False)
    monkeypatch.setattr(auth_module, "register_login_attempt", lambda _source_ip, success: None)

    response = asyncio.run(
        auth_module.login(
            _request(),
            {"username": "shopper", "password": "OrderDemo2026!", "browser_trace_id": "abc123abc123abc123abc123abc123ab"},
        )
    )

    assert response["status"] == "success"
    assert db.last_login_updates == [41]
    assert db.audit_logs[0]["action"] == "auth.login.success"
    assert db.audit_logs[0]["user_id"] == 41
    assert db.audit_logs[0]["resource"] == "users/41"
    assert "browser_trace_id=abc123abc123abc123abc123abc123ab" in db.audit_logs[0]["details"]
    assert tracer.span.attributes["auth.success"] is True
    assert tracer.span.attributes["auth.user_id"] == 41
    assert tracer.span.attributes["db.audit.entity"] == "audit_logs"


def test_login_failure_writes_audit_before_rejecting(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()
    tracer = _DummyTracer()
    monkeypatch.setattr(auth_module, "get_db", lambda: _FakeDbContext(db))
    monkeypatch.setattr(auth_module, "get_tracer", lambda: tracer)
    monkeypatch.setattr(auth_module, "login_rate_limited", lambda _source_ip: False)
    monkeypatch.setattr(auth_module, "register_login_attempt", lambda _source_ip, success: None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_module.login(
                _request(),
                {"username": "shopper", "password": "wrong", "browser_trace_id": "abc123abc123abc123abc123abc123ab"},
            )
        )

    assert exc.value.status_code == 401
    assert db.audit_logs[0]["action"] == "auth.login.failure"
    assert db.audit_logs[0]["user_id"] == 41
    assert "reason=invalid_credentials" in db.audit_logs[0]["details"]
    assert tracer.span.attributes["auth.success"] is False
    assert tracer.span.attributes["auth.failure_reason"] == "invalid_credentials"
