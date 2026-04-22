"""Push CRM-managed catalog changes into the drone shop service."""

from __future__ import annotations

from typing import Iterable

import httpx

from server.config import cfg
from server.observability.correlation import build_correlation_id, outbound_headers, set_peer_service

_SYNC_PATH = "/api/integrations/crm/catalog-sync"


def shop_catalog_sync_configured() -> bool:
    return bool((cfg.octo_drone_shop_url or "").strip() and (cfg.drone_shop_internal_key or "").strip())


def build_shop_sync_payload(product: dict) -> dict:
    return {
        "name": str(product.get("name", "") or "").strip(),
        "sku": str(product.get("sku", "") or "").strip().upper(),
        "description": str(product.get("description", "") or "").strip(),
        "price": float(product.get("price") or 0.0),
        "stock": int(product.get("stock") or 0),
        "category": str(product.get("category", "") or "").strip(),
        "image_url": str(product.get("image_url", "") or "").strip(),
        "is_active": 1 if int(product.get("is_active", 1) or 0) else 0,
    }


async def sync_products_to_shop(
    products: Iterable[dict],
    *,
    action: str = "upsert",
    correlation_id: str = "",
    source: str = "enterprise-crm-portal",
) -> dict:
    base_url = (cfg.octo_drone_shop_url or "").rstrip("/")
    from server.observability.logging_sdk import push_log
    from server.observability.otel_setup import get_tracer

    tracer = get_tracer()
    resolved_correlation_id = build_correlation_id(correlation_id)
    prepared_products = [build_shop_sync_payload(product) for product in products]

    if not base_url:
        return {"configured": False, "synced": False, "reason": "OCTO_DRONE_SHOP_URL not configured"}
    if not cfg.drone_shop_internal_key:
        return {"configured": False, "synced": False, "reason": "DRONE_SHOP_INTERNAL_KEY not configured"}
    if not prepared_products:
        return {"configured": True, "synced": True, "count": 0, "action": action, "skipped": True}

    url = f"{base_url}{_SYNC_PATH}"

    with tracer.start_as_current_span("catalog.sync.shop") as span:
        span.set_attribute("catalog.sync.action", action)
        span.set_attribute("catalog.sync.count", len(prepared_products))
        span.set_attribute("integration.target_service", "octo-drone-shop")
        set_peer_service(span, "octo-drone-shop", base_url)

        headers = outbound_headers(resolved_correlation_id)
        headers["X-Internal-Service-Key"] = cfg.drone_shop_internal_key

        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                response = await client.post(
                    url,
                    json={
                        "action": action,
                        "source": source,
                        "products": prepared_products,
                    },
                )
            body = response.json()
        except Exception as exc:
            safe_error = str(exc)
            span.set_attribute("catalog.sync.error", safe_error)
            push_log(
                "ERROR",
                "Shop catalog sync failed",
                **{
                    "catalog.sync.action": action,
                    "catalog.sync.count": len(prepared_products),
                    "catalog.sync.reason": safe_error,
                    "integration.target_service": "octo-drone-shop",
                    "correlation.id": resolved_correlation_id,
                },
            )
            return {
                "configured": True,
                "synced": False,
                "action": action,
                "count": len(prepared_products),
                "reason": safe_error,
            }

        synced = response.status_code in (200, 201) and not body.get("error")
        span.set_attribute("catalog.sync.status_code", response.status_code)
        push_log(
            "INFO" if synced else "WARNING",
            "Shop catalog sync completed" if synced else "Shop catalog sync returned error",
            **{
                "catalog.sync.action": action,
                "catalog.sync.count": len(prepared_products),
                "catalog.sync.status_code": response.status_code,
                "integration.target_service": "octo-drone-shop",
                "correlation.id": resolved_correlation_id,
            },
        )
        return {
            "configured": True,
            "synced": synced,
            "action": action,
            "count": len(prepared_products),
            "status_code": response.status_code,
            "response": body,
        }


async def sync_product_to_shop(
    product: dict,
    *,
    action: str = "upsert",
    correlation_id: str = "",
    source: str = "enterprise-crm-portal",
) -> dict:
    return await sync_products_to_shop(
        [product],
        action=action,
        correlation_id=correlation_id,
        source=source,
    )
