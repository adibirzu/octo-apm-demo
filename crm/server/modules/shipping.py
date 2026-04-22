"""Shipping & logistics module — geo-distributed latency simulation.

Vulnerabilities:
- No validation on carrier/tracking number
- No authorization on status updates
- Deliberately slow cross-join for region queries (APM demo)
"""

import asyncio

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import push_log
from server.observability import business_metrics
from server.database import Shipment, get_db

router = APIRouter(prefix="/api/shipping", tags=["Shipping"])
tracer_fn = get_tracer

# Region-based artificial delay (seconds) to simulate geo-distributed latency
REGION_DELAY = {
    "ap-southeast": 0.8,
    "sa-east": 1.2,
    "af-south": 1.5,
}


async def _apply_region_delay(tracer, region: str):
    """Apply artificial delay based on region and log it as a span attribute."""
    delay = REGION_DELAY.get(region, 0)
    if delay > 0:
        with tracer.start_as_current_span("shipping.region_latency") as span:
            span.set_attribute("shipping.region", region)
            span.set_attribute("shipping.artificial_delay_ms", int(delay * 1000))
            await asyncio.sleep(delay)
            push_log("WARN", f"Slow region query: {region} (+{int(delay * 1000)}ms)", **{
                "shipping.region": region,
                "shipping.delay_ms": int(delay * 1000),
            })


@router.get("")
async def list_shipments(
    request: Request,
    status: str = Query(default="", description="Filter by status"),
    carrier: str = Query(default="", description="Filter by carrier"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List shipments with order+customer join."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("shipping.list") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.shipments_list"):
                query = ("SELECT s.*, o.total as order_total, o.customer_id, "
                         "c.name as customer_name "
                         "FROM shipments s "
                         "LEFT JOIN orders o ON s.order_id = o.id "
                         "LEFT JOIN customers c ON o.customer_id = c.id "
                         "WHERE 1=1")
                params = {}
                if status:
                    query += " AND s.status = :status"
                    params["status"] = status
                if carrier:
                    query += " AND s.carrier = :carrier"
                    params["carrier"] = carrier
                query += " ORDER BY s.created_at DESC"
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

        shipments = [dict(r._mapping) for r in rows]
        span.set_attribute("shipping.count", len(shipments))
        return {"shipments": shipments, "total": len(shipments), "limit": limit, "offset": offset}


@router.get("/by-region")
async def shipments_by_region(
    request: Request,
    region: str = Query(default="", description="Filter by origin/destination region"),
):
    """Shipments grouped by origin/destination region — deliberately slow cross-join for some regions."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("shipping.by_region") as span:
        # Apply region-based artificial delay
        if region:
            await _apply_region_delay(tracer, region)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.shipments_by_region"):
                query = ("SELECT origin_region, destination_region, "
                         "COUNT(*) as shipment_count, "
                         "SUM(shipping_cost) as total_cost, "
                         "AVG(weight_kg) as avg_weight "
                         "FROM shipments WHERE 1=1")
                params = {}
                if region:
                    query += " AND (origin_region = :region OR destination_region = :region)"
                    params["region"] = region
                query += " GROUP BY origin_region, destination_region"
                query += " ORDER BY shipment_count DESC"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

        regions = [dict(r._mapping) for r in rows]
        span.set_attribute("shipping.region_count", len(regions))
        return {"regions": regions, "total": len(regions)}


@router.get("/warehouses")
async def list_warehouses(request: Request):
    """List warehouses."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("shipping.warehouses.list") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.warehouses_list"):
                result = await db.execute(
                    text("SELECT * FROM warehouses ORDER BY region, name")
                )
                rows = result.fetchall()

        warehouses = [dict(r._mapping) for r in rows]
        return {"warehouses": warehouses, "total": len(warehouses)}


@router.get("/{shipment_id}")
async def get_shipment(shipment_id: int, request: Request):
    """Get shipment detail with tracking history."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("shipping.get") as span:
        span.set_attribute("shipping.id", shipment_id)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.shipment_detail"):
                result = await db.execute(
                    text("SELECT s.*, o.total as order_total, o.customer_id, "
                         "c.name as customer_name "
                         "FROM shipments s "
                         "LEFT JOIN orders o ON s.order_id = o.id "
                         "LEFT JOIN customers c ON o.customer_id = c.id "
                         "WHERE s.id = :id"),
                    {"id": shipment_id}
                )
                shipment = result.fetchone()

            if not shipment:
                return {"error": "Shipment not found"}

            # Build a synthetic tracking history based on status
            tracking_history = []
            statuses_order = ["processing", "shipped", "in_transit", "delivered"]
            shipment_dict = dict(shipment._mapping)
            current_status = shipment_dict.get("status", "processing")
            for s in statuses_order:
                tracking_history.append({
                    "status": s,
                    "reached": statuses_order.index(s) <= statuses_order.index(current_status)
                        if current_status in statuses_order else s == current_status,
                })

        return {
            "shipment": shipment_dict,
            "tracking_history": tracking_history,
        }


@router.post("")
async def create_shipment(request: Request):
    """Create shipment — VULN: no validation on carrier/tracking number."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("shipping.create") as span:
        # VULN: no validation on carrier or tracking_number — accepts anything
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.shipment_insert"):
                shipment = Shipment(
                    order_id=body.get("order_id"),
                    tracking_number=body.get("tracking_number", ""),
                    carrier=body.get("carrier", ""),  # VULN: no validation
                    status="processing",
                    origin_region=body.get("origin_region", ""),
                    destination_region=body.get("destination_region", ""),
                    weight_kg=body.get("weight_kg", 0.0),
                    shipping_cost=body.get("shipping_cost", 0.0),
                    estimated_delivery=body.get("estimated_delivery"),
                )
                db.add(shipment)
                await db.flush()
                shipment_id = shipment.id

        business_metrics.record_shipment_created(
            carrier=body.get("carrier", ""),
            origin_region=body.get("origin_region", ""),
            destination_region=body.get("destination_region", ""),
        )
        cost = float(body.get("shipping_cost", 0))
        if cost > 0:
            business_metrics.record_shipping_cost_value(cost, carrier=body.get("carrier", ""))
        push_log("INFO", f"Shipment #{shipment_id} created", **{
            "shipping.id": shipment_id,
            "shipping.carrier": body.get("carrier", ""),
            "shipping.origin": body.get("origin_region", ""),
            "shipping.destination": body.get("destination_region", ""),
        })
        return {"status": "created", "shipment_id": shipment_id}


@router.patch("/{shipment_id}/status")
async def update_shipment_status(shipment_id: int, request: Request):
    """Update shipment status — VULN: no auth."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()
    new_status = body.get("status", "")

    with tracer.start_as_current_span("shipping.update_status") as span:
        span.set_attribute("shipping.id", shipment_id)
        span.set_attribute("shipping.new_status", new_status)

        # VULN: no authorization — any user can update any shipment status
        with security_span("broken_access_control", severity="medium",
                         payload=f"shipment_id={shipment_id} status={new_status}",
                         source_ip=client_ip):
            pass

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.shipment_status_update"):
                update_sql = "UPDATE shipments SET status = :status"
                params = {"status": new_status, "sid": shipment_id}

                if new_status == "delivered":
                    update_sql += ", actual_delivery = CURRENT_TIMESTAMP"

                update_sql += " WHERE id = :sid"
                await db.execute(text(update_sql), params)

        if new_status == "delivered":
            business_metrics.record_shipment_delivered()
        push_log("INFO", f"Shipment #{shipment_id} status updated to '{new_status}'", **{
            "shipping.id": shipment_id,
            "shipping.new_status": new_status,
        })
        return {"status": "updated", "shipment_id": shipment_id, "new_status": new_status}
