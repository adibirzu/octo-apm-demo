from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from server.modules import admin


class _ScalarResult:
    def __init__(self, value: int):
        self._value = value
        self.rowcount = value

    def scalar(self) -> int:
        return self._value


class _FakeDb:
    def __init__(self) -> None:
        self.counts = {
            "order_sync_audit": 2,
            "audit_logs": 3,
            "user_sessions": 4,
            "page_views": 5,
            "support_tickets": 6,
            "shipments": 7,
            "invoices": 8,
            "order_items": 9,
            "orders": 10,
        }
        self.deletes: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        table = next((name for name in self.counts if name in sql), "")
        value = self.counts.get(table, 0)
        if sql.lstrip().upper().startswith("DELETE"):
            self.deletes.append(table)
        return _ScalarResult(value)


def _client(monkeypatch: pytest.MonkeyPatch, fake_db: _FakeDb, user: dict | None = None) -> TestClient:
    app = FastAPI()

    if user is not None:
        async def _session_injector(request: Request, call_next):
            request.state.current_user = user
            return await call_next(request)

        app.middleware("http")(_session_injector)

    @asynccontextmanager
    async def _fake_get_db():
        yield fake_db

    app.include_router(admin.router)
    monkeypatch.setattr(admin, "get_db", _fake_get_db)
    return TestClient(app)


def test_retention_preview_requires_admin_user(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _FakeDb())

    response = client.get("/api/admin/data-retention/preview?older_than_days=30")

    assert response.status_code == 401


def test_retention_preview_counts_without_deleting(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = _FakeDb()
    client = _client(monkeypatch, fake_db, {"user_id": 1, "username": "admin", "role": "admin"})

    response = client.get("/api/admin/data-retention/preview?older_than_days=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["total_matching_rows"] == sum(fake_db.counts.values())
    assert fake_db.deletes == []


def test_retention_cleanup_deletes_child_tables_before_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_db = _FakeDb()
    client = _client(monkeypatch, fake_db, {"user_id": 1, "username": "admin", "role": "admin"})

    response = client.post("/api/admin/data-retention/cleanup", json={"older_than_days": 45})

    assert response.status_code == 200
    assert response.json()["total_deleted_rows"] == sum(fake_db.counts.values())
    assert fake_db.deletes[-4:] == ["shipments", "invoices", "order_items", "orders"]


def test_admin_template_exposes_retention_controls() -> None:
    template = (
        Path(__file__).resolve().parent.parent
        / "server"
        / "templates"
        / "page.html"
    ).read_text()

    assert "admin-retention-panel" in template
    assert "/api/admin/data-retention/preview" in template
    assert "/api/admin/data-retention/cleanup" in template
