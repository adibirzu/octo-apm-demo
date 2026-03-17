"""Catalogue module — products, categories, search, reviews."""

import html
import re

from fastapi import APIRouter, Request, Query
from sqlalchemy import text
from server.database import get_db
from server.observability.correlation import apply_span_attributes, sql_attributes
from server.observability.otel_setup import get_tracer
from server.storefront import enrich_product

router = APIRouter(prefix="/api", tags=["catalogue"])

_ALLOWED_SORT = {"name", "price", "stock", "category", "created_at", "id"}


@router.get("/products")
async def list_products(request: Request,
                        search: str = "", category: str = "",
                        sort_by: str = "name"):
    """List products with safe parameterized filtering."""
    tracer = get_tracer()

    with tracer.start_as_current_span("catalogue.list_products") as span:
        apply_span_attributes(span, {
            "catalogue.search": search,
            "catalogue.category": category,
            "app.page.name": "catalogue",
            "app.module": "catalogue",
            "app.logical_endpoint": "catalogue.list_products",
        })

        # Validate sort column against whitelist
        safe_sort = sort_by if sort_by in _ALLOWED_SORT else "name"

        async with get_db() as db:
            conditions = ["is_active = 1"]
            params: dict = {}

            if search:
                conditions.append("(name LIKE :search OR description LIKE :search)")
                params["search"] = f"%{search}%"

            if category:
                conditions.append("category = :category")
                params["category"] = category

            where = " AND ".join(conditions)
            query = (
                f"SELECT id, name, sku, description, price, stock, category, image_url "
                f"FROM products WHERE {where} ORDER BY {safe_sort}"
            )

            with tracer.start_as_current_span("db.query.products") as db_span:
                apply_span_attributes(db_span, sql_attributes(query, connection_name="", database_target="oracle_atp"))
                result = await db.execute(text(query), params)
                products = [enrich_product(dict(r)) for r in result.mappings().all()]
                db_span.set_attribute("db.row_count", len(products))

        return {"products": products}


@router.get("/products/{product_id}")
async def get_product(product_id: int, request: Request):
    """Get single product by ID."""
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
            return {"error": "Product not found"}

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


def _sanitize_html(text_input: str) -> str:
    """Strip HTML tags and escape remaining content."""
    stripped = re.sub(r"<[^>]+>", "", text_input)
    return html.escape(stripped, quote=True)


@router.post("/products/{product_id}/reviews")
async def create_review(product_id: int, payload: dict, request: Request):
    """Create product review with input sanitization."""
    tracer = get_tracer()

    with tracer.start_as_current_span("catalogue.create_review") as span:
        apply_span_attributes(span, {
            "catalogue.product_id": product_id,
            "app.page.name": "catalogue",
            "app.module": "catalogue",
            "app.logical_endpoint": "catalogue.create_review",
        })

        comment = _sanitize_html(str(payload.get("comment", "")))
        author = _sanitize_html(str(payload.get("author_name", "Anonymous")))[:100]
        rating = max(1, min(5, int(payload.get("rating", 5) or 5)))

        async with get_db() as db:
            # Verify product exists
            exists = await db.execute(
                text("SELECT id FROM products WHERE id = :pid AND is_active = 1"),
                {"pid": product_id},
            )
            if not exists.first():
                return {"error": "Product not found"}

            await db.execute(
                text("INSERT INTO reviews (product_id, rating, comment, author_name) "
                     "VALUES (:pid, :rating, :review_comment, :author)"),
                {"pid": product_id, "rating": rating,
                 "review_comment": comment, "author": author},
            )

        return {"status": "created", "product_id": product_id}
