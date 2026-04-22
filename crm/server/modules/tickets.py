"""Support ticket module — OWASP A03: Injection (XSS) + A09: Logging Failures.

Vulnerabilities:
- Reflected XSS in search results
- Log injection via ticket description
- No rate limiting on ticket creation
- Unvalidated redirects in ticket links
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.observability import business_metrics
from server.database import SupportTicket, get_db

router = APIRouter(prefix="/api/tickets", tags=["Support Tickets"])
tracer_fn = get_tracer


@router.get("")
async def list_tickets(
    request: Request,
    search: str = Query(default="", description="Search tickets"),
    priority: str = Query(default="", description="Filter by priority"),
    status: str = Query(default="", description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List tickets — VULN: reflected XSS in search, SQLi in filters."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("tickets.list") as span:
        # Detect reflected XSS
        if search and ("<script" in search.lower() or "onerror" in search.lower()):
            with security_span("xss_reflected", severity="high",
                             payload=search, source_ip=client_ip):
                log_security_event("xss_reflected", "high",
                    "Reflected XSS attempt in ticket search",
                    source_ip=client_ip, payload=search)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.tickets_list"):
                query = ("SELECT t.*, c.name as customer_name FROM support_tickets t "
                         "LEFT JOIN customers c ON t.customer_id = c.id WHERE 1=1")
                params = {}
                if search:
                    query += f" AND (t.subject LIKE '%{search}%' OR t.description LIKE '%{search}%')"  # VULN: SQLi
                if priority:
                    query += " AND t.priority = :priority"
                    params["priority"] = priority
                if status:
                    query += " AND t.status = :status"
                    params["status"] = status
                query += " ORDER BY t.created_at DESC"
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

        tickets = [dict(r._mapping) for r in rows]
        # VULN: Reflecting search term in response (XSS vector in rendered HTML)
        return {"tickets": tickets, "total": len(tickets), "limit": limit, "offset": offset, "search_term": search}


@router.post("")
async def create_ticket(request: Request):
    """Create ticket — VULN: log injection, no rate limiting."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("tickets.create") as span:
        description = body.get("description", "")

        # VULN: Log injection — description can contain newlines/log format strings
        if "\n" in description or "\r" in description:
            with security_span("log_injection", severity="medium",
                             payload=description[:200], source_ip=client_ip):
                log_security_event("log_injection", "medium",
                    "Log injection attempt in ticket description",
                    source_ip=client_ip, payload=description[:200])

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.ticket_insert"):
                ticket = SupportTicket(
                    customer_id=body.get("customer_id"),
                    subject=body.get("subject", ""),
                    description=description,
                    priority=body.get("priority", "medium"),
                    assigned_to=body.get("assigned_to", ""),
                )
                db.add(ticket)
                await db.flush()
                ticket_id = ticket.id

        business_metrics.record_ticket_created(priority=body.get("priority", "medium"))
        push_log("INFO", f"Ticket #{ticket_id} created: {body.get('subject', '')}",
                 **{"tickets.id": ticket_id, "tickets.priority": body.get("priority", "medium")})
        return {"status": "created", "ticket_id": ticket_id}


@router.get("/redirect")
async def ticket_redirect(request: Request, url: str = Query(description="Redirect URL")):
    """Redirect to ticket-related URL — VULN: open redirect."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("tickets.redirect") as span:
        span.set_attribute("redirect.target_url", url)

        # VULN: Open redirect — no validation of target URL
        if not url.startswith("/"):
            with security_span("open_redirect", severity="medium",
                             payload=url, source_ip=client_ip):
                log_security_event("open_redirect", "medium",
                    "Open redirect attempt via ticket URL",
                    source_ip=client_ip, payload=url)

        return RedirectResponse(url=url)  # VULN: unvalidated redirect
