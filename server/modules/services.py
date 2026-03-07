"""Services module — API endpoints for Drone Services and Support Tickets."""

from fastapi import APIRouter
from sqlalchemy import text

from server.database import get_db
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/catalog")
async def get_services_catalog():
    """Fetch the catalog of available services."""
    tracer = get_tracer()
    with tracer.start_as_current_span("services.catalog") as span:
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, name, sku, description, price, category, image_url "
                    "FROM services WHERE is_active = 1 ORDER BY price DESC"
                )
            )
            services = [dict(row) for row in result.mappings().all()]
            span.set_attribute("services.count", len(services))
            return {"services": services}


@router.get("/tickets")
async def get_tickets(customer_id: int):
    """Fetch all support and maintenance tickets for a specific customer."""
    tracer = get_tracer()
    with tracer.start_as_current_span("services.tickets.list") as span:
        span.set_attribute("customer.id", customer_id)
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, title, status, priority, product_id, service_id, created_at, updated_at "
                    "FROM tickets WHERE customer_id = :customer_id ORDER BY updated_at DESC"
                ),
                {"customer_id": customer_id},
            )
            tickets = [dict(row) for row in result.mappings().all()]

            # Fetch messages for all retrieved tickets
            ticket_ids = [t["id"] for t in tickets]
            messages_by_ticket = {tid: [] for tid in ticket_ids}
            if ticket_ids:
                msg_result = await db.execute(
                    text(
                        "SELECT id, ticket_id, sender_type, content, created_at "
                        "FROM ticket_messages WHERE ticket_id IN :ticket_ids ORDER BY created_at ASC"
                    ),
                    {"ticket_ids": tuple(ticket_ids)},
                )
                for msg in msg_result.mappings().all():
                    messages_by_ticket[msg["ticket_id"]].append(dict(msg))

            for ticket in tickets:
                ticket["messages"] = messages_by_ticket[ticket["id"]]

            span.set_attribute("tickets.count", len(tickets))
            return {"tickets": tickets}


@router.post("/tickets")
async def create_ticket(payload: dict):
    """Create a new support or service ticket."""
    tracer = get_tracer()
    customer_id = payload.get("customer_id")
    title = payload.get("title", "").strip()
    content = payload.get("content", "").strip()
    
    if not customer_id or not title or not content:
        return {"error": "customer_id, title, and content are required"}

    with tracer.start_as_current_span("services.tickets.create") as span:
        span.set_attribute("customer.id", customer_id)
        async with get_db() as db:
            # 1. Insert Title
            result = await db.execute(
                text(
                    "INSERT INTO tickets (customer_id, title, status, priority, product_id, service_id) "
                    "VALUES (:customer_id, :title, 'open', :priority, :product_id, :service_id) "
                    "RETURNING id"
                ),
                {
                    "customer_id": customer_id,
                    "title": title,
                    "priority": payload.get("priority", "medium"),
                    "product_id": payload.get("product_id"),
                    "service_id": payload.get("service_id"),
                },
            )
            ticket_id = result.scalar()

            # 2. Insert Initial Message
            await db.execute(
                text(
                    "INSERT INTO ticket_messages (ticket_id, sender_type, content) "
                    "VALUES (:ticket_id, 'customer', :content)"
                ),
                {
                    "ticket_id": ticket_id,
                    "content": content,
                },
            )
            
            push_log(
                "INFO",
                f"New support ticket created: {ticket_id}",
                **{"ticket.id": ticket_id, "customer.id": customer_id}
            )

        return {"status": "success", "ticket_id": ticket_id}
