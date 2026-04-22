from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.modules.observability_frontend import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_frontend_observability_accepts_json_payload() -> None:
    client = _client()

    response = client.post(
        "/api/observability/frontend",
        json={
            "type": "navigation",
            "page": "/products",
            "session_id": "session-1",
            "view_id": "view-1",
            "ts": 1,
            "payload": {},
        },
    )

    assert response.status_code == 204


def test_frontend_observability_accepts_sendbeacon_text_payload() -> None:
    client = _client()

    response = client.post(
        "/api/observability/frontend",
        content='{"type":"navigation","page":"/products","session_id":"session-1","view_id":"view-1","ts":1,"payload":{}}',
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )

    assert response.status_code == 204


def test_frontend_observability_drops_invalid_payload_without_422() -> None:
    client = _client()

    response = client.post(
        "/api/observability/frontend",
        content="not-json",
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )

    assert response.status_code == 204
