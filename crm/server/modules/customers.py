"""Customer management module — OWASP A03: Injection + A01: Broken Access Control.

Vulnerabilities:
- SQL Injection in search endpoint
- IDOR (Insecure Direct Object Reference) in customer detail
- XSS (Stored) in customer notes
- No authorization checks on customer data
"""

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.database import get_db

router = APIRouter(prefix="/api/customers", tags=["Customers"])
tracer_fn = get_tracer


@router.get("")
async def list_customers(
    request: Request,
    search: str = Query(default="", description="Search customers"),
    sort_by: str = Query(default="name", description="Sort field"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List customers — VULN: SQL injection in search and sort_by parameters."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("customers.list") as span:
        span.set_attribute("customers.search_query", search)
        span.set_attribute("customers.sort_by", sort_by)

        async with get_db() as db:
            # VULN: SQL Injection — search parameter directly interpolated
            with tracer.start_as_current_span("db.query.customers_search") as db_span:
                if search:
                    # Detect SQLi patterns for security logging
                    sqli_patterns = ["'", '"', "--", ";", "UNION", "SELECT", "DROP", "OR 1=1"]
                    if any(p.lower() in search.lower() for p in sqli_patterns):
                        with security_span("sqli", severity="critical",
                                         payload=search, source_ip=client_ip):
                            log_security_event("sqli", "critical",
                                f"SQL injection attempt in customer search",
                                source_ip=client_ip, payload=search)

                    # VULN: Direct string interpolation in SQL
                    query = f"SELECT * FROM customers WHERE name LIKE '%{search}%' OR email LIKE '%{search}%' ORDER BY {sort_by}"
                else:
                    query = f"SELECT * FROM customers ORDER BY {sort_by}"

                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
                db_span.set_attribute("db.statement", query[:200])
                result = await db.execute(text(query))
                rows = result.fetchall()

        customers = [dict(r._mapping) for r in rows]
        push_log("INFO", f"Listed {len(customers)} customers", **{
            "customers.count": len(customers),
            "customers.search": search,
        })
        return {"customers": customers, "total": len(customers), "limit": limit, "offset": offset}


@router.get("/{customer_id}")
async def get_customer(customer_id: int, request: Request):
    """Get customer by ID — VULN: IDOR (no authorization check)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("customers.get") as span:
        span.set_attribute("customers.id", customer_id)

        # No auth check — any user can view any customer (IDOR)
        with security_span("idor", severity="medium",
                         payload=f"customer_id={customer_id}",
                         source_ip=client_ip):
            pass

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.customer_detail"):
                result = await db.execute(
                    text("SELECT * FROM customers WHERE id = :id"), {"id": customer_id}
                )
                customer = result.fetchone()

        if not customer:
            return {"error": "Customer not found"}

        return {"customer": dict(customer._mapping)}


@router.post("")
async def create_customer(request: Request):
    """Create customer — VULN: Stored XSS in notes field."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("customers.create") as span:
        name = body.get("name", "")
        email = body.get("email", "")
        notes = body.get("notes", "")  # VULN: no sanitization

        # Detect XSS in notes
        if "<script" in notes.lower() or "javascript:" in notes.lower() or "onerror" in notes.lower():
            with security_span("xss_stored", severity="high",
                             payload=notes, source_ip=client_ip):
                log_security_event("xss_stored", "high",
                    "Stored XSS attempt in customer notes",
                    source_ip=client_ip, payload=notes)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.customer_insert"):
                # VULN: Notes stored without sanitization
                await db.execute(
                    text("INSERT INTO customers (name, email, phone, company, industry, revenue, notes) "
                         "VALUES (:n, :e, :ph, :co, :ind, :rev, :notes)"),
                    {
                        "n": name, "e": email,
                        "ph": body.get("phone", ""),
                        "co": body.get("company", ""),
                        "ind": body.get("industry", ""),
                        "rev": body.get("revenue", 0),
                        "notes": notes,  # stored as-is
                    }
                )

        return {"status": "created", "name": name}


@router.put("/{customer_id}")
async def update_customer(customer_id: int, request: Request):
    """Update customer — VULN: SQL injection in update query."""
    tracer = tracer_fn()
    body = await request.json()

    with tracer.start_as_current_span("customers.update") as span:
        span.set_attribute("customers.id", customer_id)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.customer_update"):
                # Build dynamic SET clause — VULN: string interpolation
                set_parts = []
                for field in ("name", "email", "phone", "company", "industry", "revenue", "notes"):
                    if field in body:
                        set_parts.append(f"{field} = '{body[field]}'")  # VULN: SQLi
                if set_parts:
                    query = f"UPDATE customers SET {', '.join(set_parts)} WHERE id = {customer_id}"
                    await db.execute(text(query))

        return {"status": "updated", "customer_id": customer_id}
