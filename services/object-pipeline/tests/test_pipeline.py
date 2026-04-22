"""Object-pipeline tests — inject a fake fetch_object so no OCI SDK
dependency."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from octo_object_pipeline.api import create_app
from octo_object_pipeline.handlers import (
    ProcessingResult,
    process_catalog_image,
    process_invoice,
)


async def test_invoice_handler_extracts_total() -> None:
    body = b"Invoice #42\n\nTotal: $1234.56\nThank you."
    result = await process_invoice(body, {"object_name": "inv-42.pdf"})
    assert result.ok
    assert result.data["total"] == 1234.56


async def test_invoice_handler_misses_cleanly() -> None:
    result = await process_invoice(b"no total here", {"object_name": "x"})
    assert not result.ok
    assert "no total" in result.summary


async def test_catalog_image_rejects_large() -> None:
    body = b"x" * (6 * 1024 * 1024)
    result = await process_catalog_image(body, {})
    assert not result.ok
    assert "too large" in result.summary


async def test_catalog_image_accepts_small() -> None:
    result = await process_catalog_image(b"x" * 1024, {})
    assert result.ok


@pytest.fixture
def client() -> TestClient:
    # Fake fetch_object returns an invoice PDF-like blob
    async def _fetch(*, bucket: str, object_name: str) -> bytes:
        if bucket == "octo-invoices":
            return b"Invoice\nTotal: $99.99\n"
        if bucket == "octo-catalog-images":
            return b"fake-jpeg-bytes"
        return b""

    return TestClient(create_app(fetch_object=_fetch))


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    handlers = r.json()["handlers"]
    assert "octo-invoices" in handlers
    assert "octo-catalog-images" in handlers


def test_invoice_event_extracts_total(client: TestClient) -> None:
    event = {
        "eventType": "com.oraclecloud.objectstorage.createobject",
        "data": {
            "resourceName": "inv-42.pdf",
            "additionalDetails": {"bucketName": "octo-invoices"},
        },
    }
    r = client.post("/events/object-storage", json=event)
    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["total"] == 99.99


def test_unknown_bucket_returns_no_handler(client: TestClient) -> None:
    event = {
        "data": {
            "resourceName": "x.txt",
            "additionalDetails": {"bucketName": "not-registered"},
        }
    }
    r = client.post("/events/object-storage", json=event)
    assert r.status_code == 202
    assert r.json()["ok"] is False
    assert "no handler" in r.json()["reason"]


def test_malformed_event_400(client: TestClient) -> None:
    r = client.post("/events/object-storage", json={"data": {}})
    assert r.status_code == 400
