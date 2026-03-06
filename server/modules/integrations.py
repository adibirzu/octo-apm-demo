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

import os
import logging

import httpx
from fastapi import APIRouter, Request
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations", tags=["integrations"])

CRM_BASE_URL = os.getenv("ENTERPRISE_CRM_URL", "")


def _crm_url() -> str:
    return CRM_BASE_URL or os.getenv("C27_CRM_URL", "")


# ── Cross-service: MuShop → CRM ──────────────────────────────────

@router.get("/crm/customer-enrichment")
async def crm_customer_enrichment(customer_id: int, request: Request):
    """Enrich a MuShop customer with CRM profile data.

    Creates a distributed trace: MuShop → HTTP → CRM /api/customers/{id}
    The traceparent header is auto-injected by HTTPXClientInstrumentor.
    """
    tracer = get_tracer()
    crm = _crm_url()
    if not crm:
        return {"error": "CRM not configured", "customer_id": customer_id}

    with tracer.start_as_current_span("integration.crm.customer_enrichment") as span:
        span.set_attribute("integration.target_service", "enterprise-crm-portal")
        span.set_attribute("integration.customer_id", customer_id)
        span.set_attribute("integration.crm_url", crm)

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
    """Sync a MuShop order to CRM as an invoice/ticket.

    Creates a distributed trace spanning both services.
    """
    tracer = get_tracer()
    crm = _crm_url()
    if not crm:
        return {"error": "CRM not configured"}

    with tracer.start_as_current_span("integration.crm.sync_order") as span:
        order_id = payload.get("order_id")
        customer_email = payload.get("customer_email", "")
        total = payload.get("total", 0)

        span.set_attribute("integration.target_service", "enterprise-crm-portal")
        span.set_attribute("integration.order_id", order_id)
        span.set_attribute("integration.order_total", total)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Create an invoice in CRM
                resp = await client.post(f"{crm}/api/invoices", json={
                    "customer_email": customer_email,
                    "amount": total,
                    "description": f"MuShop Order #{order_id}",
                    "source": "mushop-cloudnative",
                })
                span.set_attribute("integration.crm.status_code", resp.status_code)

                push_log("INFO", "Order synced to CRM", **{
                    "integration.type": "sync_order",
                    "integration.order_id": order_id,
                    "integration.crm_status": resp.status_code,
                })

                return {
                    "synced": resp.status_code in (200, 201),
                    "order_id": order_id,
                    "crm_response": resp.json() if resp.status_code in (200, 201) else None,
                }

        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"synced": False, "order_id": order_id, "reason": str(e)}


@router.get("/crm/ticket-products")
async def crm_ticket_products(ticket_id: int, request: Request):
    """Fetch CRM ticket details and recommend related MuShop products.

    Distributed trace: MuShop → CRM (get ticket) → MuShop (local DB query)
    """
    tracer = get_tracer()
    crm = _crm_url()
    if not crm:
        return {"error": "CRM not configured", "ticket_id": ticket_id}

    with tracer.start_as_current_span("integration.crm.ticket_products") as span:
        span.set_attribute("integration.target_service", "enterprise-crm-portal")
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
                                "WHERE is_active = true ORDER BY RANDOM() LIMIT 3")
                    )
                    products = [dict(r) for r in result.mappings().all()]
                    db_span.set_attribute("db.row_count", len(products))

            return {
                "ticket_id": ticket_id,
                "ticket": ticket,
                "recommended_products": products,
                "source": "mushop-cloudnative",
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
        span.set_attribute("integration.crm_url", crm)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{crm}/health")
                span.set_attribute("integration.crm.status_code", resp.status_code)

            return {
                "crm_configured": True,
                "crm_url": crm,
                "status": "healthy" if resp.status_code == 200 else "unhealthy",
                "crm_response": resp.json() if resp.status_code == 200 else None,
            }
        except Exception as e:
            span.set_attribute("integration.error", str(e))
            return {"crm_configured": True, "crm_url": crm,
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
                "url": crm or None,
                "endpoints": [
                    "/api/integrations/crm/customer-enrichment",
                    "/api/integrations/crm/sync-order",
                    "/api/integrations/crm/ticket-products",
                    "/api/integrations/crm/health",
                ],
                "trace_propagation": "W3C traceparent (auto-injected by HTTPXClientInstrumentor)",
            },
        ],
    }
