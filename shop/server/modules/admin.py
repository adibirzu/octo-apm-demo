"""Admin module — governed access to users, audit logs, runtime state, and DB edits."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from opentelemetry import trace
from sqlalchemy import text

from server.auth_security import require_role
from server.config import cfg
from server.database import AuditLog, Base, get_db, seed_data, sync_engine
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ALLOWED_USER_ROLES = {"user", "admin", "manager", "analyst", "support"}
_ALLOWED_ORDER_STATUSES = {"pending", "queued", "processing", "completed", "shipped", "cancelled"}
_ALLOWED_PAYMENT_STATUSES = {"pending", "paid", "failed", "refunded"}
_ALLOWED_INVOICE_STATUSES = {"draft", "issued", "paid", "overdue", "void"}


def _require_admin(request: Request) -> dict:
    return require_role(request, "admin")


def _guard_mutation(request: Request) -> dict:
    admin_user = _require_admin(request)
    if cfg.environment == "production" or cfg.app_runtime == "oke":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative data reset is disabled in production",
        )
    return admin_user


def _trace_id() -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().trace_id:
        return format(span.get_span_context().trace_id, "032x")
    return ""


def _string_value(payload: dict, key: str, *, required: bool = False, max_len: int = 5000) -> str:
    value = str(payload.get(key, "") or "").strip()
    if required and not value:
        raise HTTPException(status_code=400, detail=f"{key} is required")
    if len(value) > max_len:
        raise HTTPException(status_code=400, detail=f"{key} exceeds {max_len} characters")
    return value


def _email_value(payload: dict, key: str = "email") -> str:
    value = _string_value(payload, key, required=True, max_len=200).lower()
    if "@" not in value or "." not in value.split("@")[-1]:
        raise HTTPException(status_code=400, detail=f"{key} must be a valid email address")
    return value


def _int_value(payload: dict, key: str, *, required: bool = False) -> int | None:
    raw = payload.get(key)
    if raw in (None, ""):
        if required:
            raise HTTPException(status_code=400, detail=f"{key} is required")
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{key} must be an integer") from exc


def _float_value(payload: dict, key: str, *, required: bool = False, minimum: float | None = None) -> float | None:
    raw = payload.get(key)
    if raw in (None, ""):
        if required:
            raise HTTPException(status_code=400, detail=f"{key} is required")
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{key} must be numeric") from exc
    if minimum is not None and value < minimum:
        raise HTTPException(status_code=400, detail=f"{key} must be >= {minimum}")
    return value


def _enum_value(payload: dict, key: str, allowed: set[str], *, default: str | None = None) -> str:
    raw = payload.get(key, default)
    value = str(raw or "").strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail=f"{key} is required")
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"{key} must be one of: {', '.join(sorted(allowed))}")
    return value


def _datetime_value(payload: dict, key: str) -> datetime | None:
    raw = payload.get(key)
    if raw in (None, ""):
        return None
    text_value = str(raw).strip()
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{key} must be ISO-8601 date/time") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


async def _require_existing_row(db, table: str, row_id: int, field_name: str = "id") -> dict:
    result = await db.execute(
        text(f"SELECT * FROM {table} WHERE {field_name} = :value FETCH FIRST 1 ROWS ONLY"),
        {"value": row_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{table[:-1].title()} not found")
    return dict(row)


async def _write_audit(db, request: Request, admin_user: dict, *, action: str, resource: str, details: str) -> None:
    db.add(
        AuditLog(
            user_id=int(admin_user["sub"]),
            action=action,
            resource=resource,
            details=details,
            ip_address=request.client.host if request.client else "unknown",
            trace_id=_trace_id(),
        )
    )


def _invoice_number() -> str:
    return f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"


@router.get("/users")
async def list_users(request: Request):
    """List users with non-sensitive account metadata."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_users") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])

        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, username, email, role, is_active, last_login, created_at "
                    "FROM users ORDER BY created_at DESC"
                )
            )
            users = [dict(r) for r in result.mappings().all()]

        span.set_attribute("admin.user_count", len(users))
        return {"users": users}


@router.get("/shops")
async def list_shops(request: Request):
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_shops") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, name, address, coordinates, contact_email, contact_phone, is_active, created_at "
                    "FROM shops ORDER BY created_at DESC FETCH FIRST 200 ROWS ONLY"
                )
            )
            shops = [dict(r) for r in result.mappings().all()]
        span.set_attribute("admin.shop_count", len(shops))
        return {"shops": shops}


@router.get("/products")
async def list_products(request: Request):
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_products") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, name, sku, description, price, stock, category, image_url, is_active, created_at "
                    "FROM products ORDER BY created_at DESC FETCH FIRST 200 ROWS ONLY"
                )
            )
            products = [dict(r) for r in result.mappings().all()]
        span.set_attribute("admin.product_count", len(products))
        return {"products": products}


@router.get("/customers")
async def list_customers(request: Request):
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_customers") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT id, name, email, phone, company, industry, revenue, notes, created_at, updated_at "
                    "FROM customers ORDER BY updated_at DESC FETCH FIRST 200 ROWS ONLY"
                )
            )
            customers = [dict(r) for r in result.mappings().all()]
        span.set_attribute("admin.customer_count", len(customers))
        return {"customers": customers}


@router.get("/orders")
async def list_orders(request: Request):
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_orders") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT o.id, o.customer_id, c.name AS customer_name, c.email AS customer_email, "
                    "o.total, o.status, o.payment_method, o.payment_status, o.shipping_address, o.notes, o.created_at "
                    "FROM orders o LEFT JOIN customers c ON c.id = o.customer_id "
                    "ORDER BY o.created_at DESC FETCH FIRST 200 ROWS ONLY"
                )
            )
            orders = [dict(r) for r in result.mappings().all()]
        span.set_attribute("admin.order_count", len(orders))
        return {"orders": orders}


@router.get("/invoices")
async def list_invoices(request: Request):
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_invoices") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        async with get_db() as db:
            result = await db.execute(
                text(
                    "SELECT i.id, i.invoice_number, i.customer_id, c.name AS customer_name, i.order_id, "
                    "i.amount, i.currency, i.status, i.issued_at, i.due_at, i.paid_at, i.notes, i.created_at, i.updated_at "
                    "FROM invoices i LEFT JOIN customers c ON c.id = i.customer_id "
                    "ORDER BY i.created_at DESC FETCH FIRST 200 ROWS ONLY"
                )
            )
            invoices = [dict(r) for r in result.mappings().all()]
        span.set_attribute("admin.invoice_count", len(invoices))
        return {"invoices": invoices}


@router.get("/audit-logs")
async def list_audit_logs(request: Request):
    """List recent audit log entries."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.list_audit_logs") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])

        async with get_db() as db:
            result = await db.execute(
                text("SELECT * FROM audit_logs ORDER BY created_at DESC FETCH FIRST 100 ROWS ONLY")
            )
            logs = [dict(r) for r in result.mappings().all()]

        span.set_attribute("admin.log_count", len(logs))
        return {"audit_logs": logs}


@router.get("/config")
async def get_config(request: Request):
    """Return deployment state without exposing live secrets."""
    admin_user = _require_admin(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.get_config") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.config_requested", True)
        return cfg.safe_runtime_summary()


@router.post("/seed")
async def trigger_seed(request: Request):
    """Manually trigger seeding outside production environments."""
    admin_user = _guard_mutation(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.seed") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        seed_data()
    return {"status": "seeded"}


@router.post("/reseed")
async def trigger_reseed(request: Request):
    """Recreate all tables and reseed outside production environments."""
    admin_user = _guard_mutation(request)
    tracer = get_tracer()
    with tracer.start_as_current_span("admin.reseed") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        if sync_engine is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database sync engine unavailable")

        Base.metadata.drop_all(sync_engine)
        Base.metadata.create_all(sync_engine)
        seed_data()
    return {"status": "reseeded"}


@router.post("/users")
async def create_user(request: Request, payload: dict):
    """Create a new user in the database."""
    admin_user = _require_admin(request)
    tracer = get_tracer()

    username = _string_value(payload, "username", required=True, max_len=100)
    email = _email_value(payload)
    password = _string_value(payload, "password", required=True, max_len=200)
    role = _enum_value(payload, "role", _ALLOWED_USER_ROLES, default="user")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    with tracer.start_as_current_span("admin.create_user") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.target_user", username)

        async with get_db() as db:
            await db.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, role, is_active) "
                    "VALUES (:username, :email, :password, :role, 1)"
                ),
                {"username": username, "email": email, "password": hashed, "role": role},
            )
            await _write_audit(
                db,
                request,
                admin_user,
                action="create_user",
                resource="users",
                details=f"Created user {username}",
            )

        push_log("INFO", f"Admin {admin_user['username']} created new user {username}", **{"admin.target_user": username})
        return {"status": "success", "message": f"User {username} created"}


@router.post("/partners")
async def create_partner(request: Request, payload: dict):
    """Create a new partner (shop) in the database."""
    admin_user = _require_admin(request)
    tracer = get_tracer()

    name = _string_value(payload, "name", required=True, max_len=200)
    address = _string_value(payload, "address", required=True, max_len=2000)
    contact_email = _string_value(payload, "contact_email", max_len=200)
    contact_phone = _string_value(payload, "contact_phone", max_len=50)

    with tracer.start_as_current_span("admin.create_partner") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.target_partner", name)

        async with get_db() as db:
            await db.execute(
                text(
                    "INSERT INTO shops (name, address, coordinates, contact_email, contact_phone, is_active) "
                    "VALUES (:name, :address, '0,0', :email, :phone, 1)"
                ),
                {"name": name, "address": address, "email": contact_email, "phone": contact_phone},
            )
            await _write_audit(
                db,
                request,
                admin_user,
                action="create_partner",
                resource="shops",
                details=f"Created partner location {name}",
            )

        push_log("INFO", f"Admin {admin_user['username']} created new partner {name}", **{"admin.target_partner": name})
        return {"status": "success", "message": f"Partner {name} created"}


@router.post("/shops")
async def create_shop(request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    shop = {
        "name": _string_value(payload, "name", required=True, max_len=200),
        "address": _string_value(payload, "address", required=True, max_len=2000),
        "coordinates": _string_value(payload, "coordinates", max_len=100),
        "contact_email": _string_value(payload, "contact_email", max_len=200),
        "contact_phone": _string_value(payload, "contact_phone", max_len=50),
        "is_active": _int_value(payload, "is_active") if payload.get("is_active") not in (None, "") else 1,
    }
    if shop["is_active"] not in (0, 1):
        raise HTTPException(status_code=400, detail="is_active must be 0 or 1")

    with tracer.start_as_current_span("admin.create_shop") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.shop_name", shop["name"])
        async with get_db() as db:
            await db.execute(
                text(
                    "INSERT INTO shops (name, address, coordinates, contact_email, contact_phone, is_active) "
                    "VALUES (:name, :address, :coordinates, :contact_email, :contact_phone, :is_active)"
                ),
                shop,
            )
            created = await db.execute(
                text(
                    "SELECT id, name, address, coordinates, contact_email, contact_phone, is_active, created_at "
                    "FROM shops WHERE name = :name ORDER BY created_at DESC FETCH FIRST 1 ROWS ONLY"
                ),
                {"name": shop["name"]},
            )
            row = dict(created.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="create_shop",
                resource=f"shops/{row['id']}",
                details=f"Created shop {row['name']}",
            )

        return {"status": "success", "message": f"Shop {row['name']} created", "shop": row}


@router.put("/shops/{shop_id}")
async def update_shop(shop_id: int, request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    shop = {
        "id": shop_id,
        "name": _string_value(payload, "name", required=True, max_len=200),
        "address": _string_value(payload, "address", required=True, max_len=2000),
        "coordinates": _string_value(payload, "coordinates", max_len=100),
        "contact_email": _string_value(payload, "contact_email", max_len=200),
        "contact_phone": _string_value(payload, "contact_phone", max_len=50),
        "is_active": _int_value(payload, "is_active") if payload.get("is_active") not in (None, "") else 1,
    }
    if shop["is_active"] not in (0, 1):
        raise HTTPException(status_code=400, detail="is_active must be 0 or 1")

    with tracer.start_as_current_span("admin.update_shop") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.shop_id", shop_id)
        async with get_db() as db:
            await _require_existing_row(db, "shops", shop_id)
            await db.execute(
                text(
                    "UPDATE shops SET name = :name, address = :address, coordinates = :coordinates, "
                    "contact_email = :contact_email, contact_phone = :contact_phone, is_active = :is_active "
                    "WHERE id = :id"
                ),
                shop,
            )
            updated = await db.execute(
                text(
                    "SELECT id, name, address, coordinates, contact_email, contact_phone, is_active, created_at "
                    "FROM shops WHERE id = :id"
                ),
                {"id": shop_id},
            )
            row = dict(updated.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="update_shop",
                resource=f"shops/{shop_id}",
                details=f"Updated shop {row['name']}",
            )

        return {"status": "success", "message": f"Shop {row['name']} updated", "shop": row}


@router.post("/products")
async def create_product(request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    stock = _int_value(payload, "stock", required=True)
    if stock is not None and stock < 0:
        raise HTTPException(status_code=400, detail="stock must be >= 0")

    product = {
        "name": _string_value(payload, "name", required=True, max_len=200),
        "sku": _string_value(payload, "sku", required=True, max_len=50).upper(),
        "description": _string_value(payload, "description", max_len=4000),
        "price": _float_value(payload, "price", required=True, minimum=0) or 0.0,
        "stock": stock or 0,
        "category": _string_value(payload, "category", max_len=100),
        "image_url": _string_value(payload, "image_url", max_len=500),
        "is_active": _int_value(payload, "is_active") if payload.get("is_active") not in (None, "") else 1,
    }
    if product["is_active"] not in (0, 1):
        raise HTTPException(status_code=400, detail="is_active must be 0 or 1")

    with tracer.start_as_current_span("admin.create_product") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.product_sku", product["sku"])
        async with get_db() as db:
            existing = await db.execute(
                text("SELECT id FROM products WHERE upper(sku) = upper(:sku) FETCH FIRST 1 ROWS ONLY"),
                {"sku": product["sku"]},
            )
            if existing.mappings().first():
                raise HTTPException(status_code=409, detail="Product SKU already exists")

            await db.execute(
                text(
                    "INSERT INTO products (name, sku, description, price, stock, category, image_url, is_active) "
                    "VALUES (:name, :sku, :description, :price, :stock, :category, :image_url, :is_active)"
                ),
                product,
            )
            created = await db.execute(
                text(
                    "SELECT id, name, sku, description, price, stock, category, image_url, is_active, created_at "
                    "FROM products WHERE upper(sku) = upper(:sku) FETCH FIRST 1 ROWS ONLY"
                ),
                {"sku": product["sku"]},
            )
            row = dict(created.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="create_product",
                resource=f"products/{row['id']}",
                details=f"Created product {row['sku']}",
            )

        return {"status": "success", "message": f"Product {row['sku']} created", "product": row}


@router.put("/products/{product_id}")
async def update_product(product_id: int, request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    stock = _int_value(payload, "stock", required=True)
    if stock is not None and stock < 0:
        raise HTTPException(status_code=400, detail="stock must be >= 0")

    product = {
        "id": product_id,
        "name": _string_value(payload, "name", required=True, max_len=200),
        "sku": _string_value(payload, "sku", required=True, max_len=50).upper(),
        "description": _string_value(payload, "description", max_len=4000),
        "price": _float_value(payload, "price", required=True, minimum=0) or 0.0,
        "stock": stock or 0,
        "category": _string_value(payload, "category", max_len=100),
        "image_url": _string_value(payload, "image_url", max_len=500),
        "is_active": _int_value(payload, "is_active") if payload.get("is_active") not in (None, "") else 1,
    }
    if product["is_active"] not in (0, 1):
        raise HTTPException(status_code=400, detail="is_active must be 0 or 1")

    with tracer.start_as_current_span("admin.update_product") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.product_id", product_id)
        async with get_db() as db:
            await _require_existing_row(db, "products", product_id)
            duplicate = await db.execute(
                text(
                    "SELECT id FROM products WHERE upper(sku) = upper(:sku) AND id != :id "
                    "FETCH FIRST 1 ROWS ONLY"
                ),
                {"sku": product["sku"], "id": product_id},
            )
            if duplicate.mappings().first():
                raise HTTPException(status_code=409, detail="Product SKU already exists")

            await db.execute(
                text(
                    "UPDATE products SET name = :name, sku = :sku, description = :description, price = :price, "
                    "stock = :stock, category = :category, image_url = :image_url, is_active = :is_active "
                    "WHERE id = :id"
                ),
                product,
            )
            updated = await db.execute(
                text(
                    "SELECT id, name, sku, description, price, stock, category, image_url, is_active, created_at "
                    "FROM products WHERE id = :id"
                ),
                {"id": product_id},
            )
            row = dict(updated.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="update_product",
                resource=f"products/{product_id}",
                details=f"Updated product {row['sku']}",
            )

        return {"status": "success", "message": f"Product {row['sku']} updated", "product": row}


@router.post("/customers")
async def create_customer(request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    customer = {
        "name": _string_value(payload, "name", required=True, max_len=200),
        "email": _email_value(payload),
        "phone": _string_value(payload, "phone", max_len=50),
        "company": _string_value(payload, "company", max_len=200),
        "industry": _string_value(payload, "industry", max_len=100),
        "revenue": _float_value(payload, "revenue", minimum=0) or 0.0,
        "notes": _string_value(payload, "notes", max_len=4000),
    }

    with tracer.start_as_current_span("admin.create_customer") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.customer_email", customer["email"])
        async with get_db() as db:
            existing = await db.execute(
                text("SELECT id FROM customers WHERE lower(email) = lower(:email) FETCH FIRST 1 ROWS ONLY"),
                {"email": customer["email"]},
            )
            if existing.mappings().first():
                raise HTTPException(status_code=409, detail="Customer email already exists")

            await db.execute(
                text(
                    "INSERT INTO customers (name, email, phone, company, industry, revenue, notes) "
                    "VALUES (:name, :email, :phone, :company, :industry, :revenue, :notes)"
                ),
                customer,
            )
            created = await db.execute(
                text(
                    "SELECT id, name, email, phone, company, industry, revenue, notes, created_at, updated_at "
                    "FROM customers WHERE lower(email) = lower(:email) FETCH FIRST 1 ROWS ONLY"
                ),
                {"email": customer["email"]},
            )
            row = dict(created.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="create_customer",
                resource=f"customers/{row['id']}",
                details=f"Created customer {row['email']}",
            )

        return {"status": "success", "message": f"Customer {row['email']} created", "customer": row}


@router.put("/customers/{customer_id}")
async def update_customer(customer_id: int, request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    customer = {
        "name": _string_value(payload, "name", required=True, max_len=200),
        "email": _email_value(payload),
        "phone": _string_value(payload, "phone", max_len=50),
        "company": _string_value(payload, "company", max_len=200),
        "industry": _string_value(payload, "industry", max_len=100),
        "revenue": _float_value(payload, "revenue", minimum=0) or 0.0,
        "notes": _string_value(payload, "notes", max_len=4000),
        "id": customer_id,
    }

    with tracer.start_as_current_span("admin.update_customer") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.customer_id", customer_id)
        async with get_db() as db:
            await _require_existing_row(db, "customers", customer_id)
            duplicate = await db.execute(
                text(
                    "SELECT id FROM customers WHERE lower(email) = lower(:email) AND id != :id "
                    "FETCH FIRST 1 ROWS ONLY"
                ),
                {"email": customer["email"], "id": customer_id},
            )
            if duplicate.mappings().first():
                raise HTTPException(status_code=409, detail="Customer email already exists")

            await db.execute(
                text(
                    "UPDATE customers SET name = :name, email = :email, phone = :phone, company = :company, "
                    "industry = :industry, revenue = :revenue, notes = :notes, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :id"
                ),
                customer,
            )
            updated = await db.execute(
                text(
                    "SELECT id, name, email, phone, company, industry, revenue, notes, created_at, updated_at "
                    "FROM customers WHERE id = :id"
                ),
                {"id": customer_id},
            )
            row = dict(updated.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="update_customer",
                resource=f"customers/{customer_id}",
                details=f"Updated customer {row['email']}",
            )

        return {"status": "success", "message": f"Customer {row['email']} updated", "customer": row}


@router.post("/orders")
async def create_order(request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    customer_id = _int_value(payload, "customer_id", required=True)
    total = _float_value(payload, "total", required=True, minimum=0) or 0.0
    order = {
        "customer_id": customer_id,
        "total": total,
        "status": _enum_value(payload, "status", _ALLOWED_ORDER_STATUSES, default="pending"),
        "payment_method": _string_value(payload, "payment_method", max_len=50) or "credit_card",
        "payment_status": _enum_value(payload, "payment_status", _ALLOWED_PAYMENT_STATUSES, default="pending"),
        "shipping_address": _string_value(payload, "shipping_address", required=True, max_len=4000),
        "notes": _string_value(payload, "notes", max_len=4000),
    }

    with tracer.start_as_current_span("admin.create_order") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.customer_id", customer_id)
        async with get_db() as db:
            await _require_existing_row(db, "customers", customer_id)
            await db.execute(
                text(
                    "INSERT INTO orders (customer_id, total, status, payment_method, payment_status, shipping_address, notes) "
                    "VALUES (:customer_id, :total, :status, :payment_method, :payment_status, :shipping_address, :notes)"
                ),
                order,
            )
            created = await db.execute(
                text(
                    "SELECT id, customer_id, total, status, payment_method, payment_status, shipping_address, notes, created_at "
                    "FROM orders WHERE customer_id = :customer_id ORDER BY created_at DESC FETCH FIRST 1 ROWS ONLY"
                ),
                {"customer_id": customer_id},
            )
            row = dict(created.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="create_order",
                resource=f"orders/{row['id']}",
                details=f"Created admin order #{row['id']}",
            )

        return {"status": "success", "message": f"Order #{row['id']} created", "order": row}


@router.put("/orders/{order_id}")
async def update_order(order_id: int, request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    customer_id = _int_value(payload, "customer_id", required=True)
    order = {
        "id": order_id,
        "customer_id": customer_id,
        "total": _float_value(payload, "total", required=True, minimum=0) or 0.0,
        "status": _enum_value(payload, "status", _ALLOWED_ORDER_STATUSES, default="pending"),
        "payment_method": _string_value(payload, "payment_method", max_len=50) or "credit_card",
        "payment_status": _enum_value(payload, "payment_status", _ALLOWED_PAYMENT_STATUSES, default="pending"),
        "shipping_address": _string_value(payload, "shipping_address", required=True, max_len=4000),
        "notes": _string_value(payload, "notes", max_len=4000),
    }

    with tracer.start_as_current_span("admin.update_order") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.order_id", order_id)
        async with get_db() as db:
            await _require_existing_row(db, "customers", customer_id)
            await _require_existing_row(db, "orders", order_id)
            await db.execute(
                text(
                    "UPDATE orders SET customer_id = :customer_id, total = :total, status = :status, "
                    "payment_method = :payment_method, payment_status = :payment_status, "
                    "shipping_address = :shipping_address, notes = :notes WHERE id = :id"
                ),
                order,
            )
            updated = await db.execute(
                text(
                    "SELECT id, customer_id, total, status, payment_method, payment_status, shipping_address, notes, created_at "
                    "FROM orders WHERE id = :id"
                ),
                {"id": order_id},
            )
            row = dict(updated.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="update_order",
                resource=f"orders/{order_id}",
                details=f"Updated order #{order_id}",
            )

        return {"status": "success", "message": f"Order #{order_id} updated", "order": row}


@router.post("/invoices")
async def create_invoice(request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    customer_id = _int_value(payload, "customer_id", required=True)
    order_id = _int_value(payload, "order_id")
    amount = _float_value(payload, "amount", minimum=0)
    due_at = _datetime_value(payload, "due_at")
    paid_at = _datetime_value(payload, "paid_at")
    issued_at = _datetime_value(payload, "issued_at") or datetime.utcnow()
    invoice_number = _string_value(payload, "invoice_number", max_len=100) or _invoice_number()

    with tracer.start_as_current_span("admin.create_invoice") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.customer_id", customer_id)
        async with get_db() as db:
            await _require_existing_row(db, "customers", customer_id)
            order_total = None
            if order_id is not None:
                existing_order = await _require_existing_row(db, "orders", order_id)
                order_total = float(existing_order["total"] or 0.0)

            final_amount = amount if amount is not None else order_total
            if final_amount is None:
                raise HTTPException(status_code=400, detail="amount is required when order_id is not provided")

            await db.execute(
                text(
                    "INSERT INTO invoices (invoice_number, customer_id, order_id, amount, currency, status, issued_at, due_at, paid_at, notes) "
                    "VALUES (:invoice_number, :customer_id, :order_id, :amount, :currency, :status, :issued_at, :due_at, :paid_at, :notes)"
                ),
                {
                    "invoice_number": invoice_number,
                    "customer_id": customer_id,
                    "order_id": order_id,
                    "amount": final_amount,
                    "currency": _string_value(payload, "currency", max_len=10) or "USD",
                    "status": _enum_value(payload, "status", _ALLOWED_INVOICE_STATUSES, default="draft"),
                    "issued_at": issued_at,
                    "due_at": due_at,
                    "paid_at": paid_at,
                    "notes": _string_value(payload, "notes", max_len=4000),
                },
            )
            created = await db.execute(
                text(
                    "SELECT id, invoice_number, customer_id, order_id, amount, currency, status, issued_at, due_at, paid_at, notes, created_at, updated_at "
                    "FROM invoices WHERE invoice_number = :invoice_number FETCH FIRST 1 ROWS ONLY"
                ),
                {"invoice_number": invoice_number},
            )
            row = dict(created.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="create_invoice",
                resource=f"invoices/{row['id']}",
                details=f"Created invoice {invoice_number}",
            )

        return {"status": "success", "message": f"Invoice {invoice_number} created", "invoice": row}


@router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: int, request: Request, payload: dict):
    admin_user = _require_admin(request)
    tracer = get_tracer()

    customer_id = _int_value(payload, "customer_id", required=True)
    order_id = _int_value(payload, "order_id")
    invoice_number = _string_value(payload, "invoice_number", required=True, max_len=100)
    amount = _float_value(payload, "amount", required=True, minimum=0) or 0.0

    with tracer.start_as_current_span("admin.update_invoice") as span:
        span.set_attribute("admin.requested_by", admin_user["username"])
        span.set_attribute("admin.invoice_id", invoice_id)
        async with get_db() as db:
            await _require_existing_row(db, "customers", customer_id)
            await _require_existing_row(db, "invoices", invoice_id)
            if order_id is not None:
                await _require_existing_row(db, "orders", order_id)

            duplicate = await db.execute(
                text(
                    "SELECT id FROM invoices WHERE invoice_number = :invoice_number AND id != :id "
                    "FETCH FIRST 1 ROWS ONLY"
                ),
                {"invoice_number": invoice_number, "id": invoice_id},
            )
            if duplicate.mappings().first():
                raise HTTPException(status_code=409, detail="Invoice number already exists")

            await db.execute(
                text(
                    "UPDATE invoices SET invoice_number = :invoice_number, customer_id = :customer_id, "
                    "order_id = :order_id, amount = :amount, currency = :currency, status = :status, "
                    "issued_at = :issued_at, due_at = :due_at, paid_at = :paid_at, notes = :notes, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                ),
                {
                    "id": invoice_id,
                    "invoice_number": invoice_number,
                    "customer_id": customer_id,
                    "order_id": order_id,
                    "amount": amount,
                    "currency": _string_value(payload, "currency", max_len=10) or "USD",
                    "status": _enum_value(payload, "status", _ALLOWED_INVOICE_STATUSES, default="draft"),
                    "issued_at": _datetime_value(payload, "issued_at") or datetime.utcnow(),
                    "due_at": _datetime_value(payload, "due_at"),
                    "paid_at": _datetime_value(payload, "paid_at"),
                    "notes": _string_value(payload, "notes", max_len=4000),
                },
            )
            updated = await db.execute(
                text(
                    "SELECT id, invoice_number, customer_id, order_id, amount, currency, status, issued_at, due_at, paid_at, notes, created_at, updated_at "
                    "FROM invoices WHERE id = :id"
                ),
                {"id": invoice_id},
            )
            row = dict(updated.mappings().first())
            await _write_audit(
                db,
                request,
                admin_user,
                action="update_invoice",
                resource=f"invoices/{invoice_id}",
                details=f"Updated invoice {invoice_number}",
            )

        return {"status": "success", "message": f"Invoice {invoice_number} updated", "invoice": row}
