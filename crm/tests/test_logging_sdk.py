from __future__ import annotations

import json
import sys
import types
from dataclasses import replace
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path = [str(APP_ROOT), *[path for path in sys.path if path != str(APP_ROOT)]]
for module_name in list(sys.modules):
    if module_name == "server" or module_name.startswith("server."):
        del sys.modules[module_name]

from server.observability import logging_sdk
from server.observability.workflow_context import WorkflowContext, _ctx


def test_mask_pii_returns_new_dict_and_masks_contact_fields() -> None:
    original = {
        "customer_email": "ada@example.com",
        "customer_phone": "+1 555 867 5309",
        "message": "Contact ada@example.com for follow-up",
        "count": 2,
    }

    masked = logging_sdk._mask_pii(original)

    assert masked is not original
    assert original["customer_email"] == "ada@example.com"
    assert masked["customer_email"] == "a***@example.com"
    assert masked["customer_phone"] == "***5309"
    assert masked["message"] == "Contact a***@example.com for follow-up"
    assert masked["count"] == 2


def test_push_log_enqueues_masked_payload(monkeypatch) -> None:
    queued: list[tuple[str, str, dict]] = []

    class _Queue:
        def put(self, item):
            queued.append(item)

    monkeypatch.setattr(logging_sdk, "_log_queue", _Queue())

    logging_sdk.push_log(
        "INFO",
        "customer event",
        customer_email="grace@example.com",
        customer_phone="555-010-1200",
    )

    assert queued
    level, message, payload = queued[-1]
    assert level == "INFO"
    assert message == "customer event"
    assert payload["customer_email"] == "g***@example.com"
    assert payload["customer_phone"] == "***1200"


def test_json_formatter_adds_logan_aliases_to_stdout(monkeypatch) -> None:
    monkeypatch.setattr(
        logging_sdk,
        "current_trace_context",
        lambda: {"trace_id": "a" * 32, "span_id": "b" * 16, "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"},
    )
    record = logging_sdk.logging.LogRecord(
        name="security.events",
        level=logging_sdk.logging.INFO,
        pathname="",
        lineno=0,
        msg="order accepted",
        args=(),
        exc_info=None,
    )
    record.extra_fields = {
        "orders.order_id": 42,
        "payment.gateway.request_id": "pgw-42-test",
        "payment.provider": "simulated",
        "java_apm.latency_ms": 17,
    }

    payload = json.loads(logging_sdk._JSONFormatter().format(record))

    assert payload["order_id"] == 42
    assert payload["payment_gateway_request_id"] == "pgw-42-test"
    assert payload["payment_provider"] == "simulated"
    assert payload["java_apm_latency_ms"] == 17


def test_push_log_adds_current_workflow_fields(monkeypatch) -> None:
    queued: list[tuple[str, str, dict]] = []

    class _Queue:
        def put(self, item):
            queued.append(item)

    monkeypatch.setattr(logging_sdk, "_log_queue", _Queue())
    token = _ctx.set(WorkflowContext(workflow_id="checkout", step="order-sync"))
    try:
        logging_sdk.push_log("INFO", "order accepted")
    finally:
        _ctx.reset(token)

    payload = queued[-1][2]
    assert payload["workflow.id"] == "checkout"
    assert payload["workflow.step"] == "order-sync"
    assert payload["workflow_id"] == "checkout"
    assert payload["workflow_step"] == "order-sync"


def test_push_log_adds_request_trace_and_service_fields(monkeypatch) -> None:
    queued: list[tuple[str, str, dict]] = []
    records: list[logging_sdk.logging.LogRecord] = []

    class _Queue:
        def put(self, item):
            queued.append(item)

    monkeypatch.setattr(logging_sdk, "_log_queue", _Queue())
    monkeypatch.setattr(logging_sdk, "current_request_id", lambda: "req-crm-123")
    monkeypatch.setattr(logging_sdk._security_logger, "handle", lambda record: records.append(record))
    monkeypatch.setattr(
        logging_sdk,
        "current_trace_context",
        lambda: {"trace_id": "a" * 32, "span_id": "b" * 16, "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"},
    )

    logging_sdk.push_log("INFO", "order accepted", customer_email="grace@example.com")

    payload = queued[-1][2]
    emitted = json.loads(logging_sdk._JSONFormatter().format(records[-1]))

    assert payload["request_id"] == "req-crm-123"
    assert payload["trace_id"] == "a" * 32
    assert payload["oracleApmTraceId"] == "a" * 32
    assert payload["span_id"] == "b" * 16
    assert payload["oracleApmSpanId"] == "b" * 16
    assert payload["service.name"]
    assert emitted["service_namespace"] == payload["service.namespace"]
    assert payload["customer_email"] == "g***@example.com"


def test_push_log_adds_app_log_event_to_current_and_request_spans(monkeypatch) -> None:
    events = {"current": [], "request": []}

    class _Span:
        def __init__(self, key: str):
            self.key = key

        def is_recording(self) -> bool:
            return True

        def add_event(self, name: str, attrs: dict) -> None:
            events[self.key].append((name, attrs))

    class _Queue:
        def put(self, item):
            pass

    current_span = _Span("current")
    request_span = _Span("request")
    monkeypatch.setattr(logging_sdk, "_log_queue", _Queue())
    monkeypatch.setattr(logging_sdk.trace, "get_current_span", lambda: current_span)
    monkeypatch.setattr(
        logging_sdk,
        "current_trace_context",
        lambda: {"trace_id": "1" * 32, "span_id": "2" * 16, "traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"},
    )

    token = logging_sdk.bind_request_span(request_span)
    try:
        logging_sdk.push_log(
            "INFO",
            "customer event",
            customer_email="grace@example.com",
            **{
                "http.url.path": "/api/simulate",
                "auth.user_id": 41,
                "auth.success": True,
                "orders.order_id": 9001,
            },
        )
    finally:
        logging_sdk.reset_request_span(token)

    assert events["current"][0][0] == "app.log"
    assert events["request"][0][0] == "app.log"
    assert events["request"][0][1]["log.message"] == "customer event"
    assert events["request"][0][1]["http.url.path"] == "/api/simulate"
    assert events["request"][0][1]["auth.user_id"] == 41
    assert events["request"][0][1]["auth.success"] is True
    assert events["request"][0][1]["orders.order_id"] == 9001
    assert "customer_email" not in events["request"][0][1]


def test_oci_logging_payload_uses_current_sdk_shape(monkeypatch) -> None:
    captured: dict = {}

    class _FakeClient:
        def put_logs(self, **kwargs):
            captured["put_logs"] = kwargs

    class _FakeModel:
        def __init__(self, **kwargs):
            assert "defaultloglevel" not in kwargs
            self.kwargs = kwargs

    fake_oci = types.ModuleType("oci")
    fake_loggingingestion = types.ModuleType("oci.loggingingestion")
    fake_models = types.ModuleType("oci.loggingingestion.models")
    fake_models.LogEntry = _FakeModel
    fake_models.LogEntryBatch = _FakeModel
    fake_models.PutLogsDetails = _FakeModel

    monkeypatch.setitem(sys.modules, "oci", fake_oci)
    monkeypatch.setitem(sys.modules, "oci.loggingingestion", fake_loggingingestion)
    monkeypatch.setitem(sys.modules, "oci.loggingingestion.models", fake_models)
    monkeypatch.setattr(logging_sdk, "_get_oci_logging_client", lambda: _FakeClient())
    monkeypatch.setattr(logging_sdk, "cfg", replace(logging_sdk.cfg, oci_log_id="ocid1.log.oc1..test"))

    logging_sdk._push_to_oci_logging(
        "info",
        "order accepted",
        {
            "oracleApmTraceId": "abc123",
            "service.name": "enterprise-crm-portal",
            "orders.order_id": 42,
            "payment.provider": "simulated",
            "payment.gateway.request_id": "pgw-42-test",
            "java_apm.latency_ms": 17,
        },
    )

    details = captured["put_logs"]["put_logs_details"]
    batch = details.kwargs["log_entry_batches"][0]
    entry = batch.kwargs["entries"][0]
    payload = json.loads(entry.kwargs["data"])
    logan_message = json.loads(payload["message"])

    assert captured["put_logs"]["log_id"] == "ocid1.log.oc1..test"
    assert entry.kwargs["time"].tzinfo is not None
    assert payload["timestamp"]
    assert payload["level"] == "INFO"
    assert payload["event_message"] == "order accepted"
    assert payload["log_message"] == "order accepted"
    assert logan_message["message"] == "order accepted"
    assert payload["oracleApmTraceId"] == "abc123"
    assert payload["service_name"] == "enterprise-crm-portal"
    assert payload["order_id"] == 42
    assert payload["payment_provider"] == "simulated"
    assert payload["payment_gateway_request_id"] == "pgw-42-test"
    assert payload["java_apm_latency_ms"] == 17
    assert logan_message["oracleApmTraceId"] == "abc123"
    assert logan_message["service_name"] == "enterprise-crm-portal"
