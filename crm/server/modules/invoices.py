"""Invoice management module — OWASP A02: Cryptographic Failures + A04: Insecure Design.

Vulnerabilities:
- Sensitive data exposure (full invoice details without auth)
- Predictable invoice numbers
- No CSRF protection on payment actions
- PDF generation with SSTI potential
"""

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.observability import business_metrics
from server.database import get_db

router = APIRouter(prefix="/api/invoices", tags=["Invoices"])
tracer_fn = get_tracer


@router.get("")
async def list_invoices(
    request: Request,
    status: str = Query(default="", description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List all invoices — VULN: no auth, exposes financial data."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("invoices.list"):
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.invoices_list"):
                query = "SELECT i.*, o.customer_id, c.name as customer_name FROM invoices i " \
                        "LEFT JOIN orders o ON i.order_id = o.id " \
                        "LEFT JOIN customers c ON o.customer_id = c.id WHERE 1=1"
                params = {}
                if status:
                    query += " AND i.status = :status"
                    params["status"] = status
                query += " ORDER BY i.created_at DESC"
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
                result = await db.execute(text(query), params)
                rows = result.fetchall()

        invoices = [dict(r._mapping) for r in rows]
        return {"invoices": invoices, "total": len(invoices), "limit": limit, "offset": offset}


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: int, request: Request):
    """Get invoice — VULN: IDOR + sensitive data exposure."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("invoices.get") as span:
        span.set_attribute("invoices.id", invoice_id)

        with security_span("sensitive_data", severity="medium",
                         payload=f"invoice_id={invoice_id}",
                         source_ip=client_ip):
            pass

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.invoice_detail"):
                result = await db.execute(
                    text("SELECT i.*, o.customer_id, o.shipping_address, c.name as customer_name, c.email "
                         "FROM invoices i LEFT JOIN orders o ON i.order_id = o.id "
                         "LEFT JOIN customers c ON o.customer_id = c.id WHERE i.id = :id"),
                    {"id": invoice_id}
                )
                invoice = result.fetchone()

        if not invoice:
            return {"error": "Invoice not found"}
        return {"invoice": dict(invoice._mapping)}


@router.post("/{invoice_id}/pay")
async def pay_invoice(invoice_id: int, request: Request):
    """Mark invoice as paid — VULN: no CSRF token, no auth check."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("invoices.pay") as span:
        # VULN: No CSRF protection
        with security_span("csrf", severity="medium",
                         payload=f"pay invoice {invoice_id}",
                         source_ip=client_ip):
            log_security_event("csrf", "medium",
                f"Invoice payment without CSRF protection",
                source_ip=client_ip, payload=f"invoice_id={invoice_id}")

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.invoice_pay"):
                await db.execute(
                    text("UPDATE invoices SET status = 'paid' WHERE id = :id"),
                    {"id": invoice_id}
                )

        business_metrics.record_invoice_paid(invoice_id)
        push_log("INFO", f"Invoice #{invoice_id} marked as paid", **{
            "invoices.id": invoice_id,
            "invoices.action": "payment",
        })
        return {"status": "paid", "invoice_id": invoice_id}


@router.get("/{invoice_id}/pdf")
async def generate_invoice_pdf(invoice_id: int, request: Request):
    """Generate PDF — VULN: SSTI in template parameter."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    template = request.query_params.get("template", "default")

    with tracer.start_as_current_span("invoices.generate_pdf") as span:
        # VULN: Template parameter could allow SSTI
        if "{{" in template or "{%" in template:
            with security_span("ssti", severity="critical",
                             payload=template, source_ip=client_ip):
                log_security_event("ssti", "critical",
                    "SSTI attempt in invoice PDF template",
                    source_ip=client_ip, payload=template)

        from jinja2 import Environment
        env = Environment()  # VULN: no sandboxing
        try:
            rendered = env.from_string(f"Invoice #{invoice_id} - Template: {template}").render()
        except Exception as e:
            rendered = f"Error: {e}"  # VULN: error details leaked

        return {"invoice_id": invoice_id, "template": template, "preview": rendered}
