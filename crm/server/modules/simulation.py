"""Simulation control module — toggles chaos flags, simulates issues,
generates demo data, and proxies commands to the drone shop.

Allows runtime control of DB latency, disconnects, memory leaks, CPU spikes,
plus one-click order/customer generation for demo environments.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text, select, func as sa_func

from server.config import cfg
from server.database import Customer, Order, OrderItem, Product, async_session_factory
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log
from server.observability.correlation import build_correlation_id, outbound_headers
from server.order_sync import sync_external_orders, external_orders_base_url

logger = logging.getLogger(__name__)


async def _safe_json(request: Request) -> dict:
    """Parse request body as JSON, returning {} on empty/malformed bodies."""
    if not request.headers.get("content-type", "").startswith("application/json"):
        return {}
    try:
        body = await request.body()
        if not body or body.strip() == b"":
            return {}
        return await request.json()
    except Exception:
        return {}

router = APIRouter(prefix="/api/simulate", tags=["Issue Simulation"])
tracer_fn = get_tracer

# ── Runtime-mutable simulation state ──────────────────────────────
_sim_state = {
    "db_latency": False,
    "db_disconnect": False,
    "memory_leak": False,
    "cpu_spike": False,
    "slow_queries": False,
    "error_rate": 0.0,
}


class SimulationConfig(BaseModel):
    db_latency: bool | None = None
    db_disconnect: bool | None = None
    memory_leak: bool | None = None
    cpu_spike: bool | None = None
    slow_queries: bool | None = None
    error_rate: float | None = None


# ── Status & Configuration ────────────────────────────────────────

@router.get("/status")
async def simulation_status(request: Request):
    """Get current simulation state."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("simulation.status"):
        return {"simulation": _sim_state}


@router.post("/configure")
async def configure_simulation(config: SimulationConfig, request: Request):
    """Toggle simulation flags at runtime."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.configure") as span:
        changes = {}
        for field, value in config.model_dump(exclude_none=True).items():
            old = _sim_state.get(field)
            _sim_state[field] = value
            changes[field] = {"old": old, "new": value}
            span.set_attribute(f"simulation.{field}", value)

        push_log("WARNING", "Simulation configuration changed", **{
            "simulation.changes": str(changes),
        })
        return {"status": "updated", "changes": changes, "current": _sim_state}


@router.post("/reset")
async def reset_simulation(request: Request):
    """Reset all simulation flags to off."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("simulation.reset"):
        for key in _sim_state:
            _sim_state[key] = False if isinstance(_sim_state[key], bool) else 0.0
        push_log("INFO", "Simulation state reset to defaults")
        return {"status": "reset", "current": _sim_state}


# ── One-Shot Incidents ────────────────────────────────────────────

@router.post("/db-latency")
async def trigger_db_latency(request: Request):
    """Manually trigger a DB latency spike (one-shot)."""
    tracer = tracer_fn()
    body = await _safe_json(request)
    delay = min(body.get("delay_seconds", 3.0), 30.0)

    with tracer.start_as_current_span("simulation.db_latency") as span:
        span.set_attribute("simulation.delay_seconds", delay)
        await asyncio.sleep(delay)
        push_log("WARNING", f"Simulated DB latency: {delay}s", **{
            "simulation.type": "db_latency",
            "simulation.delay": delay,
        })
        return {"status": "completed", "type": "db_latency", "delay": delay}


@router.post("/db-disconnect")
async def trigger_db_disconnect(request: Request):
    """Simulate a temporary DB disconnect (10s)."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.db_disconnect") as span:
        _sim_state["db_disconnect"] = True
        push_log("ERROR", "Simulated DB disconnect activated", **{
            "simulation.type": "db_disconnect",
        })
        await asyncio.sleep(10)
        _sim_state["db_disconnect"] = False
        return {"status": "completed", "type": "db_disconnect", "duration": "10s"}


@router.post("/error-burst")
async def trigger_error_burst(request: Request):
    """Generate a burst of errors for log/APM testing."""
    tracer = tracer_fn()
    body = await _safe_json(request)
    count = min(body.get("count", 10), 100)

    with tracer.start_as_current_span("simulation.error_burst") as span:
        span.set_attribute("simulation.error_count", count)
        for i in range(count):
            with tracer.start_as_current_span(f"simulation.error_{i}") as err_span:
                err_span.set_attribute("error.simulated", True)
                err_span.set_attribute("error.index", i)
                push_log("ERROR", f"Simulated error {i+1}/{count}", **{
                    "simulation.type": "error_burst",
                    "simulation.index": i,
                })

        return {"status": "completed", "type": "error_burst", "errors_generated": count}


@router.post("/slow-query")
async def trigger_slow_query(request: Request):
    """One-shot slow query: executes a real DB call with artificial delay."""
    tracer = tracer_fn()
    body = await _safe_json(request)
    delay = min(body.get("delay_seconds", 2.0), 10.0)

    with tracer.start_as_current_span("simulation.slow_query") as span:
        span.set_attribute("simulation.delay_seconds", delay)
        # Use Python-side sleep + a real DB round-trip instead of DBMS_LOCK.SLEEP
        # which requires EXECUTE privilege not available on Oracle ATP by default.
        await asyncio.sleep(delay)
        async with async_session_factory() as session:
            await session.execute(
                text("SELECT /*+ simulation.slow_query */ COUNT(*) FROM orders")
            )
        push_log("WARNING", f"Simulated slow query: {delay}s")
        return {"status": "completed", "type": "slow_query", "delay": delay}


@router.post("/n-plus-one")
async def trigger_n_plus_one(request: Request):
    """Simulate an N+1 query problem by executing N individual SELECTs."""
    tracer = tracer_fn()
    body = await _safe_json(request)
    n = min(body.get("count", 50), 200)

    with tracer.start_as_current_span("simulation.n_plus_one") as span:
        span.set_attribute("simulation.n_queries", n)
        async with async_session_factory() as session:
            for i in range(n):
                with tracer.start_as_current_span(f"db.select_order_{i}"):
                    await session.execute(
                        text("SELECT * FROM orders WHERE id = :id"),
                        {"id": i + 1},
                    )
        push_log("WARNING", f"Simulated N+1: {n} individual queries")
        return {"status": "completed", "type": "n_plus_one", "queries_executed": n}


@router.post("/app-exception")
async def trigger_app_exception(request: Request):
    """Raise a deliberate application error for APM error tracking."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.app_exception") as span:
        span.set_attribute("error.simulated", True)
        try:
            raise ValueError("Simulated application exception for APM testing")
        except ValueError as e:
            span.record_exception(e)
            span.set_attribute("otel.status_code", "ERROR")
            push_log("ERROR", f"Simulated app exception: {e}", **{
                "simulation.type": "app_exception",
                "error.type": "ValueError",
            })
            return {"status": "completed", "type": "app_exception", "error": str(e)}


@router.post("/db-error")
async def trigger_db_error(request: Request):
    """Simulate a DB error by temporarily enabling disconnect for 5s."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.db_error") as span:
        _sim_state["db_disconnect"] = True
        push_log("ERROR", "Simulated DB error (5s disconnect)", **{
            "simulation.type": "db_error",
        })
        await asyncio.sleep(5)
        _sim_state["db_disconnect"] = False
        return {"status": "completed", "type": "db_error", "duration": "5s"}


# ── Demo Data Generation ─────────────────────────────────────────

_FAKE_COMPANIES = [
    ("Quantum Dynamics", "Technology", 12000000),
    ("Vector Air Mobility", "Aerospace", 5800000),
    ("NovaTech Solutions", "Software", 3200000),
    ("Pacific Rim Trading", "Logistics", 8500000),
    ("Aurora BioSciences", "Healthcare", 15000000),
    ("Pinnacle Manufacturing", "Industrial", 9200000),
    ("Stellar Communications", "Telecom", 7100000),
    ("Atlas Infrastructure", "Construction", 6400000),
]

_FAKE_CONTACTS = [
    "Morgan Lee", "Jordan Chen", "Taylor Kim", "Alex Rivera",
    "Casey Wright", "Quinn Torres", "Riley Patel", "Drew Nguyen",
]

_ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]


async def _random_customer_id() -> int | None:
    """Pick a random existing customer ID from the database."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM customers ORDER BY DBMS_RANDOM.VALUE FETCH FIRST 1 ROWS ONLY")
        )
        row = result.first()
        return row[0] if row else None


async def _random_product() -> tuple[int, float] | None:
    """Pick a random product (id, price) from the database."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id, price FROM products ORDER BY DBMS_RANDOM.VALUE FETCH FIRST 1 ROWS ONLY")
        )
        row = result.first()
        return (row[0], float(row[1])) if row else None


@router.post("/generate-orders")
async def generate_orders(request: Request):
    """Generate random orders for demo/stress testing."""
    tracer = tracer_fn()
    body = await _safe_json(request)
    count = max(1, min(body.get("count", 5), 50))
    customer_id = body.get("customer_id")
    product_id = body.get("product_id")
    status = body.get("status", "processing")
    high_value = body.get("high_value", False)

    with tracer.start_as_current_span("simulation.generate_orders") as span:
        span.set_attribute("simulation.order_count", count)
        order_ids = []
        total_value = 0.0

        async with async_session_factory() as session:
            for _ in range(count):
                cid = customer_id or await _random_customer_id()
                if not cid:
                    return {"status": "error", "reason": "no customers in database"}
                prod = await _random_product()
                if not prod:
                    return {"status": "error", "reason": "no products in database"}
                pid, price = prod if not product_id else (product_id, prod[1])
                qty = random.randint(1, body.get("max_quantity", 5))

                if high_value:
                    price = random.uniform(10000, 30000)
                    qty = random.randint(2, 5)

                order_total = round(price * qty, 2)
                total_value += order_total
                sid = f"sim-{uuid4().hex[:12]}"

                await session.execute(
                    text(
                        "INSERT INTO orders (customer_id, total, status, source_system, "
                        "source_order_id, sync_status, backlog_status, correlation_id, created_at) "
                        "VALUES (:cid, :total, :status, 'crm-simulation', :sid, 'local', 'current', :corr, SYSDATE)"
                    ),
                    {"cid": cid, "total": order_total, "status": status, "sid": sid,
                     "corr": build_correlation_id("sim")},
                )
                # Get the new order ID
                result = await session.execute(
                    text("SELECT id FROM orders WHERE source_order_id = :sid"),
                    {"sid": sid},
                )
                order_row = result.first()
                oid = order_row[0] if order_row else None

                if oid:
                    await session.execute(
                        text(
                            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                            "VALUES (:oid, :pid, :qty, :price)"
                        ),
                        {"oid": oid, "pid": pid, "qty": qty, "price": price},
                    )
                    order_ids.append(oid)

            await session.commit()

        push_log("INFO", f"Simulation: generated {count} orders", **{
            "simulation.type": "generate_orders",
            "simulation.count": count,
            "simulation.total_value": total_value,
        })
        return {
            "status": "completed", "type": "generate_orders",
            "orders_created": len(order_ids), "total_value": round(total_value, 2),
            "order_ids": order_ids,
        }


@router.post("/generate-backlog")
async def generate_backlog(request: Request):
    """Generate orders stuck in backlog state."""
    tracer = tracer_fn()
    body = await _safe_json(request)
    count = max(1, min(body.get("count", 5), 20))

    with tracer.start_as_current_span("simulation.generate_backlog") as span:
        span.set_attribute("simulation.count", count)
        order_ids = []

        async with async_session_factory() as session:
            for _ in range(count):
                cid = await _random_customer_id()
                prod = await _random_product()
                if not cid or not prod:
                    continue
                pid, price = prod
                qty = random.randint(1, 3)
                total = round(price * qty, 2)
                sid = f"sim-backlog-{uuid4().hex[:8]}"
                stale_time = datetime.utcnow() - timedelta(hours=random.randint(2, 48))

                await session.execute(
                    text(
                        "INSERT INTO orders (customer_id, total, status, source_system, "
                        "source_order_id, sync_status, backlog_status, correlation_id, "
                        "last_synced_at, created_at) "
                        "VALUES (:cid, :total, 'pending', 'crm-simulation', :sid, "
                        "'pending', 'backlog', :corr, :synced, :created)"
                    ),
                    {"cid": cid, "total": total, "sid": sid,
                     "corr": build_correlation_id("sim-backlog"),
                     "synced": stale_time, "created": stale_time},
                )
                result = await session.execute(
                    text("SELECT id FROM orders WHERE source_order_id = :sid"), {"sid": sid},
                )
                row = result.first()
                if row:
                    order_ids.append(row[0])
                    await session.execute(
                        text("INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                             "VALUES (:oid, :pid, :qty, :price)"),
                        {"oid": row[0], "pid": pid, "qty": qty, "price": price},
                    )

            await session.commit()

        push_log("WARNING", f"Simulation: generated {len(order_ids)} backlog orders")
        return {
            "status": "completed", "type": "generate_backlog",
            "orders_created": len(order_ids), "order_ids": order_ids,
        }


@router.post("/high-value-order")
async def high_value_order(request: Request):
    """Generate a suspiciously high-value order to trigger anomaly detection."""
    tracer = tracer_fn()
    body = await _safe_json(request)

    with tracer.start_as_current_span("simulation.high_value_order") as span:
        cid = body.get("customer_id") or await _random_customer_id()
        if not cid:
            return {"status": "error", "reason": "no customers in database"}
        prod = await _random_product()
        if not prod:
            return {"status": "error", "reason": "no products in database"}
        pid, _ = prod

        total = round(random.uniform(55000, 150000), 2)
        sid = f"sim-hv-{uuid4().hex[:8]}"

        async with async_session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO orders (customer_id, total, status, source_system, "
                    "source_order_id, sync_status, correlation_id, notes, created_at) "
                    "VALUES (:cid, :total, 'processing', 'crm-simulation', :sid, "
                    "'local', :corr, 'HIGH VALUE - Simulation generated', SYSDATE)"
                ),
                {"cid": cid, "total": total, "sid": sid,
                 "corr": build_correlation_id("sim-hv")},
            )
            result = await session.execute(
                text("SELECT id FROM orders WHERE source_order_id = :sid"), {"sid": sid},
            )
            row = result.first()
            oid = row[0] if row else None
            if oid:
                await session.execute(
                    text("INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                         "VALUES (:oid, :pid, 1, :price)"),
                    {"oid": oid, "pid": pid, "price": total},
                )
            await session.commit()

        push_log("WARNING", f"Simulation: high-value order ${total:,.2f}", **{
            "simulation.type": "high_value_order",
            "simulation.total": total,
            "simulation.threshold": cfg.suspicious_order_total_threshold,
            "simulation.alert_triggered": total > cfg.suspicious_order_total_threshold,
        })
        return {
            "status": "completed", "type": "high_value_order",
            "order_id": oid, "total": total,
            "alert_triggered": total > cfg.suspicious_order_total_threshold,
        }


@router.post("/add-customer")
async def add_random_customer(request: Request):
    """Add a random demo customer."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.add_customer"):
        company, industry, revenue = random.choice(_FAKE_COMPANIES)
        contact = random.choice(_FAKE_CONTACTS)
        email = f"sim.{uuid4().hex[:6]}@{company.lower().replace(' ', '')}.demo"

        async with async_session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO customers (name, email, company, industry, revenue, created_at) "
                    "VALUES (:name, :email, :company, :industry, :revenue, SYSDATE)"
                ),
                {"name": contact, "email": email, "company": company,
                 "industry": industry, "revenue": revenue},
            )
            await session.commit()
            result = await session.execute(
                text("SELECT id FROM customers WHERE email = :email"), {"email": email},
            )
            row = result.first()

        push_log("INFO", f"Simulation: added customer {contact} at {company}")
        return {
            "status": "completed", "type": "add_customer",
            "customer_id": row[0] if row else None,
            "name": contact, "email": email, "company": company,
        }


class CreateCustomerRequest(BaseModel):
    company_name: str
    contact_name: str
    email: str
    industry: str = ""
    revenue: float = 0.0


@router.post("/create-customer")
async def create_customer(req: CreateCustomerRequest, request: Request):
    """Create a specific customer/company."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.create_customer"):
        async with async_session_factory() as session:
            existing = await session.execute(
                text("SELECT id FROM customers WHERE LOWER(email) = :email"),
                {"email": req.email.lower()},
            )
            if existing.first():
                return {"status": "error", "reason": "customer with this email already exists"}

            await session.execute(
                text(
                    "INSERT INTO customers (name, email, company, industry, revenue, created_at) "
                    "VALUES (:name, :email, :company, :industry, :revenue, SYSDATE)"
                ),
                {"name": req.contact_name, "email": req.email,
                 "company": req.company_name, "industry": req.industry,
                 "revenue": req.revenue},
            )
            await session.commit()
            result = await session.execute(
                text("SELECT id FROM customers WHERE email = :email"), {"email": req.email},
            )
            row = result.first()

        push_log("INFO", f"Simulation: created customer {req.contact_name}")
        return {
            "status": "completed", "type": "create_customer",
            "customer_id": row[0] if row else None,
            "name": req.contact_name, "email": req.email,
        }


@router.post("/sync-customers")
async def sync_customers(request: Request):
    """Trigger on-demand order sync from the drone shop."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.sync_customers") as span:
        cid = build_correlation_id("manual-sync")
        span.set_attribute("correlation.id", cid)
        try:
            result = await sync_external_orders(correlation_id=cid)
            push_log("INFO", "Simulation: manual sync completed", **{
                "simulation.type": "sync_customers",
                "simulation.synced": result.get("created", 0) + result.get("updated", 0),
            })
            return {"status": "completed", "type": "sync_customers", **result}
        except Exception as e:
            logger.warning("Sync failed: %s", type(e).__name__)
            return {"status": "error", "reason": str(e)[:200]}


# ── Drone Shop Proxy ──────────────────────────────────────────────

_ALLOWED_PROXY_ACTIONS = {"configure", "reset", "db-latency", "error-burst", "status"}


@router.api_route("/drone-shop/{action}", methods=["GET", "POST"])
async def drone_shop_proxy(action: str, request: Request):
    """Proxy simulation commands to the drone shop via internal service key."""
    tracer = tracer_fn()

    if action not in _ALLOWED_PROXY_ACTIONS:
        return {"status": "error", "reason": f"action '{action}' not allowed"}

    base_url = external_orders_base_url()
    if not base_url:
        return {"status": "skipped", "reason": "drone shop URL not configured"}

    target = f"{base_url}/api/simulate/{action}"
    method = request.method.upper()

    with tracer.start_as_current_span("simulation.drone_shop_proxy") as span:
        span.set_attribute("simulation.proxy_target", target)
        span.set_attribute("simulation.proxy_action", action)

        headers = outbound_headers(build_correlation_id("drone-proxy"))
        if cfg.drone_shop_internal_key:
            headers["X-Internal-Service-Key"] = cfg.drone_shop_internal_key

        try:
            body = await request.body()
            async with httpx.AsyncClient(timeout=10.0) as client:
                if method == "POST":
                    resp = await client.post(target, content=body,
                                             headers={**headers, "Content-Type": "application/json"})
                else:
                    resp = await client.get(target, headers=headers)

            push_log("INFO", f"Drone shop proxy: {action} -> {resp.status_code}")
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:500]}
            return {"status": "proxied", "upstream_status": resp.status_code, "data": data}

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            push_log("WARNING", f"Drone shop unreachable: {type(e).__name__}")
            return {"status": "unreachable", "reason": f"{type(e).__name__}: drone shop not responding"}
        except Exception as e:
            return {"status": "error", "reason": str(e)[:200]}


# ── Accessor for middleware ───────────────────────────────────────

def get_sim_state() -> dict:
    """Accessor for middleware to check current sim state."""
    return _sim_state
