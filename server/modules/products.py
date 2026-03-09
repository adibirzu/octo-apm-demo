"""Product catalog module — OWASP A03: Injection + A05: Security Misconfiguration.

Vulnerabilities:
- SQL injection in search/filter
- Verbose error messages exposing internals
- No input validation on price/stock
- Mass assignment on product fields
"""

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event
from server.database import get_db
from server.db_compat import BOOL_TRUE

router = APIRouter(prefix="/api/products", tags=["Products"])
tracer_fn = get_tracer


@router.get("")
async def list_products(
    request: Request,
    category: str = Query(default="", description="Filter by category"),
    min_price: str = Query(default="", description="Minimum price"),
    max_price: str = Query(default="", description="Maximum price"),
    limit: int = Query(default=100, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip"),
):
    """List products — VULN: SQLi in category filter, verbose errors."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("products.list") as span:
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.products_list"):
                # VULN: SQL injection via category parameter
                query = f"SELECT * FROM products WHERE is_active = {BOOL_TRUE}"
                if category:
                    query += f" AND category = '{category}'"  # VULN: SQLi
                if min_price:
                    query += f" AND price >= {min_price}"  # VULN: SQLi
                if max_price:
                    query += f" AND price <= {max_price}"  # VULN: SQLi
                query += " ORDER BY name"
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"

                try:
                    result = await db.execute(text(query))
                    rows = result.fetchall()
                except Exception as e:
                    # VULN: Verbose error message exposes SQL details
                    return {"error": f"Database error: {str(e)}", "query": query}

        products = [dict(r._mapping) for r in rows]
        return {"products": products, "total": len(products), "limit": limit, "offset": offset}


@router.get("/{product_id}")
async def get_product(product_id: int, request: Request):
    tracer = tracer_fn()
    with tracer.start_as_current_span("products.get") as span:
        span.set_attribute("products.id", product_id)
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.product_detail"):
                result = await db.execute(
                    text("SELECT * FROM products WHERE id = :id"), {"id": product_id}
                )
                product = result.fetchone()
        if not product:
            return {"error": "Product not found"}
        return {"product": dict(product._mapping)}


@router.post("")
async def create_product(request: Request):
    """Create product — VULN: no price validation, mass assignment."""
    tracer = tracer_fn()
    body = await request.json()

    with tracer.start_as_current_span("products.create"):
        # VULN: No validation — negative prices, huge stock values accepted
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.product_insert"):
                await db.execute(
                    text("INSERT INTO products (name, sku, description, price, stock, category) "
                         "VALUES (:n, :s, :d, :p, :st, :c)"),
                    {
                        "n": body.get("name", ""),
                        "s": body.get("sku", ""),
                        "d": body.get("description", ""),
                        "p": body.get("price", 0),  # VULN: no min/max validation
                        "st": body.get("stock", 0),
                        "c": body.get("category", ""),
                    }
                )
        return {"status": "created"}
