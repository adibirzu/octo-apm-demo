"""Database engine, session, and models for MuShop Cloud Native Portal.

Supports Oracle ATP (production) and PostgreSQL (development).
Uses SQLAlchemy async for both backends.
"""

import os
import logging
from contextlib import asynccontextmanager

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey,
    create_engine, text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func

from server.config import cfg

logger = logging.getLogger(__name__)

Base = declarative_base()

# ── Engine creation ──────────────────────────────────────────────

_engine_kwargs = {
    "echo": False,
    "pool_size": 5,
    "max_overflow": 10,
    "pool_pre_ping": True,
}

if cfg.use_oracle:
    import oracledb
    oracledb.init_oracle_client()  # thin mode if no Instant Client

    _connect_args = {}
    if cfg.oracle_wallet_dir:
        _connect_args["config_dir"] = cfg.oracle_wallet_dir
        _connect_args["wallet_location"] = cfg.oracle_wallet_dir
        _connect_args["wallet_password"] = cfg.oracle_wallet_password

    engine = create_async_engine(
        cfg.database_url,
        connect_args={
            "dsn": cfg.oracle_dsn,
            **_connect_args,
        },
        **_engine_kwargs,
    )
else:
    engine = create_async_engine(cfg.database_url, **_engine_kwargs)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_db():
    """Yield an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Models ───────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(50), default="user")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    category = Column(String(100))
    image_url = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    phone = Column(String(50))
    company = Column(String(200))
    industry = Column(String(100))
    revenue = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    total = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    notes = Column(Text)
    shipping_address = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    customer = relationship("Customer")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    order = relationship("Order")
    product = relationship("Product")


class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    product = relationship("Product")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    author_name = Column(String(200))
    created_at = Column(DateTime, server_default=func.now())
    product = relationship("Product")


class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    discount_percent = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    max_uses = Column(Integer, default=100)
    used_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    tracking_number = Column(String(100))
    carrier = Column(String(100))
    status = Column(String(50), default="processing")
    origin_region = Column(String(50))
    destination_region = Column(String(50))
    weight_kg = Column(Float, default=0.0)
    shipping_cost = Column(Float, default=0.0)
    estimated_delivery = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    order = relationship("Order")


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    region = Column(String(50), nullable=False)
    address = Column(Text)
    capacity = Column(Integer, default=10000)
    current_stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    campaign_type = Column(String(50), default="email")
    status = Column(String(50), default="draft")
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)
    target_audience = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    leads = relationship("Lead", back_populates="campaign")


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    email = Column(String(200), nullable=False)
    name = Column(String(200))
    source = Column(String(100))
    status = Column(String(50), default="new")
    score = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    campaign = relationship("Campaign", back_populates="leads")


class PageView(Base):
    __tablename__ = "page_views"
    id = Column(Integer, primary_key=True)
    page = Column(String(200), nullable=False)
    visitor_ip = Column(String(50))
    visitor_region = Column(String(50))
    user_agent = Column(String(500))
    load_time_ms = Column(Integer)
    session_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    action = Column(String(100), nullable=False)
    resource = Column(String(200))
    details = Column(Text)
    ip_address = Column(String(50))
    trace_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())
