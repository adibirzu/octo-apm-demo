"""Analytics module — cross-module metrics, geo performance, conversion funnel.

Vulnerabilities:
- SQL injection in region filter (geo endpoint)
- Deliberately slow multi-query patterns for APM demo
- Region-based artificial latency to simulate geo-distributed performance
"""

import asyncio

from fastapi import APIRouter, Request, Query, Header
from sqlalchemy import text

from server.database import PageView
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.observability import business_metrics
from server.database import get_db

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
tracer_fn = get_tracer

# Region-based artificial latency (seconds) to create visible differences in APM traces
REGION_LATENCY = {
    "us-east-1": 0.05,      # 50ms - closest
    "us-west-2": 0.12,      # 120ms
    "eu-west-1": 0.18,      # 180ms
    "eu-central-1": 0.22,   # 220ms
    "ap-southeast-1": 0.35, # 350ms
    "ap-northeast-1": 0.40, # 400ms
    "sa-east-1": 0.55,      # 550ms
    "af-south-1": 0.70,     # 700ms
    "me-south-1": 0.45,     # 450ms
}


async def _apply_region_latency(tracer, region: str):
    """Apply artificial latency based on region, logged as a span attribute."""
    delay = REGION_LATENCY.get(region, 0)
    if delay > 0:
        with tracer.start_as_current_span("analytics.region_latency") as span:
            span.set_attribute("analytics.region", region)
            span.set_attribute("analytics.artificial_delay_ms", int(delay * 1000))
            span.set_attribute("analytics.delay_reason", "geo_distance_simulation")
            await asyncio.sleep(delay)
            push_log("WARN", f"Region latency applied: {region} (+{int(delay * 1000)}ms)", **{
                "analytics.region": region,
                "analytics.delay_ms": int(delay * 1000),
            })


def _detect_region(region_param: str, header_region: str) -> str:
    """Detect region from query param or header."""
    return region_param or header_region or ""


@router.get("/overview")
async def overview(request: Request):
    """Cross-module summary — does 6+ DB queries with individual spans."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("analytics.overview") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.total_customers"):
                r = await db.execute(text("SELECT COUNT(*) FROM customers"))
                total_customers = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.total_orders"):
                r = await db.execute(text("SELECT COUNT(*) FROM orders"))
                total_orders = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.total_revenue"):
                r = await db.execute(text("SELECT COALESCE(SUM(total), 0) FROM orders"))
                total_revenue = float(r.fetchone()[0])

            with tracer.start_as_current_span("db.query.total_campaigns"):
                r = await db.execute(text("SELECT COUNT(*) FROM campaigns"))
                total_campaigns = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.total_shipments"):
                r = await db.execute(text("SELECT COUNT(*) FROM shipments"))
                total_shipments = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.total_leads"):
                r = await db.execute(text("SELECT COUNT(*) FROM leads"))
                total_leads = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.active_campaigns"):
                r = await db.execute(
                    text("SELECT COUNT(*) FROM campaigns WHERE status = 'active'")
                )
                active_campaigns = r.fetchone()[0]

        span.set_attribute("analytics.total_customers", total_customers)
        span.set_attribute("analytics.total_orders", total_orders)
        span.set_attribute("analytics.total_revenue", total_revenue)

        return {
            "total_customers": total_customers,
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_campaigns": total_campaigns,
            "active_campaigns": active_campaigns,
            "total_shipments": total_shipments,
            "total_leads": total_leads,
        }


@router.get("/geo")
async def geo_analytics(
    request: Request,
    region: str = Query(default="", description="Filter by visitor region"),
    x_client_region: str = Header(default="", alias="X-Client-Region"),
):
    """Page views grouped by region with load time percentiles — VULN: SQL injection in region filter."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    effective_region = _detect_region(region, x_client_region)

    with tracer.start_as_current_span("analytics.geo") as span:
        span.set_attribute("analytics.region_filter", effective_region)

        # Apply region-based latency
        if effective_region:
            await _apply_region_latency(tracer, effective_region)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.geo_page_views"):
                # VULN: SQL injection — region is interpolated directly
                if effective_region:
                    # VULN: f-string SQL injection
                    query = (f"SELECT visitor_region, COUNT(*) as view_count, "
                             f"AVG(load_time_ms) as avg_load_time, "
                             f"MIN(load_time_ms) as min_load_time, "
                             f"MAX(load_time_ms) as max_load_time "
                             f"FROM page_views "
                             f"WHERE visitor_region = '{effective_region}' "
                             f"GROUP BY visitor_region "
                             f"ORDER BY view_count DESC")

                    with security_span("sql_injection", severity="critical",
                                     payload=effective_region,
                                     source_ip=client_ip):
                        log_security_event("sql_injection", "critical",
                            f"Unparameterized region filter in geo query: {effective_region}",
                            source_ip=client_ip, payload=effective_region)

                    result = await db.execute(text(query))
                else:
                    result = await db.execute(
                        text("SELECT visitor_region, COUNT(*) as view_count, "
                             "AVG(load_time_ms) as avg_load_time, "
                             "MIN(load_time_ms) as min_load_time, "
                             "MAX(load_time_ms) as max_load_time "
                             "FROM page_views "
                             "GROUP BY visitor_region "
                             "ORDER BY view_count DESC")
                    )
                rows = result.fetchall()

        regions = [dict(r._mapping) for r in rows]
        return {"regions": regions, "total": len(regions)}


@router.get("/funnel")
async def conversion_funnel(request: Request):
    """Conversion funnel: leads -> qualified -> customers -> orders (4 sequential queries)."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("analytics.funnel") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.funnel_total_leads"):
                r = await db.execute(text("SELECT COUNT(*) FROM leads"))
                total_leads = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.funnel_qualified_leads"):
                r = await db.execute(
                    text("SELECT COUNT(*) FROM leads WHERE status IN ('qualified', 'converted')")
                )
                qualified_leads = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.funnel_converted_customers"):
                r = await db.execute(
                    text("SELECT COUNT(DISTINCT customer_id) FROM leads "
                         "WHERE status = 'converted' AND customer_id IS NOT NULL")
                )
                converted_customers = r.fetchone()[0]

            with tracer.start_as_current_span("db.query.funnel_orders_from_leads"):
                r = await db.execute(
                    text("SELECT COUNT(DISTINCT o.id) FROM orders o "
                         "INNER JOIN leads l ON l.customer_id = o.customer_id "
                         "WHERE l.status = 'converted'")
                )
                orders_from_leads = r.fetchone()[0]

        funnel = [
            {"stage": "leads", "count": total_leads},
            {"stage": "qualified", "count": qualified_leads},
            {"stage": "converted_to_customer", "count": converted_customers},
            {"stage": "placed_order", "count": orders_from_leads},
        ]
        return {"funnel": funnel}


@router.get("/revenue-by-region")
async def revenue_by_region(request: Request):
    """Revenue breakdown by shipping destination region."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("analytics.revenue_by_region") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.revenue_by_dest_region"):
                result = await db.execute(
                    text("SELECT s.destination_region, "
                         "COUNT(DISTINCT s.order_id) as order_count, "
                         "COALESCE(SUM(o.total), 0) as total_revenue, "
                         "COALESCE(SUM(s.shipping_cost), 0) as total_shipping_cost "
                         "FROM shipments s "
                         "LEFT JOIN orders o ON s.order_id = o.id "
                         "GROUP BY s.destination_region "
                         "ORDER BY total_revenue DESC")
                )
                rows = result.fetchall()

        regions = [dict(r._mapping) for r in rows]
        return {"regions": regions, "total": len(regions)}


@router.post("/track")
async def track_page_view(request: Request):
    """Record a page view — accepts visitor_region, page, load_time_ms from client."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("analytics.track") as span:
        page = body.get("page", "/")
        visitor_region = body.get("visitor_region", "")
        load_time_ms = body.get("load_time_ms", 0)

        span.set_attribute("analytics.page", page)
        span.set_attribute("analytics.visitor_region", visitor_region)
        span.set_attribute("analytics.load_time_ms", load_time_ms)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.page_view_insert"):
                pv = PageView(
                    page=page,
                    visitor_ip=client_ip,
                    visitor_region=visitor_region,
                    user_agent=body.get("user_agent", request.headers.get("user-agent", "")),
                    load_time_ms=load_time_ms,
                    referrer=body.get("referrer", ""),
                    session_id=body.get("session_id", ""),
                )
                db.add(pv)
                await db.flush()
                pv_id = pv.id

        business_metrics.record_page_view(page=page, region=visitor_region, load_time_ms=load_time_ms)
        push_log("INFO", f"Page view tracked: {page}", **{
            "analytics.page_view_id": pv_id,
            "analytics.page": page,
            "analytics.region": visitor_region,
            "analytics.load_time_ms": load_time_ms,
        })
        return {"status": "tracked", "page_view_id": pv_id}


@router.get("/performance")
async def performance_by_region(
    request: Request,
    region: str = Query(default="", description="Filter by region"),
    x_client_region: str = Header(default="", alias="X-Client-Region"),
):
    """Page load time stats by region — shows different regions having different avg load times."""
    tracer = tracer_fn()
    effective_region = _detect_region(region, x_client_region)

    with tracer.start_as_current_span("analytics.performance") as span:
        span.set_attribute("analytics.region_filter", effective_region)

        # Apply region-based latency
        if effective_region:
            await _apply_region_latency(tracer, effective_region)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.performance_by_region"):
                query = ("SELECT visitor_region, "
                         "COUNT(*) as total_views, "
                         "AVG(load_time_ms) as avg_load_time, "
                         "MIN(load_time_ms) as p0_load_time, "
                         "MAX(load_time_ms) as p100_load_time "
                         "FROM page_views WHERE 1=1")
                params = {}
                if effective_region:
                    query += " AND visitor_region = :region"
                    params["region"] = effective_region
                query += " GROUP BY visitor_region ORDER BY avg_load_time DESC"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

        regions = [dict(r._mapping) for r in rows]
        return {"regions": regions, "total": len(regions)}
