"""Database engine, session management, and models (PostgreSQL or Oracle ATP)."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey,
    UniqueConstraint, Identity, create_engine, inspect, text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

from server.config import cfg

logger = logging.getLogger(__name__)

# ── Engine creation (PostgreSQL or Oracle ATP) ─────────────────────

_engine_kwargs = {
    "pool_size": cfg.db_pool_size,
    "max_overflow": cfg.db_max_overflow,
    "pool_timeout": cfg.db_pool_timeout,
    "pool_pre_ping": True,
    "echo": False,
}

_connect_args: dict = {}
_oracle_configured = bool(cfg.oracle_dsn and cfg.oracle_password)
if not cfg.use_postgres and _oracle_configured:
    import oracledb

    oracledb.defaults.config_dir = cfg.oracle_wallet_dir or ""
    oracledb.defaults.fetch_lobs = False
    _connect_args = {"dsn": cfg.oracle_dsn}
    if cfg.oracle_wallet_dir:
        _connect_args["config_dir"] = cfg.oracle_wallet_dir
        _connect_args["wallet_location"] = cfg.oracle_wallet_dir
        _connect_args["wallet_password"] = cfg.oracle_wallet_password

_database_configured = bool(cfg._database_url) if cfg.use_postgres else _oracle_configured

engine = None
sync_engine = None
async_session_factory = None

if _database_configured:
    try:
        engine = create_async_engine(
            cfg.database_url,
            connect_args=_connect_args,
            **_engine_kwargs,
        )
        sync_engine = create_engine(
            cfg.database_sync_url,
            connect_args=_connect_args,
            # Sizing notes (see KB-435):
            # - This engine is used by the session middleware's per-request auth
            #   lookup, so it must handle bursts of cache misses without queueing.
            # - The 30s in-process session cache in auth.py cushions repeat hits, so
            #   we only need enough capacity for concurrent *new* session validations.
            # - It must NOT mirror the async pool — doubling the Oracle ATP session
            #   footprint per replica risks fleet-wide session exhaustion.
            # - `pool_pre_ping=True` prevents stale connections from silently failing
            #   after Oracle-side password rotations.
            # - Pool sizing comes from config (DB_AUTH_POOL_SIZE etc.) so ops can tune
            #   and observe it independently of the main app pool.
            pool_pre_ping=True,
            pool_size=cfg.db_auth_pool_size,
            max_overflow=cfg.db_auth_max_overflow,
            pool_timeout=cfg.db_auth_pool_timeout,
        )
        async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
        if cfg.use_postgres:
            logger.info("Using PostgreSQL backend for local/standalone workflow")
        else:
            logger.info("Using Oracle ATP backend (DSN: %s)", cfg.oracle_dsn)
    except ModuleNotFoundError as exc:
        engine = None
        sync_engine = None
        async_session_factory = None
        logger.warning(
            "Database engine not initialized because the configured driver is unavailable: %s",
            exc,
        )
else:
    logger.warning("Database engine not initialized because no database credentials were configured")

# Enrich every DB query with db.statement + db.oracle.sql_id for APM Trace Explorer
from server.observability.db_spans import register_db_span_events
if not cfg.use_postgres and engine is not None and sync_engine is not None:
    register_db_span_events(engine)
    register_db_span_events(sync_engine)

# Tag Oracle sessions with MODULE/ACTION/CLIENT_IDENTIFIER for OPSI + DB Management correlation
from server.observability.db_session_tagging import register_session_tagging
if not cfg.use_postgres and engine is not None and sync_engine is not None:
    register_session_tagging(engine)
    register_session_tagging(sync_engine)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session with chaos simulation support."""
    if cfg.simulate_db_disconnect:
        raise ConnectionError("Simulated database disconnect")
    if cfg.simulate_db_latency:
        await asyncio.sleep(2.5)
    if async_session_factory is None:
        raise RuntimeError("Database engine is not configured")
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── ORM Models (Oracle + PostgreSQL compatible) ────────────────────
# - Identity(always=False) works on both Oracle and PostgreSQL
# - Integer instead of Boolean for Oracle compatibility

class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    phone = Column(String(50))
    company = Column(String(200))
    industry = Column(String(100))
    revenue = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    orders = relationship("Order", back_populates="customer")
    tickets = relationship("SupportTicket", back_populates="customer")


class Shop(Base):
    __tablename__ = "shops"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(200), nullable=False)
    address = Column(Text, default="")
    coordinates = Column(String(100), default="")
    contact_email = Column(String(200), default="")
    contact_phone = Column(String(50), default="")
    is_active = Column(Integer, default=1)
    slug = Column(String(80), unique=True, nullable=False)
    storefront_url = Column(String(500), nullable=False)
    crm_base_url = Column(String(500), nullable=False)
    region = Column(String(80), nullable=False)
    currency = Column(String(10), default="USD")
    status = Column(String(50), default="active")
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    products = relationship("Product", back_populates="shop")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, Identity(always=False), primary_key=True)
    shop_id = Column(Integer, ForeignKey("shops.id"))
    name = Column(String(200), nullable=False)
    sku = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    category = Column(String(100))
    image_url = Column(String(500))
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    shop = relationship("Shop", back_populates="products")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("source_system", "source_order_id", name="uq_orders_source_ref"),
    )
    id = Column(Integer, Identity(always=False), primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    total = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    notes = Column(Text)
    shipping_address = Column(Text)
    source_system = Column(String(100), default="enterprise-crm")
    source_order_id = Column(String(120))
    source_customer_email = Column(String(200))
    sync_status = Column(String(50), default="local")
    backlog_status = Column(String(50), default="current")
    sync_error = Column(Text)
    source_payload = Column(Text)
    correlation_id = Column(String(128))
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, Identity(always=False), primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, Identity(always=False), primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    invoice_number = Column(String(50), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    tax = Column(Float, default=0.0)
    status = Column(String(50), default="unpaid")
    due_date = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    order = relationship("Order")


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(Integer, Identity(always=False), primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    subject = Column(String(300), nullable=False)
    description = Column(Text)
    priority = Column(String(20), default="medium")
    status = Column(String(50), default="open")
    assigned_to = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    customer = relationship("Customer", back_populates="tickets")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, Identity(always=False), primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(50), default="user")
    is_active = Column(Integer, default=1)
    last_login = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, Identity(always=False), primary_key=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False)
    auth_method = Column(String(30), default="password")
    created_at = Column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, Identity(always=False), primary_key=True)
    user_id = Column(Integer)
    action = Column(String(100), nullable=False)
    resource = Column(String(200))
    details = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    trace_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(200), nullable=False)
    report_type = Column(String(50))
    query = Column(Text)
    parameters = Column(Text)
    created_by = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(200), nullable=False)
    campaign_type = Column(String(50), default="email")
    status = Column(String(50), default="draft")
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)
    target_audience = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    leads = relationship("Lead", back_populates="campaign")


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, Identity(always=False), primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    email = Column(String(200), nullable=False)
    name = Column(String(200))
    source = Column(String(100))
    status = Column(String(50), default="new")
    score = Column(Integer, default=0)
    notes = Column(Text)
    converted_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    campaign = relationship("Campaign", back_populates="leads")
    customer = relationship("Customer")


class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, Identity(always=False), primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    tracking_number = Column(String(100))
    carrier = Column(String(100))
    status = Column(String(50), default="processing")
    origin_region = Column(String(50))
    destination_region = Column(String(50))
    weight_kg = Column(Float, default=0.0)
    shipping_cost = Column(Float, default=0.0)
    estimated_delivery = Column(DateTime)
    actual_delivery = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    order = relationship("Order")


class PageView(Base):
    __tablename__ = "page_views"
    id = Column(Integer, Identity(always=False), primary_key=True)
    page = Column(String(200), nullable=False)
    visitor_ip = Column(String(50))
    visitor_region = Column(String(50))
    user_agent = Column(String(500))
    load_time_ms = Column(Integer)
    referrer = Column(String(500))
    session_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(200), nullable=False)
    region = Column(String(50), nullable=False)
    address = Column(Text)
    capacity = Column(Integer, default=10000)
    current_stock = Column(Integer, default=0)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())


class OrderSyncAudit(Base):
    __tablename__ = "order_sync_audit"
    id = Column(Integer, Identity(always=False), primary_key=True)
    source_system = Column(String(100), nullable=False)
    source_order_id = Column(String(120))
    sync_action = Column(String(50), nullable=False)
    sync_status = Column(String(50), nullable=False)
    message = Column(Text)
    correlation_id = Column(String(128))
    trace_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())
