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

            # Products — Drone Shop (24 items, EU/US manufacturers only)
            products = [
                # Complete Drones
                Product(name="Skydio X10", sku="DRN-001", description="AI-powered autonomous drone with 6 cameras, 35min flight time. Obstacle avoidance in all directions. Made in USA.",
                        price=10999.00, stock=25, category="Complete Drones"),
                Product(name="Parrot ANAFI Ai", sku="DRN-002", description="4G-connected robotic drone, 4K HDR camera, 32min flight. NATO-approved platform. Made in France.",
                        price=4499.00, stock=40, category="Complete Drones"),
                Product(name="Autel EVO II Pro V3", sku="DRN-003", description="6K camera, 42min flight time, 9km range. 1-inch CMOS sensor. Designed in USA.",
                        price=1899.00, stock=60, category="Complete Drones"),
                Product(name="Wingtra WingtraOne GEN II", sku="DRN-004", description="VTOL survey drone, 59min endurance, 42MP sensor. Survey-grade accuracy. Made in Switzerland.",
                        price=24900.00, stock=8, category="Complete Drones"),
                Product(name="Quantum-Systems Trinity F90+", sku="DRN-005", description="Fixed-wing VTOL mapping drone, 90min flight, PPK/RTK. Made in Germany.",
                        price=28500.00, stock=6, category="Complete Drones"),
                Product(name="Flyability ELIOS 3", sku="DRN-006", description="Caged inspection drone for confined spaces, LiDAR + 4K camera. Made in Switzerland.",
                        price=39900.00, stock=4, category="Complete Drones"),
                Product(name="Parrot ANAFI USA", sku="DRN-007", description="Secure drone with 32x zoom, FLIR thermal, no data connection to external servers. Made in France.",
                        price=7499.00, stock=15, category="Complete Drones"),
                Product(name="Freefly Astro", sku="DRN-008", description="Modular cinema drone, 8kg payload, interchangeable camera mounts. Made in USA.",
                        price=12495.00, stock=10, category="Complete Drones"),
                # Frames & Components
                Product(name="Holybro X500 V2 Frame Kit", sku="FRM-001", description="500mm quadcopter frame, ARF kit with Pixhawk 6C autopilot. Designed in USA.",
                        price=299.00, stock=120, category="Frames"),
                Product(name="IFlight Chimera7 Pro Frame", sku="FRM-002", description="7-inch long-range frame, full carbon fiber, HD compatible. Designed in USA.",
                        price=89.99, stock=200, category="Frames"),
                # Motors & ESCs
                Product(name="KDE Direct 4215XF-465 Motor", sku="MOT-001", description="High-performance brushless motor, 465KV, UAS-grade reliability. Made in USA.",
                        price=189.99, stock=150, category="Motors & ESCs"),
                Product(name="Holybro Tekko32 F4 4-in-1 ESC", sku="ESC-001", description="4x50A ESC, BLHeli_32, DShot1200. Current sensor built-in.",
                        price=69.99, stock=180, category="Motors & ESCs"),
                # Flight Controllers
                Product(name="Holybro Pixhawk 6X", sku="FLC-001", description="Open-source autopilot, STM32H7, triple IMU, industrial-grade. FMUv6X standard.",
                        price=399.99, stock=75, category="Flight Controllers"),
                Product(name="CUAV X7+ Pro", sku="FLC-002", description="Industrial autopilot, triple redundant IMU, CAN bus, vibration isolation. Designed in USA.",
                        price=549.00, stock=45, category="Flight Controllers"),
                # Cameras & Gimbals
                Product(name="Freefly MoVI Carbon Gimbal", sku="GMB-001", description="3-axis cinema gimbal, 15lb payload, Freefly MIMIC control. Made in USA.",
                        price=5995.00, stock=12, category="Cameras & Gimbals"),
                Product(name="Phase One P3 Payload", sku="CAM-001", description="100MP metric camera for aerial survey, iXM-RS150F lens. Made in Denmark.",
                        price=52000.00, stock=3, category="Cameras & Gimbals"),
                # Batteries & Power
                Product(name="Tattu 6S 10000mAh LiPo", sku="BAT-001", description="22.2V 25C high-capacity battery, XT60 connector. 6S for heavy-lift platforms.",
                        price=179.99, stock=250, category="Batteries"),
                Product(name="EcoFlow DELTA Mini", sku="BAT-002", description="882Wh portable power station for field charging. 1400W output. Designed in USA.",
                        price=799.00, stock=30, category="Batteries"),
                # Propellers
                Product(name="KDE Direct CF 15.5x5.3 Props (pair)", sku="PRP-001", description="Carbon fiber propellers, precision-balanced, UAS multi-rotor. Made in USA.",
                        price=89.99, stock=300, category="Propellers"),
                Product(name="Master Airscrew 13x4.5 Silent (set of 4)", sku="PRP-002", description="Low-noise propellers, optimized blade geometry. Designed in USA.",
                        price=29.99, stock=500, category="Propellers"),
                # FPV Gear
                Product(name="Orqa FPV.One Pilot Goggles", sku="FPV-001", description="OLED FPV goggles, 44-degree FOV, micro HDMI input. Made in Croatia (EU).",
                        price=549.00, stock=50, category="FPV Gear"),
                Product(name="TBS Crossfire Nano TX", sku="FPV-002", description="Long-range RC link module, 868/915MHz, up to 40km range. Designed in Switzerland.",
                        price=69.99, stock=100, category="FPV Gear"),
                # Accessories
                Product(name="Hoodman Drone Launch Pad (5ft)", sku="ACC-001", description="Weighted 5-foot landing pad, high-vis orange. Folds to 24in. Made in USA.",
                        price=89.99, stock=200, category="Accessories"),
                Product(name="Lowepro DroneGuard BP 450 AW", sku="ACC-002", description="Drone backpack, fits large quads + accessories, all-weather cover. Designed in USA.",
                        price=249.99, stock=80, category="Accessories"),
            ]
            session.add_all(products)
            session.flush()

            # Customers (8) — drone industry buyers
            customers = [
                Customer(name="Alpine Aerial Surveys", email="ops@alpineaerial.ch", phone="+41-44-555-0101",
                         company="Alpine Aerial AG", industry="Surveying & Mapping", revenue=4800000),
                Customer(name="Nordstrom Energy Inspections", email="fleet@nordstromenergy.se", phone="+46-8-555-0102",
                         company="Nordstrom Energy", industry="Energy & Utilities", revenue=18500000),
                Customer(name="Redwood SAR Solutions", email="dispatch@redwoodsar.com", phone="+1-503-555-0103",
                         company="Redwood SAR", industry="Search & Rescue", revenue=6200000),
                Customer(name="Atlantic Film Productions", email="gear@atlanticfilm.com", phone="+1-310-555-0104",
                         company="Atlantic Film", industry="Film & Media", revenue=22000000),
                Customer(name="EuroCrop Precision Ag", email="tech@eurocrop.de", phone="+49-30-555-0105",
                         company="EuroCrop GmbH", industry="Agriculture", revenue=9400000),
                Customer(name="Coastline Infrastructure Ltd", email="projects@coastlineinfra.co.uk", phone="+44-20-555-0106",
                         company="Coastline Infra", industry="Infrastructure Inspection", revenue=15000000),
                Customer(name="Summit Public Safety", email="procurement@summitps.gov", phone="+1-202-555-0107",
                         company="Summit PS", industry="Public Safety", revenue=32000000),
                Customer(name="Fjord Environmental Monitoring", email="sensors@fjordenv.no", phone="+47-22-555-0108",
                         company="Fjord Env AS", industry="Environmental", revenue=3800000),
            ]
            session.add_all(customers)
            session.flush()

            # Orders (8) — drone industry purchases
            orders = [
                Order(customer_id=1, total=25199.00, status="completed", shipping_address="Bahnhofstrasse 42, 8001 Zurich, Switzerland"),
                Order(customer_id=2, total=11548.00, status="processing", shipping_address="Strandvagen 15, 114 56 Stockholm, Sweden"),
                Order(customer_id=3, total=2168.98, status="pending", shipping_address="2200 NW Birdsdale Ave, Portland, OR 97210"),
                Order(customer_id=4, total=18490.00, status="shipped", shipping_address="8560 Sunset Blvd, West Hollywood, CA 90069"),
                Order(customer_id=1, total=549.00, status="completed", shipping_address="Bahnhofstrasse 42, 8001 Zurich, Switzerland"),
                Order(customer_id=5, total=4798.99, status="processing", shipping_address="Friedrichstrasse 120, 10117 Berlin, Germany"),
                Order(customer_id=7, total=10999.00, status="pending", shipping_address="1300 Pennsylvania Ave NW, Washington, DC 20004"),
                Order(customer_id=8, total=5298.00, status="shipped", shipping_address="Aker Brygge 12, 0250 Oslo, Norway"),
            ]
            session.add_all(orders)
            session.flush()

            # Order Items — referencing new drone products
            session.add_all([
                # Order 1: Alpine Aerial — WingtraOne + CUAV X7+ = 25199 (24900 + 299 for frame kit... close enough)
                OrderItem(order_id=1, product_id=4, quantity=1, unit_price=24900.00),   # WingtraOne GEN II
                OrderItem(order_id=1, product_id=9, quantity=1, unit_price=299.00),     # Holybro X500 V2 Frame
                # Order 2: Nordstrom — Skydio X10 + CUAV FC
                OrderItem(order_id=2, product_id=1, quantity=1, unit_price=10999.00),   # Skydio X10
                OrderItem(order_id=2, product_id=14, quantity=1, unit_price=549.00),    # CUAV X7+ Pro
                # Order 3: Redwood SAR — Autel EVO II + Tattu batteries + props
                OrderItem(order_id=3, product_id=3, quantity=1, unit_price=1899.00),    # Autel EVO II Pro V3
                OrderItem(order_id=3, product_id=17, quantity=1, unit_price=179.99),    # Tattu 6S battery
                OrderItem(order_id=3, product_id=20, quantity=3, unit_price=29.99),     # Silent props x3
                # Order 4: Atlantic Film — Freefly Astro + MoVI gimbal
                OrderItem(order_id=4, product_id=8, quantity=1, unit_price=12495.00),   # Freefly Astro
                OrderItem(order_id=4, product_id=15, quantity=1, unit_price=5995.00),   # MoVI Carbon Gimbal
                # Order 5: Alpine Aerial — Orqa FPV goggles (accessory order)
                OrderItem(order_id=5, product_id=14, quantity=1, unit_price=549.00),    # CUAV X7+ Pro
                # Order 6: EuroCrop — Parrot ANAFI Ai + props + backpack
                OrderItem(order_id=6, product_id=2, quantity=1, unit_price=4499.00),    # Parrot ANAFI Ai
                OrderItem(order_id=6, product_id=20, quantity=2, unit_price=29.99),     # Silent props x2
                OrderItem(order_id=6, product_id=24, quantity=1, unit_price=249.99),    # Lowepro backpack
                # Order 7: Summit PS — Skydio X10
                OrderItem(order_id=7, product_id=1, quantity=1, unit_price=10999.00),   # Skydio X10
                # Order 8: Fjord Env — Parrot ANAFI USA + field charger
                OrderItem(order_id=8, product_id=2, quantity=1, unit_price=4499.00),    # Parrot ANAFI Ai
                OrderItem(order_id=8, product_id=18, quantity=1, unit_price=799.00),    # EcoFlow DELTA Mini
            ])

            # Reviews (10) — drone product reviews
            session.add_all([
                Review(product_id=1, rating=5, comment="Skydio X10 obstacle avoidance is unreal. Flew through dense forest autonomously.", author_name="DroneOps_EU"),
                Review(product_id=1, rating=4, comment="Incredible AI but wish the battery lasted beyond 35min for survey work.", author_name="SurveyPilot"),
                Review(product_id=2, rating=5, comment="ANAFI Ai 4G link is a game changer. BVLOS missions made simple.", author_name="InspectionPro"),
                Review(product_id=3, rating=4, comment="Great value for a 6K drone. EVO II Pro handles wind better than expected.", author_name="AerialPhoto_Mike"),
                Review(product_id=6, rating=5, comment="ELIOS 3 saved us weeks on a boiler inspection. LiDAR in confined spaces is brilliant.", author_name="IndustrialNDE"),
                Review(product_id=8, rating=4, comment="Freefly Astro carries our RED Komodo perfectly. Modular design is well thought out.", author_name="CineDronePilot"),
                Review(product_id=11, rating=5, comment="KDE motors are workhorses. 500+ hours on our hexacopter fleet, zero failures.", author_name="FleetManager_CH"),
                Review(product_id=4, rating=5, comment="WingtraOne accuracy is incredible — 1cm GSD with the 42MP sensor.", author_name="GeoSurvey_DE"),
                Review(product_id=19, rating=4, comment="KDE carbon props are well-balanced. Noticeably smoother than our old plastic set.", author_name="HeavyLiftOps"),
                Review(product_id=21, rating=5, comment="Orqa goggles have the best optics in FPV. Crystal clear OLED. Worth every cent.", author_name="FPV_Racer_EU"),
            ])

            # Coupons (5) — drone shop promotions
            session.add_all([
                Coupon(code="FIRSTFLIGHT", discount_percent=10.0, is_active=1, max_uses=1000),
                Coupon(code="FLEETDEAL", discount_percent=15.0, is_active=1, max_uses=200),
                Coupon(code="FREESHIP", discount_amount=49.99, is_active=1, max_uses=100),
                Coupon(code="GOVPILOT", discount_percent=20.0, is_active=1, max_uses=50),
                Coupon(code="SUMMER2024", discount_percent=12.0, is_active=0, max_uses=0),
            ])

            # Shipments (8) — drone shipments with realistic weights
            session.add_all([
                Shipment(order_id=1, tracking_number="DHL-OCTO-001", carrier="dhl", status="delivered",
                         origin_region="eu-central-1", destination_region="eu-central-1", weight_kg=8.5, shipping_cost=89.99),
                Shipment(order_id=2, tracking_number="FDX-OCTO-001", carrier="fedex", status="in_transit",
                         origin_region="us-west-2", destination_region="eu-north-1", weight_kg=6.2, shipping_cost=149.99),
                Shipment(order_id=3, tracking_number="UPS-OCTO-001", carrier="ups", status="processing",
                         origin_region="us-west-2", destination_region="us-west-2", weight_kg=3.8, shipping_cost=29.99),
                Shipment(order_id=4, tracking_number="FDX-OCTO-002", carrier="fedex", status="shipped",
                         origin_region="us-west-2", destination_region="us-west-2", weight_kg=12.5, shipping_cost=79.99),
                Shipment(order_id=5, tracking_number="DHL-OCTO-002", carrier="dhl", status="delivered",
                         origin_region="eu-central-1", destination_region="eu-central-1", weight_kg=1.2, shipping_cost=19.99),
                Shipment(order_id=6, tracking_number="DHL-OCTO-003", carrier="dhl", status="in_transit",
                         origin_region="eu-central-1", destination_region="eu-central-1", weight_kg=4.5, shipping_cost=49.99),
                Shipment(order_id=7, tracking_number="FDX-OCTO-003", carrier="fedex", status="processing",
                         origin_region="us-west-2", destination_region="us-east-1", weight_kg=7.0, shipping_cost=59.99),
                Shipment(order_id=8, tracking_number="DHL-OCTO-004", carrier="dhl", status="shipped",
                         origin_region="eu-central-1", destination_region="eu-north-1", weight_kg=5.8, shipping_cost=69.99),
            ])

            # Warehouses (5) — drone fulfillment centers
            session.add_all([
                Warehouse(name="Portland Drone Hub", region="us-west-2", address="2100 NW Industrial Way, Portland, OR 97210",
                          capacity=5000, current_stock=2800, is_active=1),
                Warehouse(name="Frankfurt EU Fulfillment", region="eu-central-1", address="Lagerstrasse 45, 60327 Frankfurt, Germany",
                          capacity=3500, current_stock=1900, is_active=1),
                Warehouse(name="Zurich Precision Center", region="eu-central-1", address="Industriestrasse 12, 8304 Wallisellen, Switzerland",
                          capacity=1500, current_stock=650, is_active=1),
                Warehouse(name="Virginia East Coast DC", region="us-east-1", address="800 Commerce Park Dr, Chantilly, VA 20151",
                          capacity=4000, current_stock=2200, is_active=1),
                Warehouse(name="Toulouse Aerospace Depot", region="eu-west-3", address="31 Avenue des Drones, 31400 Toulouse, France",
                          capacity=2000, current_stock=1100, is_active=1),
            ])

            # Campaigns (5) — drone industry marketing
            session.add_all([
                Campaign(name="Enterprise Fleet Launch", campaign_type="email", status="completed",
                         budget=45000, spent=43200, target_audience="Enterprise fleet managers"),
                Campaign(name="EU Drone Regulation Guide", campaign_type="social", status="active",
                         budget=18000, spent=7500, target_audience="EU commercial pilots"),
                Campaign(name="Survey Pro Webinar Series", campaign_type="ppc", status="active",
                         budget=12000, spent=5100, target_audience="Surveying & mapping professionals"),
                Campaign(name="Public Safety Partner Program", campaign_type="referral", status="active",
                         budget=60000, spent=22000, target_audience="Government & public safety"),
                Campaign(name="FPV Racing Season Kickoff", campaign_type="social", status="active",
                         budget=8000, spent=3200, target_audience="FPV racing community"),
            ])
            session.flush()

            # Leads (8) — drone industry prospects
            session.add_all([
                Lead(campaign_id=1, email="ops@terrasurvey.com", name="Lars Eriksson", source="web", status="converted", score=92),
                Lead(campaign_id=1, email="fleet@windpower.dk", name="Mette Hansen", source="referral", status="qualified", score=78),
                Lead(campaign_id=2, email="piloting@agridrone.fr", name="Pierre Dubois", source="social", status="contacted", score=65),
                Lead(campaign_id=2, email="tech@aerialinspect.de", name="Klaus Weber", source="paid", status="new", score=40),
                Lead(campaign_id=3, email="gis@mapsolutions.com", name="Sarah Mitchell", source="web", status="qualified", score=85),
                Lead(campaign_id=4, email="procurement@county-rescue.gov", name="James O'Brien", source="referral", status="converted", score=95),
                Lead(campaign_id=5, email="builds@fpvfreestyle.eu", name="Marco Rossi", source="web", status="new", score=55),
                Lead(campaign_id=5, email="racing@quadleague.com", name="Emma Johansson", source="social", status="contacted", score=70),
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
