"""Integrations module — cross-service communication with Enterprise CRM Portal.

Calls CRM endpoints via httpx with W3C traceparent propagation, creating
distributed traces visible in OCI APM. The HTTPXClientInstrumentor auto-injects
trace context headers on every outbound HTTP call.

Endpoints:
  GET  /api/integrations/crm/customer-enrichment?customer_id=...
  GET  /api/integrations/crm/ticket-products?ticket_id=...
  POST /api/integrations/crm/sync-order
  GET  /api/integrations/crm/health
  GET  /api/integrations/status
"""

import logging
import os
import time

import httpx
from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from server.config import cfg
from server.database import get_db
from server.middleware.circuit_breaker import crm_breaker
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations", tags=["integrations"])

CRM_BASE_URL = os.getenv("ENTERPRISE_CRM_URL", "")
CRM_SYNC_STATE = {
    "last_sync_ts": 0.0,
    "last_count": 0,
    "last_error": "",
}


def _crm_url() -> str:
    return CRM_BASE_URL or os.getenv("C27_CRM_URL", "")


def _sync_state_payload() -> dict:
    return {
        "last_sync_epoch": CRM_SYNC_STATE["last_sync_ts"] or None,
        "last_count": CRM_SYNC_STATE["last_count"],
        "last_error": CRM_SYNC_STATE["last_error"] or None,
    }


def _normalize_customer(raw: dict) -> dict | None:
    email = (
        raw.get("email")
        or raw.get("email_address")
        or raw.get("contact_email")
        or ""
    ).strip()
    if not email:
        return None

    name = (
        raw.get("name")
        or raw.get("full_name")
        or raw.get("customer_name")
        or raw.get("company")
        or email.split("@")[0]
    ).strip()
    company = (raw.get("company") or raw.get("company_name") or "").strip()
    phone = (raw.get("phone") or raw.get("phone_number") or "").strip()
    industry = (raw.get("industry") or raw.get("segment") or "Enterprise").strip() or "Enterprise"
    notes = f"crm_id={raw.get('id') or raw.get('customer_id') or 'n/a'}; source=enterprise-crm-portal"
    revenue = raw.get("revenue") or raw.get("annual_revenue") or 0

    try:
        revenue_value = float(revenue or 0)
    except (TypeError, ValueError):
        revenue_value = 0.0

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "industry": industry,
        "revenue": revenue_value,
        "notes": notes,
    }


def _extract_customer_list(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("customers", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


async def _fetch_crm_customers(crm: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        attempts = [
            (f"{crm}/api/customers", {"limit": limit}),
            (f"{crm}/api/customers", {}),
            (f"{crm}/customers", {"limit": limit}),
        ]
        for url, params in attempts:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                continue
            customers = _extract_customer_list(resp.json())
            if customers:
                return customers[:limit]
    return []


async def _find_crm_customer(client: httpx.AsyncClient, crm: str, email: str) -> dict | None:
    target = (email or "").strip().lower()
    if not target:
        return None

    attempts = [
        (f"{crm}/api/customers", {"search": email, "limit": 25}),
        (f"{crm}/api/customers", {"limit": 200}),
        (f"{crm}/customers", {"limit": 200}),
    ]
    for url, params in attempts:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            continue
        for item in _extract_customer_list(resp.json()):
            candidate = (
                item.get("email")
                or item.get("email_address")
                or item.get("contact_email")
                or ""
            ).strip().lower()
            if candidate == target:
                return item
    return None


async def _ensure_crm_customer(client: httpx.AsyncClient, crm: str, customer_email: str) -> dict | None:
    customer = await _find_crm_customer(client, crm, customer_email)
    if customer:
        return customer

    email = (customer_email or "").strip()
    if not email:
        return None

    local_part = email.split("@")[0] or "octo-buyer"
    create_resp = await client.post(
        f"{crm}/api/customers",
        json={
            "name": local_part.replace(".", " ").replace("-", " ").title(),
            "email": email,
            "phone": "",
            "company": "OCTO Drone Shop",
            "industry": "Drone Operations",
            "revenue": 0,
            "notes": "source=octo-drone-shop",
        },
    )
    if create_resp.status_code not in (200, 201):
        return None

    return await _find_crm_customer(client, crm, customer_email)


async def _upsert_customers(customers: list[dict]) -> dict:
    synced = 0
    updated = 0
    inserted = 0

    async with get_db() as db:
        for raw in customers:
            customer = _normalize_customer(raw)
            if not customer:
                continue

            existing = await db.execute(
                text("SELECT id FROM customers WHERE lower(email) = lower(:email) FETCH FIRST 1 ROWS ONLY"),
                {"email": customer["email"]},
            )
            row = existing.mappings().first()
            if row:
                await db.execute(
                    text(
                        "UPDATE customers SET "
                        "name = :name, phone = :phone, company = :company, industry = :industry, "
                        "revenue = :revenue, notes = :notes, updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = :id"
                    ),
                    {**customer, "id": row["id"]},
                )
                updated += 1
            else:
                await db.execute(
                    text(
                        "INSERT INTO customers (name, email, phone, company, industry, revenue, notes) "
                        "VALUES (:name, :email, :phone, :company, :industry, :revenue, :notes)"
                    ),
                    customer,
                )
                inserted += 1
            synced += 1

    return {
        "synced": synced,
        "updated": updated,
        "inserted": inserted,
    }


async def sync_customers_from_crm(*, force: bool = False, limit: int = 200, source: str = "auto") -> dict:
    crm = _crm_url()
    if not crm:
        return {"configured": False, "synced": False, "reason": "CRM not configured", **_sync_state_payload()}

    now = time.time()
    age = now - float(CRM_SYNC_STATE["last_sync_ts"] or 0)
    if not force and CRM_SYNC_STATE["last_sync_ts"] and age < 300:
        return {
            "configured": True,
            "synced": True,
            "skipped": True,
            "reason": f"cached ({int(age)}s ago)",
            **_sync_state_payload(),
        }

    # Circuit breaker — reject fast if CRM is known-down
    if not crm_breaker.allow_request():
        return {
            "configured": True,
            "synced": False,
            "crm_host": cfg.crm_hostname or "configured",
            "reason": f"circuit breaker OPEN ({crm_breaker.name})",
            "circuit_breaker": crm_breaker.status(),
            **_sync_state_payload(),
        }

    tracer = get_tracer()
    with tracer.start_as_current_span("integration.crm.sync_customers") as span:
        span.set_attribute("integration.target_service", "enterprise-crm-portal")
        span.set_attribute("peer.service", "enterprise-crm-portal")
        span.set_attribute("component", "http")
        span.set_attribute("integration.sync_source", source)
        span.set_attribute("integration.sync_limit", limit)
        span.set_attribute("integration.circuit_breaker.state", crm_breaker.state.value)
        try:
            customers = await _fetch_crm_customers(crm, max(1, min(limit, 500)))
            upsert = await _upsert_customers(customers)
            crm_breaker.record_success()
            CRM_SYNC_STATE["last_sync_ts"] = now
            CRM_SYNC_STATE["last_count"] = upsert["synced"]
            CRM_SYNC_STATE["last_error"] = ""
            span.set_attribute("integration.crm.customers_synced", upsert["synced"])
            push_log(
                "INFO",
                "CRM customer sync completed",
                **{
                    "integration.type": "sync_customers",
                    "integration.customers_synced": upsert["synced"],
                    "integration.customers_inserted": upsert["inserted"],
                    "integration.customers_updated": upsert["updated"],
                },
            )
            return {
                "configured": True,
                "synced": True,
                "crm_host": cfg.crm_hostname or "configured",
                "customers_seen": len(customers),
                **upsert,
                **_sync_state_payload(),
            }
        except Exception as exc:
            crm_breaker.record_failure()
            CRM_SYNC_STATE["last_error"] = str(exc)
            span.set_attribute("integration.error", str(exc))
            span.set_attribute("integration.circuit_breaker.state", crm_breaker.state.value)
            return {
                "configured": True,
                "synced": False,
                "crm_host": cfg.crm_hostname or "configured",
                "reason": str(exc),
                "circuit_breaker": crm_breaker.status(),
                **_sync_state_payload(),
            }


async def list_synced_customers(limit: int = 100) -> list[dict]:
    async with get_db() as db:
        result = await db.execute(
            text(
                "SELECT id, name, email, phone, company, industry, revenue, updated_at "
                "FROM customers ORDER BY updated_at DESC"
            ),
        )
        return [dict(row) for row in result.mappings().all()][: max(1, min(limit, 500))]


async def sync_order_to_crm(*, order_id: int, customer_email: str, total: float, source: str = "shop") -> dict:
    tracer = get_tracer()
    crm = _crm_url()
    if not crm:
        return {"synced": False, "reason": "CRM not configured"}

    # Circuit breaker — reject fast if CRM is known-down
    if not crm_breaker.allow_request():
        return {
            "synced": False,
            "order_id": order_id,
            "reason": f"circuit breaker OPEN ({crm_breaker.name})",
            "circuit_breaker": crm_breaker.status(),
        }

    with tracer.start_as_current_span("integration.crm.sync_order") as span:
        span.set_attribute("integration.target_service", "enterprise-crm-portal")
        span.set_attribute("peer.service", "enterprise-crm-portal")
        span.set_attribute("component", "http")
        span.set_attribute("integration.order_id", order_id)
        span.set_attribute("integration.order_total", total)
        span.set_attribute("integration.order_source", source)
        span.set_attribute("integration.circuit_breaker.state", crm_breaker.state.value)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                customer = await _ensure_crm_customer(client, crm, customer_email)
                if not customer:
                    return {
                        "synced": False,
                        "order_id": order_id,
                        "reason": "CRM customer lookup/create failed",
                    }

                customer_id = int(customer.get("id") or customer.get("customer_id") or 0)
                if customer_id <= 0:
                    return {
                        "synced": False,
                        "order_id": order_id,
                        "reason": "CRM customer ID missing",
                    }

                resp = await client.post(
                    f"{crm}/api/orders",
                    json={
                        "customer_id": customer_id,
                        "items": [{"quantity": 1, "unit_price": float(total or 0)}],
                        "shipping_address": "Imported from OCTO Drone Shop",
                        "notes": f"OCTO Drone Shop order #{order_id}; source={source}",
                    },
                )
            crm_breaker.record_success()
            span.set_attribute("integration.crm.status_code", resp.status_code)
            push_log(
                "INFO",
                "Order synced to CRM",
                **{
                    "integration.type": "sync_order",
                    "integration.order_id": order_id,
                    "integration.crm_status": resp.status_code,
                },
            )
            return {
                "synced": resp.status_code in (200, 201),
                "order_id": order_id,
                "status_code": resp.status_code,
                "crm_response": resp.json() if resp.status_code in (200, 201) else None,
            }
        except Exception as exc:
            crm_breaker.record_failure()
            span.set_attribute("integration.error", str(exc))
            span.set_attribute("integration.circuit_breaker.state", crm_breaker.state.value)
            return {
                "synced": False,
                "order_id": order_id,
                "reason": str(exc),
                "circuit_breaker": crm_breaker.status(),
            }


# ── Cross-service: OCTO-CRM → CRM ──────────────────────────────────

@router.get("/crm/customer-enrichment")
async def crm_customer_enrichment(customer_id: int, request: Request):
    """Enrich a OCTO-CRM customer with CRM profile data.

    Creates a distributed trace: OCTO-CRM → HTTP → CRM /api/customers/{id}
    The traceparent header is auto-injected by HTTPXClientInstrumentor.
    """
    tracer = get_tracer()
    crm = _crm_url()
    if not crm:
        return {"error": "CRM not configured", "customer_id": customer_id}

    with tracer.start_as_current_span("integration.crm.customer_enrichment") as span:
        span.set_attribute("integration.target_service", "enterprise-crm-portal")
        span.set_attribute("peer.service", "enterprise-crm-portal")
        span.set_attribute("component", "http")
        span.set_attribute("integration.customer_id", customer_id)
        span.set_attribute("integration.crm_host", cfg.crm_hostname or "configured")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Call CRM customer endpoint — traceparent auto-injected
                resp = await client.get(f"{crm}/api/customers/{customer_id}")
                crm_data = resp.json() if resp.status_code == 200 else None

                span.set_attribute("integration.crm.status_code", resp.status_code)

            if crm_data:
                push_log("INFO", "CRM customer enrichment succeeded", **{
                    "integration.type": "customer_enrichment",
                    "integration.customer_id": customer_id,
                    "integration.crm_status": resp.status_code,
                })
                return {
                    "customer_id": customer_id,
                    "crm_profile": crm_data,
                    "source": "enterprise-crm-portal",
                    "enriched": True,
                }

            return {"customer_id": customer_id, "enriched": False,
                    "reason": f"CRM returned {resp.status_code}"}

        except httpx.ConnectError:
            span.set_attribute("integration.error", "connection_refused")
            return {"customer_id": customer_id, "enriched": False,
                    "reason": "CRM unreachable"}
        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"customer_id": customer_id, "enriched": False,
                    "reason": str(e)}


@router.post("/crm/sync-order")
async def crm_sync_order(payload: dict, request: Request):
    """Sync a OCTO-CRM order to CRM as an invoice/ticket.

    Creates a distributed trace spanning both services.
    """
    return await sync_order_to_crm(
        order_id=int(payload.get("order_id", 0) or 0),
        customer_email=payload.get("customer_email", ""),
        total=float(payload.get("total", 0) or 0),
        source=payload.get("source", "api"),
    )


@router.post("/crm/sync-customers")
async def crm_sync_customers(payload: dict | None = None):
    """Force a customer sync from enterprise-crm-portal into the local customer table."""
    payload = payload or {}
    return await sync_customers_from_crm(
        force=bool(payload.get("force", True)),
        limit=int(payload.get("limit", 200) or 200),
        source="manual_endpoint",
    )


@router.get("/crm/customers")
async def crm_customers(
    refresh: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
):
    """List locally persisted customers with optional CRM refresh."""
    sync = await sync_customers_from_crm(force=refresh, limit=limit, source="customers_endpoint")
    customers = await list_synced_customers(limit=limit)
    return {
        "customers": customers,
        "count": len(customers),
        "sync": sync,
    }


@router.get("/crm/ticket-products")
async def crm_ticket_products(ticket_id: int, request: Request):
    """Fetch CRM ticket details and recommend related OCTO-CRM products.

    Distributed trace: OCTO-CRM → CRM (get ticket) → OCTO-CRM (local DB query)
    """
    tracer = get_tracer()
    crm = _crm_url()
    if not crm:
        return {"error": "CRM not configured", "ticket_id": ticket_id}

    with tracer.start_as_current_span("integration.crm.ticket_products") as span:
        span.set_attribute("integration.target_service", "enterprise-crm-portal")
        span.set_attribute("peer.service", "enterprise-crm-portal")
        span.set_attribute("component", "http")
        span.set_attribute("integration.ticket_id", ticket_id)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{crm}/api/tickets/{ticket_id}")
                span.set_attribute("integration.crm.status_code", resp.status_code)

            if resp.status_code != 200:
                return {"ticket_id": ticket_id, "products": [],
                        "reason": f"CRM returned {resp.status_code}"}

            ticket = resp.json()

            # Local product recommendation based on ticket category
            from sqlalchemy import text as sa_text
            from server.database import get_db

            with tracer.start_as_current_span("db.query.recommended_products") as db_span:
                async with get_db() as db:
                    result = await db.execute(
                        sa_text("SELECT id, name, price, category FROM products "
                                "WHERE is_active = 1 FETCH FIRST 3 ROWS ONLY")
                    )
                    products = [dict(r) for r in result.mappings().all()]
                    db_span.set_attribute("db.row_count", len(products))

            return {
                "ticket_id": ticket_id,
                "ticket": ticket,
                "recommended_products": products,
                "source": "octo-crm-apm",
            }

        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"ticket_id": ticket_id, "products": [], "reason": str(e)}


@router.get("/crm/health")
async def crm_health():
    """Check CRM service health — creates a distributed trace for the health check."""
    tracer = get_tracer()
    crm = _crm_url()
    if not crm:
        return {"crm_configured": False, "status": "not_configured"}

    with tracer.start_as_current_span("integration.crm.health_check") as span:
        span.set_attribute("integration.target_service", "enterprise-crm-portal")
        span.set_attribute("peer.service", "enterprise-crm-portal")
        span.set_attribute("component", "http")
        span.set_attribute("integration.crm_host", cfg.crm_hostname or "configured")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{crm}/health")
                span.set_attribute("integration.crm.status_code", resp.status_code)

            return {
                "crm_configured": True,
                "crm_host": cfg.crm_hostname or "configured",
                "status": "healthy" if resp.status_code == 200 else "unhealthy",
                "crm_response": resp.json() if resp.status_code == 200 else None,
            }
        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"crm_configured": True, "crm_host": cfg.crm_hostname or "configured",
                    "status": "unreachable", "error": str(e)}


# ── Integration status ────────────────────────────────────────────

@router.get("/status")
async def integration_status():
    """Show all configured integrations and their status."""
    crm = _crm_url()
    return {
        "integrations": [
            {
                "name": "enterprise-crm-portal",
                "type": "cross-service",
                "configured": bool(crm),
                "host": cfg.crm_hostname or None,
                "circuit_breaker": crm_breaker.status(),
                "endpoints": [
                    "/api/integrations/crm/customer-enrichment",
                    "/api/integrations/crm/sync-order",
                    "/api/integrations/crm/sync-customers",
                    "/api/integrations/crm/customers",
                    "/api/integrations/crm/ticket-products",
                    "/api/integrations/crm/health",
                ],
                "trace_propagation": "W3C traceparent (auto-injected by HTTPXClientInstrumentor)",
            },
        ],
    }
