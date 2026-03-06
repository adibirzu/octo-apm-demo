"""Shipping module — shipments, warehouses, geo-latency.

VULNS: No auth on status update, no input validation
"""

import asyncio
import random
from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api", tags=["shipping"])

REGION_SHIPPING_DELAY_MS = {
    "us-east-1": 200, "us-west-2": 300, "eu-central-1": 100,
    "eu-west-1": 150, "ap-southeast-1": 800, "ap-northeast-1": 900,
    "sa-east-1": 1200, "af-south-1": 1500, "me-south-1": 700,
    "ap-southeast-2": 1000,
}


@router.get("/shipping")
async def list_shipments():
    """List shipments."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shipping.list") as span:
        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, order_id, tracking_number, carrier, status, "
                     "origin_region, destination_region, shipping_cost, created_at "
                     "FROM shipments ORDER BY created_at DESC")
            )
            shipments = [dict(r) for r in result.mappings().all()]
            span.set_attribute("db.row_count", len(shipments))
        return {"shipments": shipments}


@router.get("/shipping/{shipment_id}")
async def get_shipment(shipment_id: int, request: Request):
    """Get shipment with tracking — VULN: IDOR."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT * FROM shipments WHERE id = :id"), {"id": shipment_id}
        )
        shipment = result.mappings().first()

    if not shipment:
        security_span("idor", severity="low", payload=str(shipment_id),
                      source_ip=request.client.host if request.client else "",
                      endpoint=f"/api/shipping/{shipment_id}")
        return {"error": "Shipment not found"}
    return dict(shipment)


@router.post("/shipping/{shipment_id}/status")
async def update_status(shipment_id: int, payload: dict, request: Request):
    """Update shipment status — VULN: No authentication."""
    new_status = payload.get("status", "")
    async with get_db() as db:
        await db.execute(
            text("UPDATE shipments SET status = :status WHERE id = :id"),
            {"status": new_status, "id": shipment_id},
        )
    return {"status": "updated", "new_status": new_status}


@router.get("/shipping/by-region")
async def by_region(region: str = "", request: Request = None):
    """Shipments by region — with artificial shipping delay per region."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shipping.by_region") as span:
        span.set_attribute("shipping.region", region)

        delay = REGION_SHIPPING_DELAY_MS.get(region, 500)
        with tracer.start_as_current_span("shipping.region_lookup_delay") as d_span:
            d_span.set_attribute("shipping.delay_ms", delay)
            await asyncio.sleep(delay / 1000 * random.uniform(0.8, 1.2))

        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM shipments WHERE destination_region = :region "
                     "OR origin_region = :region ORDER BY created_at DESC"),
                {"region": region},
            )
            shipments = [dict(r) for r in result.mappings().all()]

        return {"shipments": shipments, "region": region, "simulated_delay_ms": delay}


@router.get("/shipping/warehouses")
async def list_warehouses():
    """List warehouses."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT * FROM warehouses WHERE is_active = true ORDER BY region")
        )
        return {"warehouses": [dict(r) for r in result.mappings().all()]}
