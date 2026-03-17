"""Business metrics — drone-shop-specific KPIs exposed as OTel instruments.

Low-cardinality labels only. Instruments lazily initialized.
"""

from server.observability.metrics import get_meter

_inited = False
_m = None

# Instruments
orders_created = None
order_value = None
cart_additions = None
checkout_total = None
checkout_failures = None
products_viewed = None
search_queries = None
auth_login = None
auth_login_failed = None
active_sessions = None
shipments_created = None
shipments_delivered = None
campaigns_created = None
leads_captured = None
page_views_tracked = None
security_events = None
crm_sync_total = None
assistant_queries = None
service_bookings = None


def _ensure():
    global _inited, _m
    global orders_created, order_value, cart_additions, checkout_total, checkout_failures
    global products_viewed, search_queries, auth_login, auth_login_failed, active_sessions
    global shipments_created, shipments_delivered, campaigns_created, leads_captured
    global page_views_tracked, security_events, crm_sync_total, assistant_queries, service_bookings

    if _inited:
        return
    _m = get_meter()

    orders_created = _m.create_counter("shop.business.orders.created", description="Orders placed", unit="1")
    order_value = _m.create_histogram("shop.business.order.value", description="Order total value", unit="USD")
    cart_additions = _m.create_counter("shop.business.cart.additions", description="Items added to cart", unit="1")
    checkout_total = _m.create_counter("shop.business.checkout.total", description="Checkout attempts", unit="1")
    checkout_failures = _m.create_counter("shop.business.checkout.failures", description="Failed checkouts", unit="1")
    products_viewed = _m.create_counter("shop.business.products.viewed", description="Product detail views", unit="1")
    search_queries = _m.create_counter("shop.business.search.queries", description="Product search queries", unit="1")
    auth_login = _m.create_counter("shop.business.auth.login", description="Successful logins", unit="1")
    auth_login_failed = _m.create_counter("shop.business.auth.login_failed", description="Failed logins", unit="1")
    active_sessions = _m.create_up_down_counter("shop.business.sessions.active", description="Active sessions", unit="1")
    shipments_created = _m.create_counter("shop.business.shipments.created", description="Shipments created", unit="1")
    shipments_delivered = _m.create_counter("shop.business.shipments.delivered", description="Shipments delivered", unit="1")
    campaigns_created = _m.create_counter("shop.business.campaigns.created", description="Campaigns created", unit="1")
    leads_captured = _m.create_counter("shop.business.leads.captured", description="Leads captured", unit="1")
    page_views_tracked = _m.create_counter("shop.business.page_views", description="Page views tracked", unit="1")
    security_events = _m.create_counter("shop.business.security.events", description="Security events", unit="1")
    crm_sync_total = _m.create_counter("shop.business.crm.sync", description="CRM sync operations", unit="1")
    assistant_queries = _m.create_counter("shop.business.assistant.queries", description="AI assistant queries", unit="1")
    service_bookings = _m.create_counter("shop.business.services.bookings", description="Service bookings", unit="1")
    _inited = True


def record_order_created(total: float, source: str = "drone-shop"):
    _ensure()
    orders_created.add(1, {"source": source})
    order_value.record(total, {"source": source})

def record_cart_addition(category: str = ""):
    _ensure()
    cart_additions.add(1, {"category": category[:30]} if category else {})

def record_checkout(success: bool = True):
    _ensure()
    checkout_total.add(1, {"result": "success" if success else "failure"})
    if not success:
        checkout_failures.add(1)

def record_product_viewed(category: str = ""):
    _ensure()
    products_viewed.add(1, {"category": category[:30]} if category else {})

def record_search(query_type: str = "text"):
    _ensure()
    search_queries.add(1, {"type": query_type})

def record_login_success(method: str = "password"):
    _ensure()
    auth_login.add(1, {"method": method})
    active_sessions.add(1)

def record_login_failure(reason: str = "invalid"):
    _ensure()
    auth_login_failed.add(1, {"reason": reason})

def record_logout():
    _ensure()
    active_sessions.add(-1)

def record_shipment_created(carrier: str = ""):
    _ensure()
    shipments_created.add(1, {"carrier": carrier[:30]} if carrier else {})

def record_shipment_delivered():
    _ensure()
    shipments_delivered.add(1)

def record_campaign_created(campaign_type: str = "email"):
    _ensure()
    campaigns_created.add(1, {"type": campaign_type})

def record_lead_captured(source: str = "web"):
    _ensure()
    leads_captured.add(1, {"source": source})

def record_page_view(page: str = ""):
    _ensure()
    page_views_tracked.add(1, {"page": page[:50]} if page else {})

def record_security_event(vuln_type: str, severity: str):
    _ensure()
    security_events.add(1, {"type": vuln_type, "severity": severity})

def record_crm_sync(result: str = "success"):
    _ensure()
    crm_sync_total.add(1, {"result": result})

def record_assistant_query():
    _ensure()
    assistant_queries.add(1)

def record_service_booking(service_type: str = ""):
    _ensure()
    service_bookings.add(1, {"type": service_type[:30]} if service_type else {})
