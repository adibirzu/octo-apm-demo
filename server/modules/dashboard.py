"""Dashboard module with ATP-safe summary queries."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from server.database import Customer, Invoice, Order, SupportTicket, get_db
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.order_sync import order_security_summary

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
tracer_fn = get_tracer


@router.get("/summary")
async def dashboard_summary(request: Request):
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.summary"):
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.customer_count"):
                customer_count = int((await db.scalar(select(func.count(Customer.id)))) or 0)

            with tracer.start_as_current_span("db.query.order_stats"):
                order_row = (
                    await db.execute(select(func.count(Order.id), func.coalesce(func.sum(Order.total), 0), func.coalesce(func.avg(Order.total), 0)))
                ).one()
                order_count, total_revenue, avg_order = order_row

            with tracer.start_as_current_span("db.query.ticket_stats"):
                ticket_rows = (
                    await db.execute(select(SupportTicket.status, func.count(SupportTicket.id)).group_by(SupportTicket.status))
                ).all()
                ticket_stats = {status: count for status, count in ticket_rows}

            with tracer.start_as_current_span("db.query.invoice_stats"):
                invoice_rows = (
                    await db.execute(
                        select(Invoice.status, func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount), 0)).group_by(Invoice.status)
                    )
                ).all()
                invoice_stats = [
                    {"status": status, "count": count, "total": float(total or 0)}
                    for status, count, total in invoice_rows
                ]

            with tracer.start_as_current_span("db.query.top_customers"):
                top_customer_rows = (
                    await db.execute(
                        select(Customer.id, Customer.name, Customer.revenue, func.count(Order.id).label("order_count"))
                        .outerjoin(Order, Order.customer_id == Customer.id)
                        .group_by(Customer.id, Customer.name, Customer.revenue)
                        .order_by(Customer.revenue.desc())
                        .limit(5)
                    )
                ).all()
                top_customers = [
                    {"id": row.id, "name": row.name, "revenue": float(row.revenue or 0), "order_count": int(row.order_count or 0)}
                    for row in top_customer_rows
                ]

            with tracer.start_as_current_span("db.query.recent_orders"):
                recent_result = await db.execute(
                    select(Order)
                    .options(selectinload(Order.customer))
                    .order_by(Order.created_at.desc())
                    .limit(10)
                )
                recent_orders = [
                    {
                        "id": order.id,
                        "total": float(order.total or 0),
                        "status": order.status,
                        "created_at": order.created_at.isoformat() if order.created_at else None,
                        "customer_name": order.customer.name if order.customer else "Unknown",
                        "source_system": order.source_system or "enterprise-crm",
                        "backlog_status": order.backlog_status or "current",
                    }
                    for order in recent_result.scalars()
                ]

        return {
            "customers": {"total": customer_count},
            "orders": {
                "total": int(order_count or 0),
                "revenue": float(total_revenue or 0),
                "average": float(avg_order or 0),
            },
            "tickets": ticket_stats,
            "invoices": invoice_stats,
            "top_customers": top_customers,
            "recent_orders": recent_orders,
            "security": await order_security_summary(),
        }


@router.get("/slow-query")
async def slow_query(
    request: Request,
    delay: float = Query(default=2.0, description="Simulated delay in seconds"),
):
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.slow_query"):
        await asyncio.sleep(min(delay, 30.0))
        push_log(
            "WARNING",
            "Slow query endpoint invoked",
            **{
                "performance.delay_seconds": delay,
                "performance.endpoint": "/api/dashboard/slow-query",
            },
        )
        return {"status": "ok", "delay": delay}


@router.get("/n-plus-one")
async def n_plus_one_demo(request: Request):
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.n_plus_one") as span:
        async with get_db() as db:
            customer_rows = (await db.execute(select(Customer.id, Customer.name))).all()

            results = []
            for customer_id, customer_name in customer_rows:
                with tracer.start_as_current_span("db.query.customer_orders") as q_span:
                    q_span.set_attribute("db.customer_id", customer_id)
                    order_count, total = (
                        await db.execute(
                            select(func.count(Order.id), func.coalesce(func.sum(Order.total), 0)).where(Order.customer_id == customer_id)
                        )
                    ).one()
                    results.append(
                        {
                            "customer": customer_name,
                            "order_count": int(order_count or 0),
                            "total": float(total or 0),
                        }
                    )

        span.set_attribute("performance.n_plus_one_queries", len(customer_rows) + 1)
        push_log(
            "WARNING",
            f"N+1 query demo: {len(customer_rows) + 1} queries executed",
            **{
                "performance.query_count": len(customer_rows) + 1,
                "performance.pattern": "n_plus_one",
            },
        )
        return {"results": results, "query_count": len(customer_rows) + 1}


@router.get("/error-demo")
async def error_demo(
    request: Request,
    error_type: str = Query(default="exception", description="Type of error to simulate"),
):
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.error_demo") as span:
        span.set_attribute("error.type", error_type)

        if error_type == "exception":
            raise ValueError("Simulated application exception for APM testing")
        if error_type == "timeout":
            await asyncio.sleep(35)
            return {"status": "timeout completed"}
        if error_type == "memory":
            _ = bytearray(100 * 1024 * 1024)
            return {"status": "allocated 100MB"}
        if error_type == "db_error":
            async with get_db() as db:
                await db.execute(text("SELECT * FROM nonexistent_table"))
        return {"status": "unknown error type", "available": ["exception", "timeout", "memory", "db_error"]}
