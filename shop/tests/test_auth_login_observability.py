"""Login observability contract tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import oracle
from starlette.requests import Request

from server.database import AuditLog
from server.modules import auth


class _Mappings:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None


class _Rows:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)


class _FakeDb:
    def __init__(self, user: dict | None) -> None:
        self.user = user
        self.audit_logs: list[dict] = []
        self.last_login_updates: list[dict] = []

    async def execute(self, statement, params: dict | None = None) -> _Rows:
        sql = str(statement)
        params = params or {}
        if "FROM users WHERE lower(username)" in sql:
            return _Rows([self.user] if self.user else [])
        if "UPDATE users SET last_login" in sql:
            self.last_login_updates.append(dict(params))
            return _Rows()
        if "INSERT INTO audit_logs" in sql:
            self.audit_logs.append(dict(params or statement.compile().params))
            return _Rows()
        return _Rows()


class _DbContext:
    def __init__(self, db: _FakeDb) -> None:
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [(b"user-agent", b"pytest-browser")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("203.0.113.10", 12345),
            "scheme": "http",
        }
    )


def _patch_common(monkeypatch: pytest.MonkeyPatch, db: _FakeDb, logs: list[dict], metrics: list[tuple[str, str]]) -> None:
    monkeypatch.setattr(auth, "get_db", lambda: _DbContext(db))
    monkeypatch.setattr(auth, "issue_token", lambda **kwargs: "signed-demo-token")
    monkeypatch.setattr(auth, "login_rate_limited", lambda _source_ip: False)
    monkeypatch.setattr(auth, "register_login_attempt", lambda _source_ip, success: None)
    monkeypatch.setattr(auth, "security_span", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth, "push_log", lambda _level, _message, **fields: logs.append(fields))
    monkeypatch.setattr(auth.business_metrics, "record_login_success", lambda method="password": metrics.append(("success", method)))
    monkeypatch.setattr(auth.business_metrics, "record_login_failure", lambda reason="invalid": metrics.append(("failure", reason)))
    monkeypatch.setattr(
        auth,
        "current_trace_context",
        lambda: {"trace_id": "f" * 32, "span_id": "e" * 16, "traceparent": "00-" + "f" * 32 + "-" + "e" * 16 + "-01"},
    )


def test_login_audit_insert_quotes_oracle_resource_column() -> None:
    statement = auth._login_audit_insert(
        user_id=42,
        username="shopper",
        source_ip="203.0.113.10",
        user_agent="pytest-browser",
        trace_id="f" * 32,
    )

    compiled = str(statement.compile(dialect=oracle.dialect()))

    assert "audit_logs" in compiled
    assert '"resource"' in compiled
    assert AuditLog.__tablename__ == "audit_logs"


@pytest.mark.asyncio
async def test_login_success_emits_audit_log_metrics_and_structured_log(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb(
        {
            "id": 42,
            "username": "shopper",
            "email": "shopper@example.invalid",
            "role": "user",
            "password_hash": "hashed",
            "is_active": 1,
        }
    )
    logs: list[dict] = []
    metrics: list[tuple[str, str]] = []
    _patch_common(monkeypatch, db, logs, metrics)
    monkeypatch.setattr(auth.bcrypt, "checkpw", lambda _password, _hash: True)

    result = await auth.login(_request(), {"username": "shopper", "password": "OrderDemo2026!"})

    assert result["status"] == "success"
    assert result["token"] == "signed-demo-token"
    assert db.last_login_updates == [{"id": 42}]
    assert db.audit_logs[-1]["user_id"] == 42
    assert db.audit_logs[-1]["trace_id"] == "f" * 32
    assert db.audit_logs[-1]["ip_address"] == "203.0.113.10"
    assert logs[-1]["auth.result"] == "success"
    assert logs[-1]["workflow.id"] == "login"
    assert logs[-1]["workflow.step"] == "authenticate"
    assert logs[-1]["auth.user_id"] == 42
    assert metrics[-1] == ("success", "password")


@pytest.mark.asyncio
async def test_login_failure_emits_detection_ready_log_and_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb(
        {
            "id": 42,
            "username": "shopper",
            "email": "shopper@example.invalid",
            "role": "user",
            "password_hash": "hashed",
            "is_active": 1,
        }
    )
    logs: list[dict] = []
    metrics: list[tuple[str, str]] = []
    _patch_common(monkeypatch, db, logs, metrics)
    monkeypatch.setattr(auth.bcrypt, "checkpw", lambda _password, _hash: False)

    with pytest.raises(HTTPException) as exc:
        await auth.login(_request(), {"username": "shopper", "password": "wrong"})

    assert exc.value.status_code == 401
    assert db.audit_logs == []
    assert logs[-1]["auth.result"] == "invalid_credentials"
    assert logs[-1]["auth.user_found"] is True
    assert logs[-1]["workflow.id"] == "login"
    assert logs[-1]["http.status_code"] == 401
    assert metrics[-1] == ("failure", "invalid_credentials")
