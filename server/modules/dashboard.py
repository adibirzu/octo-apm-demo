"""Dashboard module — summary, slow queries, N+1 demo, error demo."""

import asyncio
from fastapi import APIRouter
from sqlalchemy import text
from server.database import get_db
from server.observability.otel_setup import get_tracer

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary():
    """Dashboard summary — aggregates from all modules."""
    tracer = get_tracer()
    with tracer.start_as_current_span("dashboard.summary") as span:
        async with get_db() as db:
            customers = (await db.execute(text("SELECT COUNT(*) FROM customers"))).scalar()
            orders = (await db.execute(text("SELECT COUNT(*) FROM orders"))).scalar()
            revenue = (await db.execute(text("SELECT COALESCE(SUM(total),0) FROM orders"))).scalar()
            products = (await db.execute(text("SELECT COUNT(*) FROM products"))).scalar()
            tickets_open = (await db.execute(text("SELECT COUNT(*) FROM tickets WHERE status = 'open'"))).scalar()

        return {
            "customers": customers,
            "orders": orders,
            "revenue": float(revenue),
            "products": products,
            "tickets_open": tickets_open,
        }


@router.get("/slow-query")
async def slow_query():
    """Trigger a deliberately slow query for APM demo."""
    tracer = get_tracer()
    with tracer.start_as_current_span("dashboard.slow_query") as span:
        span.set_attribute("demo.type", "slow_query")

        async with get_db() as db:
            # Simulate a slow aggregate join
            await asyncio.sleep(2)  # artificial delay
            result = await db.execute(
                text("SELECT c.name, COUNT(o.id) as order_count, SUM(o.total) as total_spent "
                     "FROM customers c LEFT JOIN orders o ON c.id = o.customer_id "
                     "GROUP BY c.name ORDER BY total_spent DESC")
            )
            rows = [dict(r) for r in result.mappings().all()]

        return {"query_type": "slow_aggregate", "rows": len(rows), "data": rows}


@router.get("/n-plus-one")
async def n_plus_one():
    """Trigger N+1 query pattern for APM demo."""
    tracer = get_tracer()
    with tracer.start_as_current_span("dashboard.n_plus_one") as span:
        async with get_db() as db:
            orders = await db.execute(text("SELECT id, customer_id, total FROM orders"))
            order_list = [dict(r) for r in orders.mappings().all()]

            for order in order_list:
                with tracer.start_as_current_span("db.query.order_items"):
                    items = await db.execute(
                        text("SELECT * FROM order_items WHERE order_id = :oid"),
                        {"oid": order["id"]},
                    )
                    order["items"] = [dict(i) for i in items.mappings().all()]

        return {"pattern": "n_plus_one", "orders": len(order_list), "data": order_list}


@router.get("/error-demo")
async def error_demo():
    """Trigger a controlled error for observability."""
    raise ValueError("Deliberate error for observability demonstration")
