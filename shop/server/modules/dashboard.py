"""Dashboard module with shared-data demo controls for OCTO Drone Shop."""

from __future__ import annotations

import asyncio
import os
import random
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from server.config import cfg
from server.database import Customer, Order, Product, Ticket, get_db
from server.modules.integrations import CRM_SYNC_STATE, sync_customers_from_crm, sync_order_to_crm
from server.observability.correlation import apply_span_attributes
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.store_service import place_order

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
tracer_fn = get_tracer

_BACKLOG_STATUSES = {"pending", "processing", "queued", "awaiting_dispatch", "backlog"}


class DemoCustomerRequest(BaseModel):
    company: str = Field(default="", max_length=200)
    contact_name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    industry: str = Field(default="Drone Operations", max_length=100)
    revenue: float = Field(default=1500000.0, ge=0.0)
    notes: str = Field(default="", max_length=4000)


class DemoOrderRequest(BaseModel):
    customer_id: int | None = Field(default=None)
    product_id: int | None = Field(default=None)
    count: int = Field(default=1, ge=1, le=50)
    quantity: int = Field(default=1, ge=1, le=25)
    status: str = Field(default="processing", max_length=50)
    shipping_address: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=4000)
    high_value: bool = False


def _make_unique_email(company: str, contact_name: str) -> str:
    base = (contact_name or company or "octo").strip().lower()
    slug = "".join(ch if ch.isalnum() else "." for ch in base).strip(".") or "octo"
    slug = ".".join(filter(None, slug.split(".")))
    email_domain = cfg.dns_domain or os.getenv("SEED_USER_EMAIL_DOMAIN", "example.invalid")
    return f"{slug}.{uuid4().hex[:6]}@{email_domain}"


async def _catalog_snapshot() -> dict:
    async with get_db() as db:
        customer_rows = (
            await db.execute(
                select(Customer.id, Customer.name, Customer.company, Customer.email)
                .order_by(Customer.name.asc())
                .limit(200)
            )
        ).all()
        product_rows = (
            await db.execute(
                select(Product.id, Product.name, Product.price, Product.category, Product.stock, Product.image_url)
                .where(Product.is_active == 1)
                .order_by(Product.price.desc(), Product.name.asc())
                .limit(200)
            )
        ).all()

    return {
        "customers": [
            {
                "id": row.id,
                "name": row.name,
                "company": row.company or "",
                "email": row.email,
            }
            for row in customer_rows
        ],
        "products": [
            {
                "id": row.id,
                "name": row.name,
                "price": float(row.price or 0),
                "category": row.category or "",
                "stock": int(row.stock or 0),
                "image_url": row.image_url or "",
            }
            for row in product_rows
        ],
    }


@router.get("/summary")
async def summary(request: Request):
    """Dashboard summary with shared ATP-backed business state."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("dashboard.summary") as span:
        apply_span_attributes(span, {
            "app.page.name": "dashboard",
            "app.module": "dashboard",
            "app.logical_endpoint": "dashboard.summary",
            "db.target": "oracle-atp",
        })
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.customer_stats"):
                customer_count = int((await db.scalar(select(func.count(Customer.id)))) or 0)
                company_count = int(
                    (
                        await db.scalar(
                            select(func.count(func.distinct(Customer.company)))
                            .where(Customer.company.is_not(None))
                        )
                    ) or 0
                )

            with tracer.start_as_current_span("db.query.order_stats"):
                order_count = int((await db.scalar(select(func.count(Order.id)))) or 0)
                revenue = float((await db.scalar(select(func.coalesce(func.sum(Order.total), 0)))) or 0)
                avg_order = revenue / order_count if order_count else 0.0
                status_rows = (
                    await db.execute(select(Order.status, func.count(Order.id)).group_by(Order.status))
                ).all()
                status_breakdown = {status or "unknown": int(count or 0) for status, count in status_rows}

            with tracer.start_as_current_span("db.query.product_stats"):
                product_count = int((await db.scalar(select(func.count(Product.id)).where(Product.is_active == 1))) or 0)
                low_stock = int(
                    (
                        await db.scalar(
                            select(func.count(Product.id)).where(Product.is_active == 1, Product.stock <= 10)
                        )
                    ) or 0
                )

            with tracer.start_as_current_span("db.query.ticket_stats"):
                ticket_total = int((await db.scalar(select(func.count(Ticket.id)))) or 0)
                ticket_open = int(
                    (
                        await db.scalar(
                            select(func.count(Ticket.id)).where(Ticket.status.in_(["open", "new", "investigating"]))
                        )
                    ) or 0
                )

            with tracer.start_as_current_span("db.query.top_customers"):
                top_customer_rows = (
                    await db.execute(
                        select(Customer.id, Customer.name, Customer.company, Customer.revenue)
                        .order_by(Customer.revenue.desc(), Customer.name.asc())
                        .limit(5)
                    )
                ).all()
                top_customer_ids = [row.id for row in top_customer_rows]
                order_count_rows = []
                if top_customer_ids:
                    order_count_rows = (
                        await db.execute(
                            select(Order.customer_id, func.count(Order.id))
                            .where(Order.customer_id.in_(top_customer_ids))
                            .group_by(Order.customer_id)
                        )
                    ).all()
                order_counts = {customer_id: int(count or 0) for customer_id, count in order_count_rows}
                top_customers = [
                    {
                        "id": row.id,
                        "name": row.name,
                        "company": row.company or "",
                        "revenue": float(row.revenue or 0),
                        "order_count": order_counts.get(row.id, 0),
                    }
                    for row in top_customer_rows
                ]

            with tracer.start_as_current_span("db.query.recent_orders"):
                recent_orders_result = await db.execute(
                    select(Order)
                    .options(selectinload(Order.customer))
                    .order_by(Order.created_at.desc())
                    .limit(10)
                )
                recent_orders = [
                    {
                        "id": order.id,
                        "total": float(order.total or 0),
                        "status": order.status or "unknown",
                        "created_at": order.created_at.isoformat() if order.created_at else None,
                        "customer_name": order.customer.name if order.customer else "Unknown",
                        "customer_company": order.customer.company if order.customer else "",
                    }
                    for order in recent_orders_result.scalars()
                ]

            with tracer.start_as_current_span("db.query.featured_products"):
                featured_rows = (
                    await db.execute(
                        select(Product.id, Product.name, Product.price, Product.category, Product.stock, Product.description, Product.image_url)
                        .where(Product.is_active == 1)
                        .order_by(Product.price.desc(), Product.name.asc())
                        .limit(6)
                    )
                ).all()
                featured_products = [
                    {
                        "id": row.id,
                        "name": row.name,
                        "price": float(row.price or 0),
                        "category": row.category or "",
                        "stock": int(row.stock or 0),
                        "description": row.description or "",
                        "image_url": row.image_url or "",
                    }
                    for row in featured_rows
                ]

        return {
            "customers": {"total": customer_count, "companies": company_count},
            "orders": {
                "total": order_count,
                "revenue": revenue,
                "average": avg_order,
                "backlog": sum(status_breakdown.get(status, 0) for status in _BACKLOG_STATUSES),
                "status_breakdown": status_breakdown,
            },
            "products": {
                "total": product_count,
                "low_stock": low_stock,
            },
            "tickets": {
                "total": ticket_total,
                "open": ticket_open,
            },
            "top_customers": top_customers,
            "recent_orders": recent_orders,
            "featured_products": featured_products,
            "integration": {
                "crm_configured": bool(cfg.enterprise_crm_url),
                "last_sync_epoch": CRM_SYNC_STATE["last_sync_ts"] or None,
                "last_sync_count": CRM_SYNC_STATE["last_count"],
                "last_sync_error": CRM_SYNC_STATE["last_error"] or None,
            },
        }


@router.get("/catalog")
async def dashboard_catalog(request: Request):
    tracer = tracer_fn()
    with tracer.start_as_current_span("dashboard.catalog") as span:
        apply_span_attributes(span, {
            "app.page.name": "dashboard",
            "app.module": "dashboard",
            "app.logical_endpoint": "dashboard.catalog",
        })
        catalog = await _catalog_snapshot()
        span.set_attribute("dashboard.catalog.customers", len(catalog["customers"]))
        span.set_attribute("dashboard.catalog.products", len(catalog["products"]))
        return catalog


@router.post("/demo/customer")
@router.post("/demo/company")
async def create_demo_customer(payload: DemoCustomerRequest, request: Request):
    tracer = tracer_fn()
    company_name = (payload.company or payload.contact_name or "Octo Demo Air Systems").strip()
    contact_name = (payload.contact_name or payload.company or "Demo Buyer").strip()
    email = (payload.email or _make_unique_email(company_name, contact_name)).strip().lower()

    with tracer.start_as_current_span("dashboard.demo.customer") as span:
        apply_span_attributes(span, {
            "app.page.name": "dashboard",
            "app.module": "dashboard",
            "app.logical_endpoint": "dashboard.demo.customer",
            "demo.customer.company": company_name,
        })
        async with get_db() as db:
            existing = await db.scalar(select(Customer.id).where(Customer.email == email))
            if existing:
                email = _make_unique_email(company_name, contact_name)

            customer = Customer(
                name=contact_name,
                email=email,
                phone=payload.phone or "+1-555-0155",
                company=company_name,
                industry=payload.industry or "Drone Operations",
                revenue=float(payload.revenue or 0.0),
                notes=payload.notes or "Created from OCTO Drone Shop dashboard demo controls",
            )
            db.add(customer)
            await db.flush()

        push_log("INFO", "Dashboard created demo customer", **{
            "demo.action": "customer.create",
            "customer.id": customer.id,
            "customer.company": customer.company,
            "customer.email": customer.email,
        })
        return {
            "status": "created",
            "customer": {
                "id": customer.id,
                "name": customer.name,
                "company": customer.company,
                "email": customer.email,
                "industry": customer.industry,
                "revenue": float(customer.revenue or 0),
            },
        }


@router.post("/demo/orders")
async def generate_demo_orders(payload: DemoOrderRequest, request: Request):
    tracer = tracer_fn()
    requested_status = (payload.status or "processing").strip().lower()
    created_orders: list[dict] = []

    with tracer.start_as_current_span("dashboard.demo.orders") as span:
        apply_span_attributes(span, {
            "app.page.name": "dashboard",
            "app.module": "dashboard",
            "app.logical_endpoint": "dashboard.demo.orders",
            "demo.order.count": payload.count,
            "demo.order.status": requested_status,
        })
        async with get_db() as db:
            customer_query = select(Customer).order_by(Customer.id.asc())
            if payload.customer_id:
                customer_query = customer_query.where(Customer.id == payload.customer_id)
            customers = list((await db.execute(customer_query)).scalars())
            if not customers:
                return {"error": "Customer not found"}

            product_query = select(Product).where(Product.is_active == 1)
            if payload.product_id:
                product_query = product_query.where(Product.id == payload.product_id)
            products = list((await db.execute(product_query)).scalars())
            if not products:
                return {"error": "Product not found"}

            if payload.high_value:
                products.sort(key=lambda product: float(product.price or 0), reverse=True)

            for idx in range(payload.count):
                customer = customers[idx % len(customers)] if payload.customer_id else random.choice(customers)
                product = products[0] if payload.high_value else (products[idx % len(products)] if payload.product_id else random.choice(products))
                quantity = payload.quantity if payload.count == 1 else max(1, payload.quantity + random.randint(0, 2))
                if payload.high_value:
                    quantity = max(quantity, random.randint(2, 6))

                shipping_address = (
                    payload.shipping_address
                    or f"{customer.company or customer.name} Logistics Bay, {customer.industry or 'Operations'} Corridor"
                )
                demo_notes = payload.notes or f"Generated from OCTO Drone Shop demo controls (batch={idx + 1}/{payload.count})"

                result = await place_order(
                    db,
                    customer={"id": customer.id, "name": customer.name, "email": customer.email},
                    items=[{
                        "product_id": product.id,
                        "quantity": quantity,
                        "price": float(product.price or 0),
                        "name": product.name,
                        "sku": product.sku,
                        "category": product.category or "",
                        "image_url": product.image_url or "",
                    }],
                    shipping_address=shipping_address,
                    payment_method="invoice",
                    notes=demo_notes,
                    source="dashboard_demo",
                    trace_id=uuid4().hex,
                )
                await db.execute(
                    text("UPDATE orders SET status = :status WHERE id = :order_id"),
                    {"status": requested_status, "order_id": result["order"]["id"]},
                )
                result["order"]["status"] = requested_status
                created_orders.append({
                    "order_id": result["order"]["id"],
                    "customer": customer.name,
                    "customer_email": customer.email,
                    "company": customer.company or "",
                    "product": product.name,
                    "quantity": quantity,
                    "status": requested_status,
                    "total": result["total"],
                    "tracking_number": result["tracking_number"],
                })

        crm_sync_results = []
        for order in created_orders:
            crm_sync_results.append(
                await sync_order_to_crm(
                    order_id=order["order_id"],
                    customer_email=order["customer_email"],
                    total=order["total"],
                    source="dashboard_demo",
                )
            )

        push_log("INFO", "Dashboard generated demo orders", **{
            "demo.action": "orders.generate",
            "demo.order.count": len(created_orders),
            "demo.order.status": requested_status,
        })
        return {
            "status": "created",
            "count": len(created_orders),
            "orders": created_orders,
            "crm_sync": crm_sync_results,
        }


@router.post("/demo/sync-customers")
async def sync_demo_customers(payload: dict | None = None):
    force = True if payload is None else bool(payload.get("force", True))
    limit = 200 if payload is None else max(1, min(int(payload.get("limit", 200) or 200), 500))
    return await sync_customers_from_crm(force=force, limit=limit, source="dashboard_demo")


@router.get("/slow-query")
async def slow_query(delay: float = Query(default=2.0, ge=0.1, le=10.0)):
    """Trigger a deliberately slow query for APM demo."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("dashboard.slow_query") as span:
        apply_span_attributes(span, {
            "demo.type": "slow_query",
            "app.page.name": "dashboard",
            "app.module": "dashboard",
            "app.logical_endpoint": "dashboard.slow_query",
        })

        async with get_db() as db:
            await asyncio.sleep(delay)
            result = await db.execute(
                text(
                    "SELECT c.name, c.company, COUNT(o.id) AS order_count, COALESCE(SUM(o.total), 0) AS total_spent "
                    "FROM customers c LEFT JOIN orders o ON c.id = o.customer_id "
                    "GROUP BY c.name, c.company ORDER BY total_spent DESC"
                )
            )
            rows = [dict(r) for r in result.mappings().all()]

        push_log("WARNING", "Slow query demo executed", **{
            "demo.type": "slow_query",
            "demo.delay_seconds": delay,
            "demo.rows": len(rows),
        })
        return {"query_type": "slow_aggregate", "delay": delay, "rows": len(rows), "data": rows}


@router.get("/n-plus-one")
async def n_plus_one():
    """Trigger N+1 query pattern for APM demo."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("dashboard.n_plus_one") as span:
        apply_span_attributes(span, {
            "demo.type": "n_plus_one",
            "app.page.name": "dashboard",
            "app.module": "dashboard",
            "app.logical_endpoint": "dashboard.n_plus_one",
        })
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

        push_log("WARNING", "N+1 query demo executed", **{
            "demo.type": "n_plus_one",
            "demo.query_count": len(order_list) + 1,
        })
        return {"pattern": "n_plus_one", "orders": len(order_list), "query_count": len(order_list) + 1, "data": order_list}


@router.get("/error-demo")
async def error_demo(error_type: str = Query(default="exception")):
    """Trigger controlled application or database failures for observability."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("dashboard.error_demo") as span:
        apply_span_attributes(span, {
            "demo.type": "error_demo",
            "demo.error_type": error_type,
            "app.page.name": "dashboard",
            "app.module": "dashboard",
            "app.logical_endpoint": "dashboard.error_demo",
        })
        if error_type == "exception":
            raise ValueError("Deliberate error for observability demonstration")
        if error_type == "timeout":
            await asyncio.sleep(30)
            return {"status": "timeout complete"}
        if error_type == "db_error":
            async with get_db() as db:
                await db.execute(text("SELECT * FROM nonexistent_dashboard_table"))
        return {
            "status": "unknown_error_type",
            "available": ["exception", "timeout", "db_error"],
        }
