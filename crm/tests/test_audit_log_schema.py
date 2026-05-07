from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine, inspect, text

import server.bootstrap as bootstrap

from server.bootstrap import (
    _derived_crm_public_url,
    _derived_shop_public_url,
    _ensure_audit_log_columns,
    _should_reconcile_seed_field,
)


def test_bootstrap_adds_user_agent_to_legacy_audit_logs(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'crm.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE audit_logs ("
                "id INTEGER PRIMARY KEY, "
                "user_id INTEGER, "
                "action VARCHAR(100), "
                "resource VARCHAR(200), "
                "details TEXT, "
                "ip_address VARCHAR(50), "
                "trace_id VARCHAR(64), "
                "created_at TIMESTAMP"
                ")"
            )
        )
        _ensure_audit_log_columns(conn)
        _ensure_audit_log_columns(conn)

    columns = {column["name"] for column in inspect(engine).get_columns("audit_logs")}
    assert "user_agent" in columns


def test_seed_urls_come_from_deployment_config(monkeypatch) -> None:
    monkeypatch.setenv("CRM_PUBLIC_URL", "https://admin-public.example.test/")
    monkeypatch.setattr(
        bootstrap,
        "cfg",
        SimpleNamespace(
            shop_public_url="https://shop-public.example.test/",
            crm_base_url="http://admin.internal/",
            dns_domain="example.test",
        ),
    )

    assert _derived_shop_public_url() == "https://shop-public.example.test"
    assert _derived_crm_public_url() == "https://admin-public.example.test"


def test_seed_reconciliation_replaces_placeholders_only() -> None:
    assert _should_reconcile_seed_field(
        "https://shop.example.test", "https://shop-public.internal"
    )
    assert not _should_reconcile_seed_field(
        "https://custom-store.example.com", "https://shop-public.internal"
    )
