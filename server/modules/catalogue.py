"""Catalogue module — products, categories, search, reviews.

VULNS: SQLi (search), XSS (reviews), IDOR (product detail)
"""

from fastapi import APIRouter, Request, Query
from sqlalchemy import text
from server.database import get_db
from server.observability.correlation import apply_span_attributes, sql_attributes
from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.storefront import enrich_product

router = APIRouter(prefix="/api", tags=["catalogue"])


@router.get("/products")
async def list_products(request: Request,
                        search: str = "", category: str = "",
                        sort_by: str = "name"):
    """List products — VULN: SQL injection in search and sort_by."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("catalogue.list_products") as span:
        apply_span_attributes(span, {
            "catalogue.search": search,
            "catalogue.category": category,
            "app.page.name": "catalogue",
            "app.module": "catalogue",
            "app.logical_endpoint": "catalogue.list_products",
        })

        async with get_db() as db:
            # VULN: SQL injection in search parameter
            where = "WHERE is_active = 1"
            if search:
                where += f" AND (name LIKE '%{search}%' OR description LIKE '%{search}%')"
                if any(c in search for c in ["'", ";", "--", "UNION"]):
                    security_span("sqli", severity="high", payload=search,
                                  source_ip=source_ip, endpoint="/api/products")
            if category:
                where += f" AND category = '{category}'"

            # VULN: SQL injection in sort_by
            query = f"SELECT id, name, sku, description, price, stock, category, image_url FROM products {where} ORDER BY {sort_by}"
            if sort_by not in ("name", "price", "stock", "category"):
                security_span("sqli", severity="medium", payload=sort_by,
                              source_ip=source_ip, endpoint="/api/products")

            with tracer.start_as_current_span("db.query.products") as db_span:
                apply_span_attributes(db_span, sql_attributes(query, connection_name="", database_target="oracle_atp"))
                result = await db.execute(text(query))
                products = [enrich_product(dict(r)) for r in result.mappings().all()]
                db_span.set_attribute("db.row_count", len(products))

        return {"products": products}


@router.get("/products/{product_id}")
async def get_product(product_id: int, request: Request):
    """Get single product — VULN: IDOR (no ownership check)."""
    tracer = get_tracer()
    with tracer.start_as_current_span("catalogue.get_product") as span:
        apply_span_attributes(span, {
            "catalogue.product_id": product_id,
            "app.page.name": "catalogue",
            "app.module": "catalogue",
            "app.logical_endpoint": "catalogue.get_product",
        })

        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM products WHERE id = :id"), {"id": product_id}
            )
            product = result.mappings().first()

        if not product:
            # VULN: IDOR — can enumerate product IDs
            security_span("idor", severity="low",
                          payload=str(product_id),
                          source_ip=request.client.host if request.client else "",
                          endpoint=f"/api/products/{product_id}",
                          product_id=product_id)
            return {"error": "Product not found", "requested_id": product_id}

        return enrich_product(dict(product))


@router.get("/categories")
async def list_categories():
    """List distinct categories."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT DISTINCT category FROM products WHERE is_active = 1 ORDER BY category")
        )
        return {"categories": [r[0] for r in result.all()]}


@router.get("/products/{product_id}/reviews")
async def get_reviews(product_id: int):
    """Get product reviews."""
    tracer = get_tracer()
    with tracer.start_as_current_span("catalogue.get_reviews") as span:
        apply_span_attributes(span, {
            "catalogue.product_id": product_id,
            "app.page.name": "catalogue",
            "app.module": "catalogue",
            "app.logical_endpoint": "catalogue.get_reviews",
        })
        async with get_db() as db:
            result = await db.execute(
                text("SELECT id, rating, comment, author_name, created_at "
                     "FROM reviews WHERE product_id = :pid ORDER BY created_at DESC"),
                {"pid": product_id},
            )
            reviews = [dict(r) for r in result.mappings().all()]
            span.set_attribute("db.row_count", len(reviews))
        return {"reviews": reviews, "count": len(reviews)}


@router.post("/products/{product_id}/reviews")
async def create_review(product_id: int, payload: dict, request: Request):
    """Create review — VULN: Stored XSS in comment, no auth required."""
    tracer = get_tracer()
    source_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("catalogue.create_review") as span:
        apply_span_attributes(span, {
            "catalogue.product_id": product_id,
            "app.page.name": "catalogue",
            "app.module": "catalogue",
            "app.logical_endpoint": "catalogue.create_review",
        })
        comment = payload.get("comment", "")
        author = payload.get("author_name", "Anonymous")
        rating = payload.get("rating", 5)

        # VULN: No HTML sanitization — stored XSS
        if "<script" in comment.lower() or "onerror" in comment.lower():
            security_span("xss", severity="high", payload=comment,
                          source_ip=source_ip, endpoint=f"/api/products/{product_id}/reviews",
                          product_id=product_id)

        async with get_db() as db:
            await db.execute(
                text("INSERT INTO reviews (product_id, rating, comment, author_name) "
                     "VALUES (:pid, :rating, :review_comment, :author)"),
                {"pid": product_id, "rating": rating,
                 "review_comment": comment, "author": author},
            )

        return {"status": "created", "product_id": product_id}
