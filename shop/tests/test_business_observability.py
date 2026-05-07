"""Shop business observability recorder coverage."""

from __future__ import annotations

from server.observability import business_metrics


class _Counter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict]] = []

    def add(self, value: int, attrs: dict | None = None) -> None:
        self.calls.append((value, attrs or {}))


class _Histogram:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict]] = []

    def record(self, value: float, attrs: dict | None = None) -> None:
        self.calls.append((value, attrs or {}))


def _install_fake_instruments(monkeypatch):
    instruments = {
        "payment_authorizations": _Counter(),
        "payment_risk_score": _Histogram(),
        "java_app_server_calls": _Counter(),
        "java_app_server_latency": _Histogram(),
        "synthetic_user_runs": _Counter(),
        "synthetic_user_records": _Counter(),
        "synthetic_orders_created": _Counter(),
        "attack_stages": _Counter(),
    }
    monkeypatch.setattr(business_metrics, "_inited", True)
    for name, instrument in instruments.items():
        monkeypatch.setattr(business_metrics, name, instrument)
    return instruments


def test_demo_metric_recorders_emit_low_cardinality_attributes(monkeypatch) -> None:
    instruments = _install_fake_instruments(monkeypatch)

    business_metrics.record_payment_authorization(
        status="DECLINED",
        provider="simulated-provider-with-a-long-name",
        source="shop_checkout",
        risk_score=73,
    )
    business_metrics.record_java_app_server_call(
        operation="java_app_server.post.api.java-apm.payment.authorize",
        status="ok",
        latency_ms=12.6,
    )
    business_metrics.record_synthetic_user_run(
        created=2,
        updated=3,
        deleted=1,
        orders_created=4,
        generator="vm-scheduler",
    )
    business_metrics.record_attack_stage(
        stage="payment_interception",
        severity="critical",
        technique_id="T1056.001",
    )

    assert instruments["payment_authorizations"].calls == [
        (1, {"status": "declined", "provider": "simulated-provider-with-a-long", "source": "shop_checkout"})
    ]
    assert instruments["payment_risk_score"].calls == [
        (73.0, {"status": "declined", "provider": "simulated-provider-with-a-long", "source": "shop_checkout"})
    ]
    assert instruments["java_app_server_calls"].calls == [
        (1, {"operation": "payment.authorize", "status": "ok"})
    ]
    assert instruments["java_app_server_latency"].calls == [
        (12.6, {"operation": "payment.authorize", "status": "ok"})
    ]
    assert instruments["synthetic_user_runs"].calls == [(1, {"generator": "vm-scheduler"})]
    assert instruments["synthetic_user_records"].calls == [
        (2, {"operation": "created", "generator": "vm-scheduler"}),
        (3, {"operation": "updated", "generator": "vm-scheduler"}),
        (1, {"operation": "deleted", "generator": "vm-scheduler"}),
    ]
    assert instruments["synthetic_orders_created"].calls == [
        (4, {"source": "synthetic-user-cron", "generator": "vm-scheduler"})
    ]
    assert instruments["attack_stages"].calls == [
        (1, {"stage": "payment_interception", "severity": "critical", "technique_id": "T1056.001"})
    ]
