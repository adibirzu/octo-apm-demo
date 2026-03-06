"""OCI APM Test App — Database engine, session, models, and initialization.

Supports Oracle ATP (production) and PostgreSQL (development).
Uses SQLAlchemy async for both backends. Creates tables + seeds on startup.
"""

import os
import logging
from contextlib import asynccontextmanager

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey,
    Identity, create_engine, text, inspect,
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
    # Use thin mode (pure-Python, no Oracle Instant Client needed)
    oracledb.defaults.config_dir = cfg.oracle_wallet_dir or ""
    oracledb.defaults.fetch_lobs = False

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
    # Sync engine for create_all (Oracle)
    _sync_url = f"oracle+oracledb://{cfg.oracle_user}:{cfg.oracle_password}@"
    _sync_connect = {"dsn": cfg.oracle_dsn, **_connect_args}
    sync_engine = create_engine(_sync_url, connect_args=_sync_connect)
else:
    engine = create_async_engine(cfg.database_url, **_engine_kwargs)
    _sync_url = cfg.database_sync_url or cfg.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    sync_engine = create_engine(_sync_url) if _sync_url else None

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
    id = Column(Integer, Identity(always=False), primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(50), default="user")
    is_active = Column(Integer, default=1)  # Use Integer for Oracle compat
    last_login = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    category = Column(String(100))
    image_url = Column(String(500))
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())


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


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, Identity(always=False), primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    total = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    notes = Column(Text)
    shipping_address = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    customer = relationship("Customer")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, Identity(always=False), primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    order = relationship("Order")
    product = relationship("Product")


class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, Identity(always=False), primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    product = relationship("Product")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, Identity(always=False), primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    author_name = Column(String(200))
    created_at = Column(DateTime, server_default=func.now())
    product = relationship("Product")


class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, Identity(always=False), primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    discount_percent = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    is_active = Column(Integer, default=1)
    max_uses = Column(Integer, default=100)
    used_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


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
    created_at = Column(DateTime, server_default=func.now())
    order = relationship("Order")


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
    created_at = Column(DateTime, server_default=func.now())
    leads = relationship("Lead", back_populates="campaign")


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, Identity(always=False), primary_key=True)
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
    id = Column(Integer, Identity(always=False), primary_key=True)
    page = Column(String(200), nullable=False)
    visitor_ip = Column(String(50))
    visitor_region = Column(String(50))
    user_agent = Column(String(500))
    referrer = Column(String(500))
    load_time_ms = Column(Integer)
    session_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, Identity(always=False), primary_key=True)
    user_id = Column(Integer)
    action = Column(String(100), nullable=False)
    resource = Column(String(200))
    details = Column(Text)
    ip_address = Column(String(50))
    trace_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


# ── Database Initialization ──────────────────────────────────────

def init_tables():
    """Create all tables if they don't exist (works with both PG and Oracle).

    If tables exist but are empty and missing Identity columns (Oracle),
    drops and recreates them with proper Identity columns.
    """
    if sync_engine is None:
        logger.warning("No sync engine — skipping table creation")
        return
    try:
        insp = inspect(sync_engine)
        existing_tables = insp.get_table_names()

        if cfg.use_oracle and "users" in existing_tables:
            # Check if users table is empty — if so, drop all and recreate
            # (fixes tables created without IDENTITY columns)
            from sqlalchemy.orm import Session
            with Session(sync_engine) as session:
                count = session.execute(text("SELECT COUNT(*) FROM users")).scalar()
                if count == 0:
                    logger.info("Oracle tables exist but are empty — dropping for Identity column fix")
                    Base.metadata.drop_all(sync_engine)

        Base.metadata.create_all(sync_engine, checkfirst=True)
        logger.info("Database tables created/verified (backend: %s)",
                     "oracle" if cfg.use_oracle else "postgresql")
    except Exception as e:
        logger.error("Failed to create tables: %s", e)
        raise


def seed_data():
    """Insert seed data if tables are empty."""
    if sync_engine is None:
        return
    from sqlalchemy.orm import Session
    try:
        with Session(sync_engine) as session:
            if session.query(User).count() > 0:
                logger.info("Database already seeded — skipping")
                return

            # Users
            session.add_all([
                User(username="admin", email="admin@ocitest.local",
                     password_hash="$2b$12$LJ3X5wKv7IfAzGMkVbHDneFQ3KQJXhHjqW/Tq3hXqp6NpXq8vU5Lm",
                     role="admin"),
                User(username="shopper", email="shopper@ocitest.local",
                     password_hash="$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy",
                     role="user"),
                User(username="manager", email="manager@ocitest.local",
                     password_hash="$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy",
                     role="manager"),
                User(username="analyst", email="analyst@ocitest.local",
                     password_hash="$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy",
                     role="analyst"),
                User(username="support", email="support@ocitest.local",
                     password_hash="$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy",
                     role="support"),
            ])
            session.flush()

            # Products (12 items)
            products = [
                Product(name="OCI Classic Tee", sku="TEE-001", description="Classic cotton t-shirt with OCI logo",
                        price=29.99, stock=500, category="Clothing"),
                Product(name="Cloud Hoodie", sku="HOD-001", description="Warm hoodie for cloud-native developers",
                        price=59.99, stock=200, category="Clothing"),
                Product(name="Cloud Socks (3-pack)", sku="SOC-001", description="Comfortable socks with cloud patterns",
                        price=14.99, stock=1000, category="Clothing"),
                Product(name="DevOps Cap", sku="CAP-001", description="Baseball cap for the DevOps lifestyle",
                        price=24.99, stock=300, category="Accessories"),
                Product(name="Kubernetes Sticker Pack", sku="STK-001", description="Pack of 10 K8s-themed stickers",
                        price=9.99, stock=2000, category="Accessories"),
                Product(name="OCI Mug", sku="MUG-001", description="Ceramic mug with Oracle Cloud Infrastructure logo",
                        price=19.99, stock=400, category="Drinkware"),
                Product(name="Microservices Mug", sku="MUG-002", description="Mug celebrating distributed systems",
                        price=19.99, stock=350, category="Drinkware"),
                Product(name="Cloud Native Backpack", sku="BAG-001", description="Durable laptop backpack for on-the-go",
                        price=79.99, stock=100, category="Bags"),
                Product(name="Terraform Notebook", sku="NTB-001", description="Hardcover notebook for infrastructure planning",
                        price=15.99, stock=600, category="Stationery"),
                Product(name="Docker Whale Plush", sku="PLH-001", description="Adorable blue whale plushie",
                        price=24.99, stock=150, category="Toys"),
                Product(name="Observability Poster", sku="PST-001", description="Wall poster: traces, metrics, and logs",
                        price=12.99, stock=400, category="Decor"),
                Product(name="Zero Trust Lanyard", sku="LAN-001", description="Security-themed conference lanyard",
                        price=7.99, stock=800, category="Accessories"),
            ]
            session.add_all(products)
            session.flush()

            # Customers (8)
            customers = [
                Customer(name="Acme Corp", email="contact@acme.com", phone="+1-555-0101",
                         company="Acme Corporation", industry="Manufacturing", revenue=5200000),
                Customer(name="Globex Industries", email="info@globex.com", phone="+1-555-0102",
                         company="Globex", industry="Technology", revenue=12800000),
                Customer(name="Initech Solutions", email="sales@initech.com", phone="+1-555-0103",
                         company="Initech", industry="Consulting", revenue=3400000),
                Customer(name="Stark Industries", email="tony@stark.com", phone="+1-555-0105",
                         company="Stark Ind", industry="Defense", revenue=89000000),
                Customer(name="Wayne Enterprises", email="bruce@wayne.com", phone="+1-555-0106",
                         company="Wayne Ent", industry="Conglomerate", revenue=120000000),
                Customer(name="Cyberdyne Systems", email="info@cyberdyne.com", phone="+1-555-0107",
                         company="Cyberdyne", industry="AI/Robotics", revenue=8900000),
                Customer(name="Umbrella Corp", email="hq@umbrella.com", phone="+1-555-0108",
                         company="Umbrella", industry="Pharmaceuticals", revenue=45000000),
                Customer(name="Weyland-Yutani", email="admin@wy.corp", phone="+1-555-0109",
                         company="Weyland-Yutani", industry="Aerospace", revenue=67000000),
            ]
            session.add_all(customers)
            session.flush()

            # Orders (8)
            orders = [
                Order(customer_id=1, total=89.97, status="completed", shipping_address="123 Industrial Way, Springfield"),
                Order(customer_id=2, total=159.97, status="processing", shipping_address="456 Tech Park, Silicon Valley"),
                Order(customer_id=3, total=44.98, status="pending", shipping_address="789 Consulting Blvd, New York"),
                Order(customer_id=4, total=79.99, status="shipped", shipping_address="10880 Malibu Point, CA"),
                Order(customer_id=1, total=29.99, status="completed", shipping_address="123 Industrial Way, Springfield"),
                Order(customer_id=5, total=134.97, status="processing", shipping_address="1007 Mountain Drive, Gotham"),
                Order(customer_id=7, total=49.98, status="pending", shipping_address="Raccoon City, 42 Hive St"),
                Order(customer_id=8, total=95.98, status="shipped", shipping_address="Gateway Station, LV-426"),
            ]
            session.add_all(orders)
            session.flush()

            # Order Items
            session.add_all([
                OrderItem(order_id=1, product_id=1, quantity=2, unit_price=29.99),
                OrderItem(order_id=1, product_id=3, quantity=2, unit_price=14.99),
                OrderItem(order_id=2, product_id=2, quantity=1, unit_price=59.99),
                OrderItem(order_id=2, product_id=8, quantity=1, unit_price=79.99),
                OrderItem(order_id=2, product_id=6, quantity=1, unit_price=19.99),
                OrderItem(order_id=3, product_id=5, quantity=2, unit_price=9.99),
                OrderItem(order_id=3, product_id=9, quantity=1, unit_price=15.99),
                OrderItem(order_id=3, product_id=12, quantity=1, unit_price=7.99),
                OrderItem(order_id=4, product_id=8, quantity=1, unit_price=79.99),
                OrderItem(order_id=5, product_id=1, quantity=1, unit_price=29.99),
                OrderItem(order_id=6, product_id=2, quantity=1, unit_price=59.99),
                OrderItem(order_id=6, product_id=4, quantity=1, unit_price=24.99),
                OrderItem(order_id=6, product_id=10, quantity=2, unit_price=24.99),
                OrderItem(order_id=7, product_id=6, quantity=1, unit_price=19.99),
                OrderItem(order_id=7, product_id=1, quantity=1, unit_price=29.99),
                OrderItem(order_id=8, product_id=2, quantity=1, unit_price=59.99),
                OrderItem(order_id=8, product_id=9, quantity=1, unit_price=15.99),
                OrderItem(order_id=8, product_id=6, quantity=1, unit_price=19.99),
            ])

            # Reviews (10)
            session.add_all([
                Review(product_id=1, rating=5, comment="Best t-shirt ever! Super comfortable.", author_name="CloudFan"),
                Review(product_id=1, rating=4, comment="Nice quality, runs a bit large", author_name="DevOpsGuru"),
                Review(product_id=2, rating=5, comment="Perfect for those chilly server room visits", author_name="SRELife"),
                Review(product_id=3, rating=3, comment="Socks are ok, expected more cloud patterns", author_name="K8sNewbie"),
                Review(product_id=6, rating=5, comment="Great mug! Keeps coffee hot during standups", author_name="MorningDev"),
                Review(product_id=8, rating=4, comment="Solid backpack, fits 15\" laptop perfectly", author_name="NomadCoder"),
                Review(product_id=10, rating=5, comment="So cute! Sits on my monitor now", author_name="DockerLover"),
                Review(product_id=4, rating=4, comment="Cool cap, gets compliments at conferences", author_name="ConferenceGoer"),
                Review(product_id=11, rating=5, comment="Awesome poster for the office wall", author_name="ObsNerd"),
                Review(product_id=9, rating=3, comment="Good paper quality but binding could be better", author_name="PlannerPro"),
            ])

            # Coupons (5)
            session.add_all([
                Coupon(code="WELCOME10", discount_percent=10.0, is_active=1, max_uses=1000),
                Coupon(code="CLOUD20", discount_percent=20.0, is_active=1, max_uses=500),
                Coupon(code="FREESHIP", discount_amount=9.99, is_active=1, max_uses=200),
                Coupon(code="VIP50", discount_percent=50.0, is_active=1, max_uses=10),
                Coupon(code="EXPIRED", discount_percent=15.0, is_active=0, max_uses=0),
            ])

            # Shipments (8)
            session.add_all([
                Shipment(order_id=1, tracking_number="FDX-OCI-001", carrier="fedex", status="delivered",
                         origin_region="us-east-1", destination_region="us-east-1", weight_kg=0.8, shipping_cost=9.99),
                Shipment(order_id=2, tracking_number="UPS-OCI-001", carrier="ups", status="in_transit",
                         origin_region="us-west-2", destination_region="eu-central-1", weight_kg=1.5, shipping_cost=29.99),
                Shipment(order_id=3, tracking_number="DHL-OCI-001", carrier="dhl", status="processing",
                         origin_region="eu-central-1", destination_region="ap-northeast-1", weight_kg=0.4, shipping_cost=19.99),
                Shipment(order_id=4, tracking_number="FDX-OCI-002", carrier="fedex", status="shipped",
                         origin_region="us-east-1", destination_region="us-west-2", weight_kg=2.0, shipping_cost=14.99),
                Shipment(order_id=5, tracking_number="USPS-OCI-001", carrier="usps", status="delivered",
                         origin_region="us-east-1", destination_region="us-east-1", weight_kg=0.3, shipping_cost=5.99),
                Shipment(order_id=6, tracking_number="DHL-OCI-002", carrier="dhl", status="in_transit",
                         origin_region="eu-central-1", destination_region="sa-east-1", weight_kg=1.2, shipping_cost=39.99),
                Shipment(order_id=7, tracking_number="FDX-OCI-003", carrier="fedex", status="processing",
                         origin_region="us-east-1", destination_region="eu-central-1", weight_kg=0.5, shipping_cost=12.99),
                Shipment(order_id=8, tracking_number="UPS-OCI-002", carrier="ups", status="shipped",
                         origin_region="ap-southeast-1", destination_region="us-west-2", weight_kg=1.8, shipping_cost=34.99),
            ])

            # Warehouses (5)
            session.add_all([
                Warehouse(name="US East Fulfillment", region="us-east-1", address="100 Cloud Way, Virginia",
                          capacity=50000, current_stock=32000, is_active=1),
                Warehouse(name="EU Central Hub", region="eu-central-1", address="50 OCI Str., Frankfurt",
                          capacity=30000, current_stock=18000, is_active=1),
                Warehouse(name="APAC Distribution", region="ap-southeast-1", address="88 Container Rd, Singapore",
                          capacity=20000, current_stock=8500, is_active=1),
                Warehouse(name="US West Warehouse", region="us-west-2", address="200 K8s Ave, Oregon",
                          capacity=25000, current_stock=15000, is_active=1),
                Warehouse(name="Middle East DC", region="me-south-1", address="10 Data Center Blvd, Dubai",
                          capacity=15000, current_stock=5000, is_active=1),
            ])

            # Campaigns (5)
            session.add_all([
                Campaign(name="Launch Sale", campaign_type="email", status="completed",
                         budget=25000, spent=24500, target_audience="All customers"),
                Campaign(name="Summer Collection", campaign_type="social", status="active",
                         budget=15000, spent=6000, target_audience="Young professionals"),
                Campaign(name="DevOps Swag Drop", campaign_type="ppc", status="active",
                         budget=10000, spent=4200, target_audience="DevOps engineers"),
                Campaign(name="Partner Program", campaign_type="referral", status="active",
                         budget=50000, spent=18000, target_audience="Cloud partners"),
                Campaign(name="Security Awareness", campaign_type="email", status="active",
                         budget=8000, spent=2100, target_audience="Security teams"),
            ])
            session.flush()

            # Leads (8)
            session.add_all([
                Lead(campaign_id=1, email="lead1@techco.com", name="Alice Smith", source="web", status="converted", score=92),
                Lead(campaign_id=1, email="lead2@startup.io", name="Bob Jones", source="referral", status="qualified", score=78),
                Lead(campaign_id=2, email="lead3@bigcorp.com", name="Carol Lee", source="social", status="contacted", score=65),
                Lead(campaign_id=2, email="lead4@dev.tools", name="Dave Brown", source="paid", status="new", score=40),
                Lead(campaign_id=3, email="lead5@sre.team", name="Eve Wilson", source="web", status="qualified", score=85),
                Lead(campaign_id=4, email="lead6@cloud.partner", name="Frank Chen", source="referral", status="converted", score=95),
                Lead(campaign_id=5, email="lead7@infosec.co", name="Grace Park", source="web", status="new", score=55),
                Lead(campaign_id=5, email="lead8@blueteam.org", name="Hank Miller", source="social", status="contacted", score=70),
            ])

            # Page Views (15)
            session.add_all([
                PageView(page="/shop", visitor_ip="10.0.1.1", visitor_region="eu-central-1", load_time_ms=95, session_id="sess-001"),
                PageView(page="/catalogue", visitor_ip="10.0.1.1", visitor_region="eu-central-1", load_time_ms=110, session_id="sess-001"),
                PageView(page="/shop", visitor_ip="10.0.2.1", visitor_region="us-east-1", load_time_ms=180, session_id="sess-002"),
                PageView(page="/shop", visitor_ip="10.0.3.1", visitor_region="ap-northeast-1", load_time_ms=420, session_id="sess-003"),
                PageView(page="/orders", visitor_ip="10.0.3.1", visitor_region="ap-northeast-1", load_time_ms=380, session_id="sess-003"),
                PageView(page="/shop", visitor_ip="10.0.4.1", visitor_region="us-west-2", load_time_ms=200, session_id="sess-004"),
                PageView(page="/analytics", visitor_ip="10.0.5.1", visitor_region="ap-southeast-1", load_time_ms=510, session_id="sess-005"),
                PageView(page="/shop", visitor_ip="10.0.6.1", visitor_region="sa-east-1", load_time_ms=650, session_id="sess-006"),
                PageView(page="/catalogue", visitor_ip="10.0.7.1", visitor_region="af-south-1", load_time_ms=870, session_id="sess-007"),
                PageView(page="/shop", visitor_ip="10.0.1.2", visitor_region="eu-central-1", load_time_ms=88, session_id="sess-008"),
                PageView(page="/admin-page", visitor_ip="10.0.8.1", visitor_region="me-south-1", load_time_ms=350, session_id="sess-009"),
                PageView(page="/login", visitor_ip="10.0.9.1", visitor_region="us-east-1", load_time_ms=95, session_id="sess-010"),
                PageView(page="/shop", visitor_ip="10.0.10.1", visitor_region="eu-west-1", load_time_ms=130, session_id="sess-011"),
                PageView(page="/catalogue", visitor_ip="10.0.11.1", visitor_region="us-west-2", load_time_ms=160, session_id="sess-012"),
                PageView(page="/orders", visitor_ip="10.0.12.1", visitor_region="ap-southeast-2", load_time_ms=440, session_id="sess-013"),
            ])

            # Audit Logs (5)
            session.add_all([
                AuditLog(user_id=1, action="login", resource="auth", details="Admin login from 10.0.1.1"),
                AuditLog(user_id=2, action="view_products", resource="catalogue", details="Viewed product list"),
                AuditLog(user_id=1, action="export_config", resource="admin", details="Exported app config"),
                AuditLog(user_id=3, action="create_order", resource="orders", details="Order #1 created"),
                AuditLog(user_id=1, action="view_audit_logs", resource="admin", details="Viewed audit trail"),
            ])

            session.commit()
            logger.info("Database seeded with initial data")

    except Exception as e:
        logger.error("Failed to seed database: %s", e)
        raise
