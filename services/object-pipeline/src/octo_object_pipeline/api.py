"""FastAPI surface.

OCI Events delivers object-create notifications to /events/object-storage
with the CloudEvents envelope; we extract bucket + object, fetch bytes,
dispatch to the registered handler, and return quickly.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, status

from .handlers import get_handler

logger = logging.getLogger(__name__)


def create_app(*, fetch_object=None) -> FastAPI:
    fetch_object = fetch_object or _default_fetch
    app = FastAPI(title="octo-object-pipeline", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "handlers": list(_registered())}

    @app.post("/events/object-storage", status_code=status.HTTP_202_ACCEPTED)
    async def on_object_event(event: dict[str, Any]) -> dict[str, Any]:
        # CloudEvents envelope — OCI Object Storage events follow
        # https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventsproducers.htm
        try:
            data = event["data"]
            bucket = data["additionalDetails"]["bucketName"]
            object_name = data["resourceName"]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc}")

        handler = get_handler(bucket)
        if handler is None:
            return {
                "ok": False,
                "bucket": bucket,
                "reason": "no handler registered for this bucket",
            }

        body = await fetch_object(bucket=bucket, object_name=object_name)
        result = await handler(body, {"bucket": bucket, "object_name": object_name})

        return {
            "ok": result.ok,
            "bucket": bucket,
            "object_name": object_name,
            "summary": result.summary,
            "data": result.data,
        }

    return app


def _registered() -> list[str]:
    from .handlers import HANDLERS
    return list(HANDLERS.keys())


async def _default_fetch(*, bucket: str, object_name: str) -> bytes:
    """Fetch bytes via OCI Object Storage SDK. Lazy-imported so tests
    can inject a fake fetch_object via create_app()."""
    try:
        import oci  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "oci SDK not installed — pip install '.[oci]' or inject fetch_object"
        ) from exc

    # Auth: instance principal first, falling back to local config.
    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    except Exception:
        client = oci.object_storage.ObjectStorageClient(oci.config.from_file())

    namespace = os.getenv("OCI_OS_NAMESPACE", "")
    if not namespace:
        namespace = client.get_namespace().data

    resp = client.get_object(namespace, bucket, object_name)
    # OCI response stream → bytes
    return resp.data.raw.read()


app = create_app()
