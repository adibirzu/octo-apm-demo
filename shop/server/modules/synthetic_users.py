"""Synthetic corporate user and order generation for private demos."""

from __future__ import annotations

import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from server.config import cfg
from server.observability import business_metrics
from server.observability.correlation import apply_span_attributes
from server.observability.logging_sdk import push_log
from server.observability.otel_setup import get_tracer
from server.store_service import ensure_customer, place_order


router = APIRouter(prefix="/api/synthetic", tags=["synthetic-users"])

DEFAULT_SYNTHETIC_USER_EMAIL_DOMAIN = "apex.example.test"
_MAX_SYNTHETIC_USERS = 100
_MAX_SYNTHETIC_ORDERS = 50
_DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$")

_PERSONAS: tuple[tuple[str, str, str, str], ...] = (
    ("alex", "chen", "Alex Chen", "Apex Fleet Operations"),
    ("maya", "ionescu", "Maya Ionescu", "Apex Field Services"),
    ("nora", "patel", "Nora Patel", "Apex Energy Survey"),
    ("daniel", "rossi", "Daniel Rossi", "Apex Infrastructure"),
    ("irina", "marin", "Irina Marin", "Apex Public Safety"),
    ("samuel", "wright", "Samuel Wright", "Apex Logistics"),
    ("elena", "garcia", "Elena Garcia", "Apex Agriculture"),
    ("noah", "kim", "Noah Kim", "Apex Inspection Group"),
    ("sofia", "andersen", "Sofia Andersen", "Apex Rail Systems"),
    ("matei", "popa", "Matei Popa", "Apex Utilities"),
    ("lina", "hoffman", "Lina Hoffman", "Apex Emergency Response"),
    ("omar", "saleh", "Omar Saleh", "Apex Maritime"),
)


@dataclass(frozen=True)
class SyntheticUser:
    username: str
    email: str
    display_name: str
    company: str


def normalize_synthetic_domain(domain: str | None) -> str:
    """Validate a synthetic e-mail domain and return a lower-case value."""
    normalized = (domain or DEFAULT_SYNTHETIC_USER_EMAIL_DOMAIN).strip().lower()
    if "@" in normalized or "/" in normalized or not _DOMAIN_RE.fullmatch(normalized):
        raise ValueError("synthetic user e-mail domain must be a DNS-style domain name")
    return normalized


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def generate_synthetic_users(*, count: int, domain: str | None) -> list[SyntheticUser]:
    """Build deterministic corporate-style synthetic users."""
    safe_domain = normalize_synthetic_domain(domain)
    safe_count = _clamp_int(count, default=12, minimum=1, maximum=_MAX_SYNTHETIC_USERS)
    users: list[SyntheticUser] = []
    for index in range(safe_count):
        first, last, display_name, company = _PERSONAS[index % len(_PERSONAS)]
        suffix = "" if index < len(_PERSONAS) else f"{(index // len(_PERSONAS)) + 1}"
        username = f"{first}.{last}{suffix}"
        users.append(
            SyntheticUser(
                username=username,
                email=f"{username}@{safe_domain}",
                display_name=display_name if not suffix else f"{display_name} {suffix}",
                company=company,
            )
        )
    return users


def _require_internal_key(request: Request) -> None:
    configured = (cfg.internal_service_key or "").strip()
    supplied = (request.headers.get("X-Internal-Service-Key") or "").strip()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service key is not configured",
        )
    if not hmac.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-Service-Key",
        )


def _synthetic_password_hash() -> str:
    password = secrets.token_urlsafe(24)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def _upsert_synthetic_user(db: Any, user: SyntheticUser, password_hash: str) -> tuple[int, bool]:
    existing = await db.execute(
        text(
            "SELECT id FROM users WHERE lower(username) = lower(:username) "
            "OR lower(email) = lower(:email) FETCH FIRST 1 ROWS ONLY"
        ),
        {"username": user.username, "email": user.email},
    )
    row = existing.mappings().first()
    if row:
        await db.execute(
            text(
                "UPDATE users SET username = :username, email = :email, role = 'synthetic_user', "
                "is_active = 1 WHERE id = :id"
            ),
            {"id": row["id"], "username": user.username, "email": user.email},
        )
        return int(row["id"]), False

    await db.execute(
        text(
            "INSERT INTO users (username, email, password_hash, role, is_active) "
            "VALUES (:username, :email, :password_hash, 'synthetic_user', 1)"
        ),
        {
            "username": user.username,
            "email": user.email,
            "password_hash": password_hash,
        },
    )
    created = await db.execute(
        text("SELECT id FROM users WHERE lower(email) = lower(:email) FETCH FIRST 1 ROWS ONLY"),
        {"email": user.email},
    )
    created_row = created.mappings().first()
    return int(created_row["id"]), True


async def _delete_old_synthetic_users(db: Any, *, domain: str, retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(
        text(
            "DELETE FROM users WHERE role = 'synthetic_user' "
            "AND lower(email) LIKE :domain_pattern AND created_at < :cutoff"
        ),
        {"domain_pattern": f"%@{domain}", "cutoff": cutoff},
    )
    return int(result.rowcount or 0)


async def _active_products(db: Any, limit: int = 8) -> list[dict[str, Any]]:
    safe_limit = _clamp_int(limit, default=8, minimum=1, maximum=25)
    result = await db.execute(
        text(
            "SELECT id, name, price FROM products WHERE is_active = 1 "
            f"ORDER BY id FETCH FIRST {safe_limit} ROWS ONLY"
        ),
    )
    return [dict(row) for row in result.mappings().all()]


@router.post("/users/run")
async def run_synthetic_users(request: Request, payload: dict | None = None):
    """Create/update synthetic users and generate a small order batch."""
    _require_internal_key(request)
    body = payload or {}
    domain = normalize_synthetic_domain(body.get("domain") or body.get("email_domain"))
    users = generate_synthetic_users(
        count=_clamp_int(body.get("count"), default=12, minimum=1, maximum=_MAX_SYNTHETIC_USERS),
        domain=domain,
    )
    order_count = _clamp_int(body.get("order_count"), default=6, minimum=0, maximum=_MAX_SYNTHETIC_ORDERS)
    retention_days = _clamp_int(body.get("delete_after_days"), default=7, minimum=0, maximum=365)
    trace_id = ""

    tracer = get_tracer()
    with tracer.start_as_current_span("synthetic.users.run") as span:
        span_context = span.get_span_context()
        if span_context.trace_id:
            trace_id = format(span_context.trace_id, "032x")
        apply_span_attributes(
            span,
            {
                "app.module": "synthetic-users",
                "app.logical_endpoint": "synthetic.users.run",
                "synthetic.user.domain": domain,
                "synthetic.user.count": len(users),
                "synthetic.order.requested_count": order_count,
                "synthetic.user.retention_days": retention_days,
                "db.target": cfg.database_target_label,
            },
        )

        from server.database import get_db

        created_users = 0
        updated_users = 0
        orders_created = 0
        deleted_users = 0
        product_names: list[str] = []
        password_hash = _synthetic_password_hash()

        async with get_db() as db:
            deleted_users = await _delete_old_synthetic_users(db, domain=domain, retention_days=retention_days)
            products = await _active_products(db)
            if not products and order_count:
                raise HTTPException(status_code=409, detail="No active products available for synthetic orders")
            product_names = [str(product["name"]) for product in products[:3]]

            customers: list[dict[str, Any]] = []
            for user in users:
                _, created = await _upsert_synthetic_user(db, user, password_hash)
                created_users += int(created)
                updated_users += int(not created)
                customers.append(
                    await ensure_customer(
                        db,
                        name=user.display_name,
                        email=user.email,
                        phone="+1-555-0100",
                        company=user.company,
                        industry="Drone Operations",
                    )
                )

            for index in range(order_count):
                customer = customers[index % len(customers)]
                first_product = products[index % len(products)]
                second_product = products[(index + 1) % len(products)]
                order_key = sha256(f"{trace_id}:{customer['email']}:{index}".encode("utf-8")).hexdigest()
                order = await place_order(
                    db,
                    customer=customer,
                    items=[
                        {
                            "product_id": int(first_product["id"]),
                            "quantity": 1 + (index % 2),
                            "price": float(first_product["price"]),
                        },
                        {
                            "product_id": int(second_product["id"]),
                            "quantity": 1,
                            "price": float(second_product["price"]),
                        },
                    ],
                    shipping_address="Synthetic fleet operations address",
                    payment_method="credit_card",
                    notes=f"Synthetic user activity run; domain={domain}; user={customer['email'].split('@')[0]}",
                    session_id=f"synthetic-{order_key[:16]}",
                    source="synthetic-user-cron",
                    trace_id=trace_id,
                    checkout_idempotency_key=order_key,
                )
                orders_created += int(not order.get("idempotent_replay"))

        span.set_attribute("synthetic.user.created_count", created_users)
        span.set_attribute("synthetic.user.updated_count", updated_users)
        span.set_attribute("synthetic.user.deleted_count", deleted_users)
        span.set_attribute("synthetic.order.created_count", orders_created)
        business_metrics.record_synthetic_user_run(
            created=created_users,
            updated=updated_users,
            deleted=deleted_users,
            orders_created=orders_created,
            generator="vm-scheduler",
        )
        push_log(
            "INFO",
            "Synthetic user activity generated",
            **{
                "synthetic.user.domain": domain,
                "synthetic.user.created_count": created_users,
                "synthetic.user.updated_count": updated_users,
                "synthetic.user.deleted_count": deleted_users,
                "synthetic.order.created_count": orders_created,
                "synthetic.user.generator": "vm-scheduler",
            },
        )
        return {
            "status": "completed",
            "domain": domain,
            "created_users": created_users,
            "updated_users": updated_users,
            "deleted_users": deleted_users,
            "orders_created": orders_created,
            "synthetic_users": [
                {"username": user.username, "email": user.email, "display_name": user.display_name}
                for user in users
            ],
            "sample_products": product_names,
            "trace_id": trace_id,
        }
