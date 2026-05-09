"""Security span/log enrichment regressions."""

from __future__ import annotations

from typing import Any

from server.observability import security_spans


def test_security_span_emits_log_analytics_checkout_fields(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_log_security_event(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(security_spans, "log_security_event", fake_log_security_event)
    monkeypatch.setattr(security_spans, "_persist_security_event", lambda **_: None)

    security_spans.security_span(
        "idor",
        severity="medium",
        payload="missing_product=999",
        source_ip="198.51.100.10",
        endpoint="/api/cart/add",
        product_id=999,
        session_id="session-123",
    )

    assert captured["security_check"] == "idor"
    assert captured["security_stage"] == "cart_input_validation"
    assert captured["endpoint"] == "/api/cart/add"
    assert captured["source_ip"] == "198.51.100.10"
    assert captured["product_id"] == 999
    assert captured["session_id"] == "session-123"
    assert captured["mitre_technique_id"] == "T1078"
    assert captured["owasp_category"] == "A01:2021"
