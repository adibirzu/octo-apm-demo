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

    from server.database import async_session_factory

    async with async_session_factory() as session:
        existing_user = await session.scalar(select(User.id).limit(1))
        if existing_user:
            return

        now = datetime.utcnow()
        users = [
            User(username="admin", email="admin@crm-enterprise.local", password_hash=bcrypt.hash("admin123"), role="admin"),
            User(username="user1", email="user1@crm-enterprise.local", password_hash=bcrypt.hash("password1"), role="user"),
            User(username="manager", email="manager@crm-enterprise.local", password_hash=bcrypt.hash("password1"), role="manager"),
            User(username="viewer", email="viewer@crm-enterprise.local", password_hash=bcrypt.hash("viewer123"), role="viewer"),
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
            Product(name="Enterprise License", sku="ENT-001", description="Full enterprise software license", price=99999.0, stock=100, category="License"),
            Product(name="Professional License", sku="PRO-001", description="Professional tier license", price=29999.0, stock=500, category="License"),
            Product(name="Premium Support", sku="SUP-001", description="24/7 premium support package", price=14999.0, stock=200, category="Support"),
            Product(name="Cloud Hosting", sku="CLD-001", description="Managed cloud hosting per year", price=19999.0, stock=300, category="Infrastructure"),
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
