"""Schema bootstrap and demo seed data for OKE/ATP deployments."""

from __future__ import annotations

from datetime import datetime, timedelta

from passlib.hash import bcrypt
from sqlalchemy import inspect, select, text

from server.database import (
    AuditLog,
    Base,
    Campaign,
    Customer,
    Invoice,
    Lead,
    Order,
    OrderItem,
    OrderSyncAudit,
    Product,
    Shipment,
    SupportTicket,
    User,
    Warehouse,
    engine,
)


async def bootstrap_database() -> None:
    """Create tables and seed a compact demo dataset."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_order_columns)
        await conn.run_sync(_ensure_product_columns)

    from server.database import async_session_factory

    _DEMO_USERS = {
        "admin": ("admin123", "admin", "admin@crm-enterprise.local"),
        "user1": ("password1", "user", "user1@crm-enterprise.local"),
        "manager": ("password1", "manager", "manager@crm-enterprise.local"),
        "viewer": ("viewer123", "viewer", "viewer@crm-enterprise.local"),
    }

    from server.database import async_session_factory

    async with async_session_factory() as session:
        existing_user = await session.scalar(select(User.id).limit(1))
        if existing_user:
            # Reconcile CRM demo users — upsert by email (not username) to avoid
            # overwriting Shop's users in the shared ATP database.
            for username, (password, role, email) in _DEMO_USERS.items():
                row = await session.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                )
                if row.first():
                    await session.execute(
                        text("UPDATE users SET password_hash = :hash, role = :role WHERE email = :email"),
                        {"hash": bcrypt.hash(password), "role": role, "email": email},
                    )
                else:
                    # CRM user doesn't exist yet — create with a CRM-prefixed username
                    # if the base username is taken by another app
                    existing_name = await session.execute(
                        text("SELECT id FROM users WHERE username = :user"), {"user": username},
                    )
                    actual_username = f"crm-{username}" if existing_name.first() else username
                    await session.execute(
                        text(
                            "INSERT INTO users (username, email, password_hash, role) "
                            "VALUES (:user, :email, :hash, :role)"
                        ),
                        {"user": actual_username, "email": email, "hash": bcrypt.hash(password), "role": role},
                    )
            await session.commit()
            return

        now = datetime.utcnow()
        users = [
            User(username=u, email=e, password_hash=bcrypt.hash(p), role=r)
            for u, (p, r, e) in _DEMO_USERS.items()
        ]
        session.add_all(users)

        customers = [
            Customer(name="Acme Corporation", email="contact@acme.com", phone="+1-555-0101", company="Acme Corp", industry="Manufacturing", revenue=5200000),
            Customer(name="Globex Industries", email="info@globex.com", phone="+1-555-0102", company="Globex", industry="Technology", revenue=12800000),
            Customer(name="Initech Solutions", email="sales@initech.com", phone="+1-555-0103", company="Initech", industry="Consulting", revenue=3400000),
            Customer(name="Wayne Enterprises", email="bruce@wayne.com", phone="+1-555-0106", company="Wayne Ent", industry="Conglomerate", revenue=120000000),
        ]
        session.add_all(customers)

        products = [
            # Racing Drones
            Product(name="Phantom Racer X1", sku="OCTO-001", description="Engineered for blistering speed and unmatched agility. Lightweight carbon fiber frame ensures maximum durability in high-speed maneuvers.", price=499.99, stock=150, category="Racing Drones", image_url="/static/img/products/octo_001.jpg"),
            Product(name="Vortex Pro FPV", sku="OCTO-002", description="Immersive first-person view racing with exceptional control and a robust design, perfect for competitive pilots.", price=629.50, stock=120, category="Racing Drones", image_url="/static/img/products/octo_002.jpg"),
            Product(name="Ignite Micro Racer", sku="OCTO-003", description="Designed for indoor racing fun and tight obstacle courses. Small size doesn't compromise on speed or responsiveness.", price=179.00, stock=250, category="Racing Drones", image_url="/static/img/products/octo_003.jpg"),
            # Camera Drones
            Product(name="SkyLens 4K Pro", sku="OCTO-004", description="Capture breathtaking aerial footage with a 3-axis gimbal and advanced flight modes. Extended battery for longer creative sessions.", price=1299.99, stock=80, category="Camera Drones", image_url="/static/img/products/octo_004.jpg"),
            Product(name="AeroFold Mini", sku="OCTO-005", description="Your perfect travel companion, easily folding down to fit in any bag. Crisp 1080p video and stable flight.", price=349.95, stock=180, category="Camera Drones", image_url="/static/img/products/octo_005.jpg"),
            Product(name="CinemaFly Xtreme", sku="OCTO-006", description="Designed for professional filmmakers with interchangeable lenses and unparalleled stability for cinematic productions.", price=3500.00, stock=60, category="Camera Drones", image_url="/static/img/products/octo_006.jpg"),
            # Industrial Drones
            Product(name="TerraSurvey RTK", sku="OCTO-007", description="Precision mapping and surveying with RTK GPS for centimeter-level accuracy. Streamlines data collection for construction.", price=9500.00, stock=50, category="Industrial Drones", image_url="/static/img/products/octo_007.jpg"),
            Product(name="InspectMaster Thermal", sku="OCTO-008", description="Detailed inspections with high-resolution thermal camera and advanced obstacle avoidance for infrastructure assessments.", price=7200.00, stock=70, category="Industrial Drones", image_url="/static/img/products/octo_008.jpg"),
            Product(name="AgriSprayer Pro", sku="OCTO-009", description="Optimize crop health with efficient and precise payload application. Robust design handles large fields with ease.", price=11000.00, stock=55, category="Industrial Drones", image_url="/static/img/products/octo_009.jpg"),
            # Accessories
            Product(name="Extra Flight Battery Pack", sku="OCTO-010", description="Extend your flight time with an additional high-capacity LiPo battery. Compatible with Phantom Racer and SkyLens series.", price=49.99, stock=400, category="Accessories", image_url="/static/img/products/acc_001.jpg"),
            Product(name="Propeller Guard Set", sku="OCTO-011", description="Protect your drone and surroundings with this durable propeller guard set. Easy to install, essential for beginners.", price=19.95, stock=500, category="Accessories", image_url="/static/img/products/acc_002.jpg"),
            Product(name="Rugged Carrying Case", sku="OCTO-012", description="Safely transport your drone with this custom-fitted rugged carrying case. Superior protection against impacts.", price=120.00, stock=200, category="Accessories", image_url="/static/img/products/acc_003.jpg"),
        ]
        session.add_all(products)
        await session.flush()

        orders = [
            Order(
                customer_id=customers[0].id,
                total=129998.0,
                status="completed",
                shipping_address="123 Industrial Way, Springfield",
                source_system="seed",
                source_order_id="seed-1001",
                source_customer_email=customers[0].email,
                sync_status="seeded",
                backlog_status="current",
                correlation_id="seed-1001",
                last_synced_at=now - timedelta(days=2),
            ),
            Order(
                customer_id=customers[1].id,
                total=44998.0,
                status="processing",
                shipping_address="456 Tech Park, Silicon Valley",
                source_system="seed",
                source_order_id="seed-1002",
                source_customer_email=customers[1].email,
                sync_status="seeded",
                backlog_status="backlog",
                correlation_id="seed-1002",
                last_synced_at=now - timedelta(hours=3),
            ),
            Order(
                customer_id=customers[3].id,
                total=269997.0,
                status="pending",
                shipping_address="1007 Mountain Drive, Gotham",
                source_system="octo-drone-shop",
                source_order_id="drone-2001",
                source_customer_email=customers[3].email,
                sync_status="synced",
                backlog_status="backlog",
                correlation_id="seed-2001",
                last_synced_at=now - timedelta(minutes=45),
            ),
        ]
        session.add_all(orders)
        await session.flush()

        session.add_all(
            [
                OrderItem(order_id=orders[0].id, product_id=products[0].id, quantity=1, unit_price=99999.0),
                OrderItem(order_id=orders[0].id, product_id=products[2].id, quantity=2, unit_price=14999.0),
                OrderItem(order_id=orders[1].id, product_id=products[1].id, quantity=1, unit_price=29999.0),
                OrderItem(order_id=orders[1].id, product_id=products[2].id, quantity=1, unit_price=14999.0),
                OrderItem(order_id=orders[2].id, product_id=products[0].id, quantity=2, unit_price=99999.0),
                OrderItem(order_id=orders[2].id, product_id=products[3].id, quantity=1, unit_price=19999.0),
            ]
        )

        session.add_all(
            [
                Invoice(order_id=orders[0].id, invoice_number="INV-2026-001", amount=129998.0, tax=10399.84, status="paid", due_date=now + timedelta(days=15)),
                Invoice(order_id=orders[1].id, invoice_number="INV-2026-002", amount=44998.0, tax=3599.84, status="pending", due_date=now + timedelta(days=20)),
                SupportTicket(customer_id=customers[1].id, subject="Billing discrepancy", description="Invoice total mismatch", priority="high", status="open", assigned_to="manager"),
                SupportTicket(customer_id=customers[3].id, subject="Backlog escalation", description="Drone shop order still pending", priority="medium", status="open", assigned_to="ops"),
                Warehouse(name="East Hub", region="us-east-1", address="Ashburn", capacity=20000, current_stock=12000, is_active=True),
                Warehouse(name="EU Hub", region="eu-frankfurt-1", address="Frankfurt", capacity=15000, current_stock=7000, is_active=True),
                Shipment(
                    order_id=orders[1].id,
                    tracking_number="TRK-2026-0002",
                    carrier="fedex",
                    status="processing",
                    origin_region="us-east-1",
                    destination_region="us-west-1",
                    weight_kg=2.4,
                    shipping_cost=149.0,
                    estimated_delivery=now + timedelta(days=2),
                ),
                Campaign(name="Security Webinar Series", campaign_type="email", status="active", budget=15000.0, spent=8200.0, target_audience="CISOs and security teams"),
            ]
        )
        await session.flush()

        active_campaign = await session.scalar(select(Campaign).limit(1))
        if active_campaign:
            session.add_all(
                [
                    Lead(campaign_id=active_campaign.id, customer_id=customers[0].id, email="alice@acme.com", name="Alice", source="web", status="qualified", score=86),
                    Lead(campaign_id=active_campaign.id, customer_id=customers[1].id, email="bob@globex.com", name="Bob", source="referral", status="new", score=55),
                ]
            )

        session.add(
            AuditLog(
                action="bootstrap.seed",
                resource="database",
                details="Initial demo dataset loaded",
                ip_address="127.0.0.1",
                trace_id="bootstrap-seed",
            )
        )
        await session.commit()


def _ensure_order_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    if "orders" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("orders")}
    dialect = sync_conn.dialect.name
    type_map = {
        "source_system": "VARCHAR2(100 CHAR)" if dialect == "oracle" else "VARCHAR(100)",
        "source_order_id": "VARCHAR2(120 CHAR)" if dialect == "oracle" else "VARCHAR(120)",
        "source_customer_email": "VARCHAR2(200 CHAR)" if dialect == "oracle" else "VARCHAR(200)",
        "sync_status": "VARCHAR2(50 CHAR)" if dialect == "oracle" else "VARCHAR(50)",
        "backlog_status": "VARCHAR2(50 CHAR)" if dialect == "oracle" else "VARCHAR(50)",
        "sync_error": "CLOB" if dialect == "oracle" else "TEXT",
        "source_payload": "CLOB" if dialect == "oracle" else "TEXT",
        "correlation_id": "VARCHAR2(128 CHAR)" if dialect == "oracle" else "VARCHAR(128)",
        "last_synced_at": "TIMESTAMP",
    }
    for column_name, ddl_type in type_map.items():
        if column_name not in existing:
            sync_conn.execute(text(f"ALTER TABLE orders ADD ({column_name} {ddl_type})" if dialect == "oracle" else f"ALTER TABLE orders ADD COLUMN {column_name} {ddl_type}"))

    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("orders")}
    if "uq_orders_source_ref" not in unique_constraints:
        if dialect == "oracle":
            sync_conn.execute(text("ALTER TABLE orders ADD CONSTRAINT uq_orders_source_ref UNIQUE (source_system, source_order_id)"))
        else:
            sync_conn.execute(text("ALTER TABLE orders ADD CONSTRAINT uq_orders_source_ref UNIQUE (source_system, source_order_id)"))

    tables = set(inspector.get_table_names())
    if "order_sync_audit" not in tables:
        OrderSyncAudit.__table__.create(sync_conn, checkfirst=True)


def _ensure_product_columns(sync_conn) -> None:
    """Add image_url column to products table if missing."""
    inspector = inspect(sync_conn)
    if "products" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("products")}
    if "image_url" not in existing:
        dialect = sync_conn.dialect.name
        col_type = "VARCHAR2(500 CHAR)" if dialect == "oracle" else "VARCHAR(500)"
        sync_conn.execute(
            text(f"ALTER TABLE products ADD ({col_type})" if dialect == "oracle"
                 else f"ALTER TABLE products ADD COLUMN image_url {col_type}")
        )
