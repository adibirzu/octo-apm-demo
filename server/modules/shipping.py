"""Shipping module — shipments, warehouses, geo-latency."""

import asyncio
import random
from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer

router = APIRouter(prefix="/api", tags=["shipping"])

REGION_SHIPPING_DELAY_MS = {
    "us-east-1": 200, "us-west-2": 300, "eu-central-1": 100,
    "eu-west-1": 150, "ap-southeast-1": 800, "ap-northeast-1": 900,
    "sa-east-1": 1200, "af-south-1": 1500, "me-south-1": 700,
    "ap-southeast-2": 1000,
}

_VALID_STATUSES = {"processing", "shipped", "in_transit", "delivered", "returned", "cancelled"}


@router.get("/shipping")
async def list_shipments():
    """List shipments."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shipping.list") as span:
        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, order_id, tracking_number, carrier, status, "
                     "origin_region, destination_region, weight_kg, shipping_cost, "
                     "estimated_delivery, actual_delivery, created_at "
                     "FROM shipments ORDER BY created_at DESC")
            )
            shipments = [dict(r) for r in result.mappings().all()]
            span.set_attribute("db.row_count", len(shipments))
        return {"shipments": shipments}


@router.get("/shipping/{shipment_id}")
async def get_shipment(shipment_id: int):
    """Get shipment with tracking details."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shipping.get") as span:
        span.set_attribute("shipping.shipment_id", shipment_id)
        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM shipments WHERE id = :id"), {"id": shipment_id}
            )
            shipment = result.mappings().first()

        if not shipment:
            span.set_attribute("shipping.found", False)
            return {"error": "Shipment not found"}
        span.set_attribute("shipping.found", True)
        span.set_attribute("shipping.status", str(shipment.get("status", "")))
        span.set_attribute("shipping.carrier", str(shipment.get("carrier", "")))
        return dict(shipment)


@router.post("/shipping/{shipment_id}/status")
async def update_status(shipment_id: int, payload: dict):
    """Update shipment status with validation."""
    tracer = get_tracer()
    with tracer.start_as_current_span("shipping.update_status") as span:
        new_status = str(payload.get("status", "")).strip().lower()
        span.set_attribute("shipping.shipment_id", shipment_id)
        span.set_attribute("shipping.new_status", new_status)
        if new_status not in _VALID_STATUSES:
            return {"error": f"Invalid status. Must be one of: {', '.join(sorted(_VALID_STATUSES))}"}

        async with get_db() as db:
            exists = await db.execute(
                text("SELECT id FROM shipments WHERE id = :id"), {"id": shipment_id}
            )
            if not exists.first():
                span.set_attribute("shipping.found", False)
                return {"error": "Shipment not found"}

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
    tracer = get_tracer()
    with tracer.start_as_current_span("shipping.warehouses") as span:
        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM warehouses WHERE is_active = 1 ORDER BY region")
            )
            warehouses = [dict(r) for r in result.mappings().all()]
            span.set_attribute("db.row_count", len(warehouses))
        return {"warehouses": warehouses}
