"""PR-3: /api/integrations/schema must publish the cross-service contract
so the Enterprise CRM side (and operators in a new tenancy) can discover
endpoint shapes, required auth headers, and idempotency requirements
without reading app source.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.modules.integrations import router


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.portability
def test_schema_endpoint_returns_openapi_subset(client: TestClient) -> None:
    resp = client.get("/api/integrations/schema")
    assert resp.status_code == 200
    body = resp.json()
    assert body["openapi"].startswith("3."), "must advertise OpenAPI 3.x"
    # Must document the endpoints the CRM side relies on
    paths = body.get("paths", {})
    assert any(p.startswith("/api/integrations/crm/sync-order") for p in paths)
    assert any(p.startswith("/api/integrations/crm/catalog-sync") for p in paths) or \
           any(p.startswith("/api/integrations/crm/sync-customers") for p in paths)


@pytest.mark.portability
@pytest.mark.security
def test_schema_declares_internal_service_key_header(client: TestClient) -> None:
    body = client.get("/api/integrations/schema").json()
    # The shared auth scheme must be declared so CRM implementers know to
    # send it on order-sync callbacks.
    schemes = (
        body.get("components", {}).get("securitySchemes", {})
    )
    assert "InternalServiceKey" in schemes, (
        "Shared-key auth scheme must be advertised in the integration schema"
    )
    assert schemes["InternalServiceKey"]["type"] == "apiKey"
    assert schemes["InternalServiceKey"]["in"] == "header"
    assert schemes["InternalServiceKey"]["name"] == "X-Internal-Service-Key"


@pytest.mark.portability
def test_schema_declares_idempotency_token_on_order_sync(client: TestClient) -> None:
    body = client.get("/api/integrations/schema").json()
    # Look up the order-sync request body schema
    order_path = body["paths"]["/api/integrations/crm/sync-order"]
    post = order_path["post"]
    schema = post["requestBody"]["content"]["application/json"]["schema"]
    properties = schema.get("properties", {})
    assert "idempotency_token" in properties
