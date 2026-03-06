"""Analytics module — overview, geo, funnel, page views.

VULNS: SQLi (geo region), no auth on analytics
"""

import asyncio
import random
from fastapi import APIRouter, Request
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

REGION_LATENCY = {
    "eu-central-1": 50, "eu-west-1": 80, "us-east-1": 120,
    "us-west-2": 150, "ap-southeast-1": 300, "ap-northeast-1": 350,
    "ap-southeast-2": 380, "sa-east-1": 450, "af-south-1": 700,
    "me-south-1": 250,
}


@router.get("/overview")
async def analytics_overview():
    """Cross-module analytics summary — 7 DB queries for APM demo."""
    tracer = get_tracer()
    with tracer.start_as_current_span("analytics.overview") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.customer_count"):
                r1 = await db.execute(text("SELECT COUNT(*) FROM customers"))
                total_customers = r1.scalar()

            with tracer.start_as_current_span("db.query.order_count"):
                r2 = await db.execute(text("SELECT COUNT(*) FROM orders"))
                total_orders = r2.scalar()

            with tracer.start_as_current_span("db.query.revenue"):
                r3 = await db.execute(text("SELECT COALESCE(SUM(total), 0) FROM orders WHERE status = 'completed'"))
                total_revenue = r3.scalar()

            with tracer.start_as_current_span("db.query.product_count"):
                r4 = await db.execute(text("SELECT COUNT(*) FROM products WHERE is_active = true"))
                total_products = r4.scalar()

            with tracer.start_as_current_span("db.query.campaigns"):
                r5 = await db.execute(text("SELECT COUNT(*) FROM campaigns WHERE status = 'active'"))
                active_campaigns = r5.scalar()

            with tracer.start_as_current_span("db.query.shipments"):
                r6 = await db.execute(text("SELECT COUNT(*) FROM shipments WHERE status IN ('shipped','in_transit')"))
                in_transit = r6.scalar()

            with tracer.start_as_current_span("db.query.leads"):
                r7 = await db.execute(text("SELECT COUNT(*) FROM leads"))
                total_leads = r7.scalar()

        return {
            "total_customers": total_customers,
            "total_orders": total_orders,
            "total_revenue": float(total_revenue),
            "total_products": total_products,
            "active_campaigns": active_campaigns,
            "shipments_in_transit": in_transit,
            "total_leads": total_leads,
        }


@router.get("/geo")
async def analytics_geo(region: str = "", request: Request = None):
    """Geo analytics — VULN: SQL injection in region parameter."""
    tracer = get_tracer()
    source_ip = request.client.host if request and request.client else "unknown"

    with tracer.start_as_current_span("analytics.geo") as span:
        span.set_attribute("analytics.region", region)

        delay = REGION_LATENCY.get(region, 100)
        await asyncio.sleep(delay / 1000 * random.uniform(0.8, 1.2))

        async with get_db() as db:
            if region:
                # VULN: SQL injection in region filter
                query = (f"SELECT visitor_region, COUNT(*) as view_count, "
                         f"AVG(load_time_ms) as avg_load_time "
                         f"FROM page_views WHERE visitor_region = '{region}' "
                         f"GROUP BY visitor_region ORDER BY view_count DESC")

                if any(c in region for c in ["'", ";", "--", "UNION"]):
                    security_span("sqli", severity="critical", payload=region,
                                  source_ip=source_ip, endpoint="/api/analytics/geo")
            else:
                query = ("SELECT visitor_region, COUNT(*) as view_count, "
                         "AVG(load_time_ms) as avg_load_time "
                         "FROM page_views GROUP BY visitor_region ORDER BY view_count DESC")

            result = await db.execute(text(query))
            regions = [dict(r) for r in result.mappings().all()]

        return {"regions": regions, "total": len(regions)}


@router.get("/funnel")
async def analytics_funnel():
    """Conversion funnel — 4 sequential queries (slow by design)."""
    tracer = get_tracer()
    with tracer.start_as_current_span("analytics.funnel") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.visitors"):
                r1 = await db.execute(text("SELECT COUNT(DISTINCT session_id) FROM page_views"))
                visitors = r1.scalar()

            with tracer.start_as_current_span("db.query.cart_adds"):
                r2 = await db.execute(text("SELECT COUNT(DISTINCT session_id) FROM cart_items"))
                cart_adds = r2.scalar()

            with tracer.start_as_current_span("db.query.orders_placed"):
                r3 = await db.execute(text("SELECT COUNT(*) FROM orders"))
                orders_placed = r3.scalar()

            with tracer.start_as_current_span("db.query.completed"):
                r4 = await db.execute(text("SELECT COUNT(*) FROM orders WHERE status = 'completed'"))
                completed = r4.scalar()

        return {
            "funnel": [
                {"stage": "Visitors", "count": visitors or 0},
                {"stage": "Added to Cart", "count": cart_adds or 0},
                {"stage": "Placed Order", "count": orders_placed or 0},
                {"stage": "Completed", "count": completed or 0},
            ]
        }


@router.post("/track")
async def track_pageview(payload: dict, request: Request):
    """Track a page view — VULN: No validation, stored XSS in referrer."""
    source_ip = request.client.host if request.client else ""
    async with get_db() as db:
        await db.execute(
            text("INSERT INTO page_views (page, visitor_ip, visitor_region, "
                 "load_time_ms, session_id, user_agent, referrer) "
                 "VALUES (:page, :ip, :region, :load_time, :session, :ua, :ref)"),
            {
                "page": payload.get("page", "/"),
                "ip": source_ip,
                "region": payload.get("visitor_region", ""),
                "load_time": payload.get("load_time_ms", 0),
                "session": payload.get("session_id", ""),
                "ua": request.headers.get("user-agent", ""),
                "ref": payload.get("referrer", ""),
            },
        )
    return {"status": "tracked"}
