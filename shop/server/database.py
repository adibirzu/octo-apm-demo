"""Database engine, session, models, and initialization (PostgreSQL or Oracle ATP)."""

import logging
import os
from contextlib import asynccontextmanager

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Identity, create_engine, text, inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func

from server.config import cfg
from server.storefront import ADDITIONAL_PRODUCTS

logger = logging.getLogger(__name__)

Base = declarative_base()

SEED_USER_EMAIL_DOMAIN = os.getenv("SEED_USER_EMAIL_DOMAIN", "example.invalid")
SEED_PAGEVIEW_IP_PREFIX = os.getenv("SEED_PAGEVIEW_IP_PREFIX", "198.18.0.")


def _seed_email(username: str) -> str:
    return f"{username}@{SEED_USER_EMAIL_DOMAIN}"


def _seed_ip(octet: int) -> str:
    safe_octet = max(1, min(int(octet), 254))
    return f"{SEED_PAGEVIEW_IP_PREFIX}{safe_octet}"

DRONE_CATALOG_PRODUCTS = [
    {
        "name": "Skydio X10",
        "sku": "DRN-001",
        "description": "AI-powered autonomous drone with 6 cameras, 35min flight time. Obstacle avoidance in all directions. Made in USA.",
        "price": 10999.00,
        "stock": 25,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_001.jpg",
    },
    {
        "name": "Parrot ANAFI Ai",
        "sku": "DRN-002",
        "description": "4G-connected robotic drone, 4K HDR camera, 32min flight. Defense-grade platform. Made in France.",
        "price": 4499.00,
        "stock": 40,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_002.jpg",
    },
    {
        "name": "Autel EVO II Pro V3",
        "sku": "DRN-003",
        "description": "6K camera, 42min flight time, 9km range. 1-inch CMOS sensor. Designed in USA.",
        "price": 1899.00,
        "stock": 60,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_003.jpg",
    },
    {
        "name": "Wingtra WingtraOne GEN II",
        "sku": "DRN-004",
        "description": "VTOL survey drone, 59min endurance, 42MP sensor. Survey-grade accuracy. Made in Switzerland.",
        "price": 24900.00,
        "stock": 8,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_004.jpg",
    },
    {
        "name": "Quantum-Systems Trinity F90+",
        "sku": "DRN-005",
        "description": "Fixed-wing VTOL mapping drone, 90min flight, PPK/RTK. Made in Germany.",
        "price": 28500.00,
        "stock": 6,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_005.jpg",
    },
    {
        "name": "Flyability ELIOS 3",
        "sku": "DRN-006",
        "description": "Caged inspection drone for confined spaces, LiDAR + 4K camera. Made in Switzerland.",
        "price": 39900.00,
        "stock": 4,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_006.jpg",
    },
    {
        "name": "Parrot ANAFI USA",
        "sku": "DRN-007",
        "description": "Secure drone with 32x zoom, FLIR thermal, no data connection to external servers. Made in France.",
        "price": 7499.00,
        "stock": 15,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_007.jpg",
    },
    {
        "name": "Freefly Astro",
        "sku": "DRN-008",
        "description": "Modular cinema drone, 8kg payload, interchangeable camera mounts. Made in USA.",
        "price": 12495.00,
        "stock": 10,
        "category": "Complete Drones",
        "image_url": "/static/img/products/drn_008.jpg",
    },
    {
        "name": "Holybro X500 V2 Frame Kit",
        "sku": "FRM-001",
        "description": "500mm quadcopter frame, ARF kit with Pixhawk 6C autopilot. Designed in USA.",
        "price": 299.00,
        "stock": 120,
        "category": "Frames",
        "image_url": "/static/img/products/frm_001.jpg",
    },
    {
        "name": "IFlight Chimera7 Pro Frame",
        "sku": "FRM-002",
        "description": "7-inch long-range frame, full carbon fiber, HD compatible. Designed in USA.",
        "price": 89.99,
        "stock": 200,
        "category": "Frames",
        "image_url": "/static/img/products/frm_002.jpg",
    },
    {
        "name": "KDE Direct 4215XF-465 Motor",
        "sku": "MOT-001",
        "description": "High-performance brushless motor, 465KV, UAS-grade reliability. Made in USA.",
        "price": 189.99,
        "stock": 150,
        "category": "Motors & ESCs",
        "image_url": "/static/img/products/mot_001.jpg",
    },
    {
        "name": "Holybro Tekko32 F4 4-in-1 ESC",
        "sku": "ESC-001",
        "description": "4x50A ESC, BLHeli_32, DShot1200. Current sensor built-in.",
        "price": 69.99,
        "stock": 180,
        "category": "Motors & ESCs",
        "image_url": "/static/img/products/esc_001.jpg",
    },
    {
        "name": "Holybro Pixhawk 6X",
        "sku": "FLC-001",
        "description": "Open-source autopilot, STM32H7, triple IMU, industrial-grade. FMUv6X standard.",
        "price": 399.99,
        "stock": 75,
        "category": "Flight Controllers",
        "image_url": "/static/img/products/flc_001.jpg",
    },
    {
        "name": "CUAV X7+ Pro",
        "sku": "FLC-002",
        "description": "Industrial autopilot, triple redundant IMU, CAN bus, vibration isolation. Designed in USA.",
        "price": 549.00,
        "stock": 45,
        "category": "Flight Controllers",
        "image_url": "/static/img/products/flc_002.jpg",
    },
    {
        "name": "Freefly MoVI Carbon Gimbal",
        "sku": "GMB-001",
        "description": "3-axis cinema gimbal, 15lb payload, Freefly MIMIC control. Made in USA.",
        "price": 5995.00,
        "stock": 12,
        "category": "Cameras & Gimbals",
        "image_url": "/static/img/products/gmb_001.jpg",
    },
    {
        "name": "Phase One P3 Payload",
        "sku": "CAM-001",
        "description": "100MP metric camera for aerial survey, iXM-RS150F lens. Made in Denmark.",
        "price": 52000.00,
        "stock": 3,
        "category": "Cameras & Gimbals",
        "image_url": "/static/img/products/cam_001.jpg",
    },
    {
        "name": "Tattu 6S 10000mAh LiPo",
        "sku": "BAT-001",
        "description": "22.2V 25C high-capacity battery, XT60 connector. 6S for heavy-lift platforms.",
        "price": 179.99,
        "stock": 250,
        "category": "Batteries",
        "image_url": "/static/img/products/bat_001.jpg",
    },
    {
        "name": "EcoFlow DELTA Mini",
        "sku": "BAT-002",
        "description": "882Wh portable power station for field charging. 1400W output. Designed in USA.",
        "price": 799.00,
        "stock": 30,
        "category": "Batteries",
        "image_url": "/static/img/products/bat_002.jpg",
    },
    {
        "name": "KDE Direct CF 15.5x5.3 Props (pair)",
        "sku": "PRP-001",
        "description": "Carbon fiber propellers, precision-balanced, UAS multi-rotor. Made in USA.",
        "price": 89.99,
        "stock": 300,
        "category": "Propellers",
        "image_url": "/static/img/products/prp_001.jpg",
    },
    {
        "name": "Master Airscrew 13x4.5 Silent (set of 4)",
        "sku": "PRP-002",
        "description": "Low-noise propellers, optimized blade geometry. Designed in USA.",
        "price": 29.99,
        "stock": 500,
        "category": "Propellers",
        "image_url": "/static/img/products/prp_002.jpg",
    },
    {
        "name": "Orqa FPV.One Pilot Goggles",
        "sku": "FPV-001",
        "description": "OLED FPV goggles, 44-degree FOV, micro HDMI input. Made in Croatia (EU).",
        "price": 549.00,
        "stock": 50,
        "category": "FPV Gear",
        "image_url": "/static/img/products/fpv_001.jpg",
    },
    {
        "name": "TBS Crossfire Nano TX",
        "sku": "FPV-002",
        "description": "Long-range RC link module, 868/915MHz, up to 40km range. Designed in Switzerland.",
        "price": 69.99,
        "stock": 100,
        "category": "FPV Gear",
        "image_url": "/static/img/products/fpv_002.jpg",
    },
    {
        "name": "Hoodman Drone Launch Pad (5ft)",
        "sku": "ACC-001",
        "description": "Weighted 5-foot landing pad, high-vis orange. Folds to 24in. Made in USA.",
        "price": 89.99,
        "stock": 200,
        "category": "Accessories",
        "image_url": "/static/img/products/acc_001.jpg",
    },
    {
        "name": "Lowepro DroneGuard BP 450 AW",
        "sku": "ACC-002",
        "description": "Drone backpack, fits large quads + accessories, all-weather cover. Designed in USA.",
        "price": 249.99,
        "stock": 80,
        "category": "Accessories",
        "image_url": "/static/img/products/acc_002.jpg",
    },
]

LEGACY_MUSHOP_SKUS = {
    "TEE-001",
    "HOD-001",
    "SOC-001",
    "CAP-001",
    "STK-001",
    "MUG-001",
    "MUG-002",
    "BAG-001",
    "NTB-001",
    "PLH-001",
    "PST-001",
    "LAN-001",
}

SEED_PRODUCTS = [*DRONE_CATALOG_PRODUCTS, *ADDITIONAL_PRODUCTS]

SEED_SERVICES = [
    {
        "name": "Annual Fleet Maintenance",
        "sku": "SRV-001",
        "description": "Comprehensive 100-point inspection and preventative maintenance for enterprise drone fleets.",
        "price": 2500.00,
        "category": "Maintenance",
        "image_url": "",
    },
    {
        "name": "Lidar Calibration & Alignment",
        "sku": "SRV-002",
        "description": "High-precision calibration for Zenmuse and Phase One Lidar payloads.",
        "price": 850.00,
        "category": "Calibration",
        "image_url": "",
    },
    {
        "name": "Advanced Pilot Training (BVLOS)",
        "sku": "SRV-003",
        "description": "5-day immersive tactical and BVLOS flight training course.",
        "price": 4500.00,
        "category": "Training",
        "image_url": "",
    },
    {
        "name": "Emergency Repair Diagnostic",
        "sku": "SRV-004",
        "description": "24-hour turnaround diagnostic service for grounded aircraft.",
        "price": 300.00,
        "category": "Maintenance",
        "image_url": "",
    },
]

SEED_USERS = [
    {
        "username": "admin",
        "email": _seed_email("admin"),
        "password_hash": "$2b$12$stDMKhq3T8ZSu.c.JV/AuuhFkvdoLMWTZeY/wzArJl1fzv2thZ7ZW",
        "role": "admin",
    },
    {
        "username": "shopper",
        "email": _seed_email("shopper"),
        "password_hash": "$2b$12$xHlGrfFw.WcVjkJRR2cFUuP2WgKqA90AcaBPwwm3ccPBNZmE76gx6",
        "role": "user",
    },
    {
        "username": "manager",
        "email": _seed_email("manager"),
        "password_hash": "$2b$12$xHlGrfFw.WcVjkJRR2cFUuP2WgKqA90AcaBPwwm3ccPBNZmE76gx6",
        "role": "manager",
    },
    {
        "username": "analyst",
        "email": _seed_email("analyst"),
        "password_hash": "$2b$12$xHlGrfFw.WcVjkJRR2cFUuP2WgKqA90AcaBPwwm3ccPBNZmE76gx6",
        "role": "analyst",
    },
    {
        "username": "support",
        "email": _seed_email("support"),
        "password_hash": "$2b$12$xHlGrfFw.WcVjkJRR2cFUuP2WgKqA90AcaBPwwm3ccPBNZmE76gx6",
        "role": "support",
    },
]

# ── Engine creation ──────────────────────────────────────────────

_engine_kwargs = {
    "echo": False,
    "pool_size": 5,
    "max_overflow": 10,
    "pool_pre_ping": True,
}

if cfg.use_postgres:
    logger.info("Using PostgreSQL backend: %s", cfg.masked_database_url())
    engine = create_async_engine(cfg.database_url, **_engine_kwargs)
    sync_engine = create_engine(cfg.sync_database_url)
else:
    try:
        import oracledb
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Oracle ATP mode requires 'oracledb' package. "
            "Set DATABASE_URL for PostgreSQL or install oracledb."
        ) from exc

    oracledb.defaults.config_dir = cfg.oracle_wallet_dir or ""
    oracledb.defaults.fetch_lobs = False

    _connect_args = {}
    if cfg.oracle_wallet_dir:
        _connect_args["config_dir"] = cfg.oracle_wallet_dir
        _connect_args["wallet_location"] = cfg.oracle_wallet_dir
        _connect_args["wallet_password"] = cfg.oracle_wallet_password

    engine = create_async_engine(
        cfg.database_url,
        connect_args={"dsn": cfg.oracle_dsn, **_connect_args},
        **_engine_kwargs,
    )
    _sync_url = f"oracle+oracledb://{cfg.oracle_user}:{cfg.oracle_password}@"
    sync_engine = create_engine(_sync_url, connect_args={"dsn": cfg.oracle_dsn, **_connect_args})

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Tag Oracle sessions with MODULE/ACTION/CLIENT_IDENTIFIER for OPSI + DB Management correlation
try:
    from server.observability.db_session_tagging import register_session_tagging
    register_session_tagging(engine)
    register_session_tagging(sync_engine)
except Exception:
    logger.debug("DB session tagging registration deferred", exc_info=True)


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
    payment_method = Column(String(50), default="credit_card")
    payment_status = Column(String(50), default="pending")
    payment_provider = Column(String(50), nullable=True)
    payment_provider_reference = Column(String(128), nullable=True, index=True)
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


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, Identity(always=False), primary_key=True)
    invoice_number = Column(String(100), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    status = Column(String(50), default="draft")
    issued_at = Column(DateTime, server_default=func.now())
    due_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    customer = relationship("Customer")
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


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    category = Column(String(100))
    image_url = Column(String(500))
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, Identity(always=False), primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    title = Column(String(200), nullable=False)
    status = Column(String(50), default="open")
    priority = Column(String(50), default="medium")
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    customer = relationship("Customer")
    product = relationship("Product")
    service = relationship("Service")


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id = Column(Integer, Identity(always=False), primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"))
    sender_type = Column(String(50), nullable=False)  # 'customer' or 'agent'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    ticket = relationship("Ticket")


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


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id = Column(Integer, Identity(always=False), primary_key=True)
    attack_type = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False, default="medium")
    endpoint = Column(String(255))
    source_ip = Column(String(64))
    payload = Column(Text)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    session_id = Column(String(64))
    trace_id = Column(String(64))
    details = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    product = relationship("Product")


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"
    id = Column(Integer, Identity(always=False), primary_key=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    customer_email = Column(String(200))
    product_focus = Column(String(200))
    source = Column(String(50), default="shop")
    created_at = Column(DateTime, server_default=func.now())


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    id = Column(Integer, Identity(always=False), primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    provider = Column(String(100), default="local")
    model_id = Column(String(255))
    trace_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id = Column(Integer, Identity(always=False), primary_key=True)
    workflow_key = Column(String(100), nullable=False, index=True)
    workflow_label = Column(String(200))
    source_service = Column(String(100), nullable=False)
    schedule_mode = Column(String(30), default="scheduled")
    status = Column(String(30), default="pending")
    result_summary = Column(Text)
    trace_id = Column(String(64))
    duration_ms = Column(Float, default=0.0)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)


class QueryExecution(Base):
    __tablename__ = "query_executions"
    id = Column(Integer, Identity(always=False), primary_key=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=True)
    query_name = Column(String(120), nullable=False, index=True)
    component_name = Column(String(120))
    source_service = Column(String(100), nullable=False)
    schedule_mode = Column(String(30), default="manual")
    action_name = Column(String(50), default="query")
    status = Column(String(30), default="pending")
    expected_failure = Column(Integer, default=0)
    query_text = Column(Text, nullable=False)
    prompt_text = Column(Text)
    row_count = Column(Integer, default=0)
    duration_ms = Column(Float, default=0.0)
    error_message = Column(Text)
    trace_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())
    workflow_run = relationship("WorkflowRun")


class ComponentSnapshot(Base):
    __tablename__ = "component_snapshots"
    id = Column(Integer, Identity(always=False), primary_key=True)
    component_name = Column(String(120), nullable=False, index=True)
    component_type = Column(String(60), nullable=False)
    status = Column(String(30), default="unknown")
    source_service = Column(String(100), nullable=False)
    latency_ms = Column(Float, default=0.0)
    details = Column(Text)
    trace_id = Column(String(64))
    observed_at = Column(DateTime, server_default=func.now())


# ── Database Initialization ──────────────────────────────────────

def init_tables():
    """Create all tables and seed if needed."""
    if sync_engine is None:
        logger.warning("No sync engine — skipping table creation")
        return
    try:
        insp = inspect(sync_engine)
        existing_tables = insp.get_table_names()

        if "users" in existing_tables and not cfg.use_postgres:
            # Oracle-specific: check if tables need Identity column fix
            from sqlalchemy.orm import Session
            with Session(sync_engine) as session:
                count = session.execute(text("SELECT COUNT(*) FROM users")).scalar()
                if count == 0:
                    logger.info("Oracle tables exist but are empty — dropping for Identity column fix")
                    Base.metadata.drop_all(sync_engine)

        Base.metadata.create_all(sync_engine, checkfirst=True)
        _ensure_missing_columns(sync_engine)
        backend = "postgresql" if cfg.use_postgres else "oracle_atp"
        logger.info("Database tables created/verified (backend: %s)", backend)
    except Exception as e:
        logger.error("Failed to create tables: %s", e)
        raise


def _ensure_missing_columns(engine) -> None:
    """Add columns that were introduced after initial table creation."""
    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    if "products" not in table_names:
        return
    existing = {col["name"] for col in insp.get_columns("products")}
    dialect = engine.dialect.name
    migrations = {
        "image_url": "VARCHAR2(500 CHAR)" if dialect == "oracle" else "VARCHAR(500)",
    }
    with engine.begin() as conn:
        for col_name, col_type in migrations.items():
            if col_name not in existing:
                stmt = (
                    f"ALTER TABLE products ADD ({col_name} {col_type})"
                    if dialect == "oracle"
                    else f"ALTER TABLE products ADD COLUMN {col_name} {col_type}"
                )
                conn.execute(text(stmt))
                logger.info("Added missing column products.%s", col_name)

    # Orders table migrations
    if "orders" in insp.get_table_names():
        order_cols = {col["name"] for col in insp.get_columns("orders")}
        order_migrations = {
            "payment_method": "VARCHAR2(50 CHAR)" if dialect == "oracle" else "VARCHAR(50)",
            "payment_status": "VARCHAR2(50 CHAR)" if dialect == "oracle" else "VARCHAR(50)",
        }
        for col_name, col_type in order_migrations.items():
            if col_name not in order_cols:
                try:
                    with engine.begin() as conn:
                        stmt = (
                            f"ALTER TABLE orders ADD ({col_name} {col_type})"
                            if dialect == "oracle"
                            else f"ALTER TABLE orders ADD COLUMN {col_name} {col_type}"
                        )
                        conn.execute(text(stmt))
                        logger.info("Added missing column orders.%s", col_name)
                except Exception:
                    logger.debug("Column orders.%s may already exist (concurrent DDL)", col_name)

    if "invoices" in table_names:
        invoice_cols = {col["name"] for col in insp.get_columns("invoices")}
        invoice_migrations = {
            "customer_id": "NUMBER" if dialect == "oracle" else "INTEGER",
            "currency": "VARCHAR2(10 CHAR) DEFAULT 'USD'" if dialect == "oracle" else "VARCHAR(10) DEFAULT 'USD'",
            "issued_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if dialect == "oracle" else "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "due_at": "TIMESTAMP",
            "paid_at": "TIMESTAMP",
            "notes": "CLOB" if dialect == "oracle" else "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if dialect == "oracle" else "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        for col_name, col_type in invoice_migrations.items():
            if col_name not in invoice_cols:
                try:
                    with engine.begin() as conn:
                        stmt = (
                            f"ALTER TABLE invoices ADD ({col_name} {col_type})"
                            if dialect == "oracle"
                            else f"ALTER TABLE invoices ADD COLUMN {col_name} {col_type}"
                        )
                        conn.execute(text(stmt))
                        logger.info("Added missing column invoices.%s", col_name)
                except Exception:
                    logger.debug("Column invoices.%s may already exist (concurrent DDL)", col_name)

        with engine.begin() as conn:
            if "customer_id" not in invoice_cols:
                conn.execute(
                    text(
                        "UPDATE invoices i SET customer_id = ("
                        "SELECT o.customer_id FROM orders o WHERE o.id = i.order_id"
                        ") WHERE i.customer_id IS NULL"
                    )
                )
            if "currency" not in invoice_cols:
                conn.execute(text("UPDATE invoices SET currency = 'USD' WHERE currency IS NULL"))
            if "issued_at" not in invoice_cols:
                conn.execute(text("UPDATE invoices SET issued_at = created_at WHERE issued_at IS NULL"))
            if "updated_at" not in invoice_cols:
                conn.execute(text("UPDATE invoices SET updated_at = created_at WHERE updated_at IS NULL"))
            if "due_at" not in invoice_cols and "due_date" in invoice_cols:
                conn.execute(text("UPDATE invoices SET due_at = due_date WHERE due_at IS NULL"))

    # Ensure 'shops' table exists (not in ORM, needed for /api/shop/locations)
    if "shops" not in insp.get_table_names():
        ddl = (
            "CREATE TABLE shops ("
            "id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "
            "name VARCHAR2(200 CHAR) NOT NULL, "
            "address CLOB NOT NULL, "
            "coordinates VARCHAR2(100 CHAR), "
            "contact_email VARCHAR2(200 CHAR), "
            "contact_phone VARCHAR2(50 CHAR), "
            "is_active NUMBER(1) DEFAULT 1, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            if dialect == "oracle"
            else
            "CREATE TABLE shops ("
            "id SERIAL PRIMARY KEY, "
            "name VARCHAR(200) NOT NULL, "
            "address TEXT NOT NULL, "
            "coordinates VARCHAR(100), "
            "contact_email VARCHAR(200), "
            "contact_phone VARCHAR(50), "
            "is_active INTEGER DEFAULT 1, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        with engine.begin() as conn:
            conn.execute(text(ddl))
            logger.info("Created missing 'shops' table")


def _reconcile_product_catalog(session) -> None:
    desired_by_sku = {product["sku"]: product for product in SEED_PRODUCTS}
    existing_products = {product.sku: product for product in session.query(Product).all()}

    for sku, payload in desired_by_sku.items():
        existing = existing_products.get(sku)
        if existing is None:
            try:
                nested = session.begin_nested()
                session.add(Product(**payload))
                nested.commit()
            except Exception:
                # Another replica likely inserted it — fetch and update instead
                existing = session.query(Product).filter_by(sku=sku).first()
                if not existing:
                    continue
            else:
                continue

        existing.name = payload["name"]
        existing.description = payload["description"]
        existing.price = payload["price"]
        existing.stock = payload["stock"]
        existing.category = payload["category"]
        existing.image_url = payload.get("image_url")
        existing.is_active = 1

    session.query(Product).filter(Product.sku.in_(LEGACY_MUSHOP_SKUS)).update(
        {Product.is_active: 0},
        synchronize_session=False,
    )


def _reconcile_services(session) -> None:
    desired_by_sku = {svc["sku"]: svc for svc in SEED_SERVICES}
    existing_services = {svc.sku: svc for svc in session.query(Service).all()}

    for sku, payload in desired_by_sku.items():
        existing = existing_services.get(sku)
        if existing is None:
            try:
                nested = session.begin_nested()
                session.add(Service(**payload))
                nested.commit()
            except Exception:
                existing = session.query(Service).filter_by(sku=sku).first()
                if not existing:
                    continue
            else:
                continue

        existing.name = payload["name"]
        existing.description = payload["description"]
        existing.price = payload["price"]
        existing.category = payload["category"]
        existing.is_active = 1


def _reconcile_invoices(session) -> None:
    if session.query(Invoice).count() > 0 or session.query(Order).count() == 0:
        return

    session.add_all([
        Invoice(invoice_number="INV-OCTO-1001", customer_id=1, order_id=1, amount=25199.00,
                currency="USD", status="paid", notes="Settled after delivery."),
        Invoice(invoice_number="INV-OCTO-1002", customer_id=2, order_id=2, amount=11548.00,
                currency="USD", status="issued", notes="Awaiting wire settlement."),
        Invoice(invoice_number="INV-OCTO-1003", customer_id=5, order_id=6, amount=4798.99,
                currency="USD", status="overdue", notes="Collections follow-up queued."),
    ])


def _reconcile_seed_users(session) -> None:
    desired_by_username = {user["username"]: user for user in SEED_USERS}
    existing_users = {user.username: user for user in session.query(User).all()}

    for username, payload in desired_by_username.items():
        existing = existing_users.get(username)
        if existing is None:
            try:
                nested = session.begin_nested()
                session.add(User(**payload))
                nested.commit()
            except Exception:
                existing = session.query(User).filter_by(username=username).first()
                if not existing:
                    continue
            else:
                continue

        existing.email = payload["email"]
        existing.password_hash = payload["password_hash"]
        existing.role = payload["role"]
        existing.is_active = 1


def seed_data():
    """Insert seed data if tables are empty."""
    if sync_engine is None:
        return
    from sqlalchemy.orm import Session
    try:
        with Session(sync_engine) as session:
            if session.query(User).count() > 0:
                _reconcile_seed_users(session)
                _reconcile_product_catalog(session)
                _reconcile_services(session)
                _reconcile_invoices(session)
                session.commit()
                logger.info("Database already seeded — reconciled users, catalog, services, and invoices")
                return

            # Users
            session.add_all(User(**user) for user in SEED_USERS)
            session.flush()

            session.add_all(Product(**product) for product in SEED_PRODUCTS)
            session.flush()

            session.add_all(Service(**service) for service in SEED_SERVICES)
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

            tickets = [
                Ticket(customer_id=1, title='Aegis Quadcopter Gimbal Drift', status='open', priority='high', product_id=1, service_id=None),
                Ticket(customer_id=2, title='Inquiry: Advanced Pilot Training Availability', status='open', priority='medium', product_id=None, service_id=3),
                Ticket(customer_id=4, title='Hercules HL-600 Motor Grinding Noise', status='in_progress', priority='high', product_id=2, service_id=4),
            ]
            session.add_all(tickets)
            session.flush()

            ticket_messages = [
                TicketMessage(ticket_id=1, sender_type='customer', content='The thermal payload on our Aegis drone is slowly drifting downwards during sustained flight.'),
                TicketMessage(ticket_id=1, sender_type='agent', content='We have received your report. Can you verify if the firmware was updated to v2.4.1 before the flight?'),
                TicketMessage(ticket_id=2, sender_type='customer', content='When is the next BVLOS training course scheduled in the EU?'),
                TicketMessage(ticket_id=3, sender_type='customer', content='Motor 4 on the Hercules is making a grinding noise at high RPMs.'),
                TicketMessage(ticket_id=3, sender_type='agent', content='Please ground the aircraft immediately. We are dispatching a replacement motor via overnight shipping.'),
            ]
            session.add_all(ticket_messages)
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

            session.add_all([
                Invoice(invoice_number="INV-OCTO-1001", customer_id=1, order_id=1, amount=25199.00,
                        currency="USD", status="paid", notes="Settled after delivery."),
                Invoice(invoice_number="INV-OCTO-1002", customer_id=2, order_id=2, amount=11548.00,
                        currency="USD", status="issued", notes="Awaiting wire settlement."),
                Invoice(invoice_number="INV-OCTO-1003", customer_id=5, order_id=6, amount=4798.99,
                        currency="USD", status="overdue", notes="Collections follow-up queued."),
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
                PageView(page="/shop", visitor_ip=_seed_ip(11), visitor_region="eu-central-1", load_time_ms=95, session_id="sess-001"),
                PageView(page="/catalogue", visitor_ip=_seed_ip(11), visitor_region="eu-central-1", load_time_ms=110, session_id="sess-001"),
                PageView(page="/shop", visitor_ip=_seed_ip(21), visitor_region="us-east-1", load_time_ms=180, session_id="sess-002"),
                PageView(page="/shop", visitor_ip=_seed_ip(31), visitor_region="ap-northeast-1", load_time_ms=420, session_id="sess-003"),
                PageView(page="/orders", visitor_ip=_seed_ip(31), visitor_region="ap-northeast-1", load_time_ms=380, session_id="sess-003"),
                PageView(page="/shop", visitor_ip=_seed_ip(41), visitor_region="us-west-2", load_time_ms=200, session_id="sess-004"),
                PageView(page="/analytics", visitor_ip=_seed_ip(51), visitor_region="ap-southeast-1", load_time_ms=510, session_id="sess-005"),
                PageView(page="/shop", visitor_ip=_seed_ip(61), visitor_region="sa-east-1", load_time_ms=650, session_id="sess-006"),
                PageView(page="/catalogue", visitor_ip=_seed_ip(71), visitor_region="af-south-1", load_time_ms=870, session_id="sess-007"),
                PageView(page="/shop", visitor_ip=_seed_ip(12), visitor_region="eu-central-1", load_time_ms=88, session_id="sess-008"),
                PageView(page="/admin-page", visitor_ip=_seed_ip(81), visitor_region="me-south-1", load_time_ms=350, session_id="sess-009"),
                PageView(page="/login", visitor_ip=_seed_ip(91), visitor_region="us-east-1", load_time_ms=95, session_id="sess-010"),
                PageView(page="/shop", visitor_ip=_seed_ip(101), visitor_region="eu-west-1", load_time_ms=130, session_id="sess-011"),
                PageView(page="/catalogue", visitor_ip=_seed_ip(111), visitor_region="us-west-2", load_time_ms=160, session_id="sess-012"),
                PageView(page="/orders", visitor_ip=_seed_ip(121), visitor_region="ap-southeast-2", load_time_ms=440, session_id="sess-013"),
            ])

            # Audit Logs (5)
            session.add_all([
                AuditLog(user_id=1, action="login", resource="auth", details="Admin login from seeded network sample"),
                AuditLog(user_id=2, action="view_products", resource="catalogue", details="Viewed product list"),
                AuditLog(user_id=1, action="view_config_summary", resource="admin", details="Viewed sanitized app config summary"),
                AuditLog(user_id=3, action="create_order", resource="orders", details="Order #1 created"),
                AuditLog(user_id=1, action="view_audit_logs", resource="admin", details="Viewed audit trail"),
            ])

            # Seed shops table (raw SQL — no ORM model)
            try:
                shop_count = session.execute(text("SELECT COUNT(*) FROM shops")).scalar()
                if shop_count == 0:
                    session.execute(text(
                        "INSERT INTO shops (name, address, coordinates, contact_email, contact_phone) VALUES "
                        "('OCTO Drone Shop - Flagship', '100 Cloud Way, Silicon Valley, CA', '37.3875,-122.0575', 'store.sv@octodrones.com', '+1-555-0810')"
                    ))
                    session.execute(text(
                        "INSERT INTO shops (name, address, coordinates, contact_email, contact_phone) VALUES "
                        "('OCTO Defense Systems - East', '50 Defense Blvd, Arlington, VA', '38.8816,-77.0910', 'tactical@octodrones.com', '+1-555-0820')"
                    ))
                    session.execute(text(
                        "INSERT INTO shops (name, address, coordinates, contact_email, contact_phone) VALUES "
                        "('OCTO Industrial - EU', '15 Industrialweg, Frankfurt, Germany', '50.1109,8.6821', 'eu.sales@octodrones.com', '+49-69-555-0830')"
                    ))
            except Exception:
                logger.warning("shops table not yet available for seeding")

            session.commit()
            logger.info("Database seeded with initial data")

    except Exception as e:
        logger.error("Failed to seed database: %s", e)
        raise
