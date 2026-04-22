"""Business metrics — domain-specific KPIs exposed as OTel instruments.

These metrics answer questions like "how many orders per minute?" and
"what's the revenue distribution?" — things traces alone can't efficiently answer.

Label design principles:
  - Low cardinality only (enum-like values, not free-text IDs)
  - Labels that enable meaningful dashboard breakdowns for demos
  - Never include user IDs, session IDs, or IPs in metric labels
"""

from opentelemetry import metrics

from server.observability.metrics import get_meter

_inited = False
_meter = None

# Instruments (initialized lazily to avoid import-time side effects)
orders_created = None
order_value = None
invoices_generated = None
invoice_paid = None
tickets_created = None
auth_login = None
auth_login_failed = None
active_sessions = None
order_sync_total = None
security_events = None
campaigns_created = None
leads_captured = None
leads_converted = None
shipments_created = None
shipments_delivered = None
shipping_cost = None
page_views_tracked = None
page_load_time = None
file_uploads = None
file_downloads = None
reports_generated = None
reports_executed = None
dashboard_loads = None


def _ensure():
    global _inited, _meter
    global orders_created, order_value, invoices_generated, invoice_paid
    global tickets_created, auth_login, auth_login_failed, active_sessions
    global order_sync_total, security_events
    global campaigns_created, leads_captured, leads_converted
    global shipments_created, shipments_delivered, shipping_cost
    global page_views_tracked, page_load_time
    global file_uploads, file_downloads
    global reports_generated, reports_executed
    global dashboard_loads

    if _inited:
        return
    _meter = get_meter()

    # ── Orders ─────────────────────────────────────────────────────
    orders_created = _meter.create_counter(
        "crm.business.orders.created",
        description="Orders created",
        unit="1",
    )
    order_value = _meter.create_histogram(
        "crm.business.order.value",
        description="Order total value in USD",
        unit="USD",
    )
    order_sync_total = _meter.create_counter(
        "crm.business.orders.sync",
        description="External order sync operations",
        unit="1",
    )

    # ── Invoices ───────────────────────────────────────────────────
    invoices_generated = _meter.create_counter(
        "crm.business.invoices.generated",
        description="Invoices generated or accessed",
        unit="1",
    )
    invoice_paid = _meter.create_counter(
        "crm.business.invoices.paid",
        description="Invoices marked as paid",
        unit="1",
    )

    # ── Support Tickets ────────────────────────────────────────────
    tickets_created = _meter.create_counter(
        "crm.business.tickets.created",
        description="Support tickets created",
        unit="1",
    )

    # ── Auth ───────────────────────────────────────────────────────
    auth_login = _meter.create_counter(
        "crm.business.auth.login",
        description="Successful logins",
        unit="1",
    )
    auth_login_failed = _meter.create_counter(
        "crm.business.auth.login_failed",
        description="Failed login attempts",
        unit="1",
    )
    active_sessions = _meter.create_up_down_counter(
        "crm.business.sessions.active",
        description="Active user sessions",
        unit="1",
    )

    # ── Campaigns & Leads ──────────────────────────────────────────
    campaigns_created = _meter.create_counter(
        "crm.business.campaigns.created",
        description="Marketing campaigns created",
        unit="1",
    )
    leads_captured = _meter.create_counter(
        "crm.business.leads.captured",
        description="Leads captured into campaigns",
        unit="1",
    )
    leads_converted = _meter.create_counter(
        "crm.business.leads.converted",
        description="Leads converted to qualified/customer status",
        unit="1",
    )

    # ── Shipping ───────────────────────────────────────────────────
    shipments_created = _meter.create_counter(
        "crm.business.shipments.created",
        description="Shipments created",
        unit="1",
    )
    shipments_delivered = _meter.create_counter(
        "crm.business.shipments.delivered",
        description="Shipments marked as delivered",
        unit="1",
    )
    shipping_cost = _meter.create_histogram(
        "crm.business.shipping.cost",
        description="Shipping cost per shipment",
        unit="USD",
    )

    # ── Analytics / Page Views ─────────────────────────────────────
    page_views_tracked = _meter.create_counter(
        "crm.business.page_views.tracked",
        description="Page views recorded via analytics endpoint",
        unit="1",
    )
    page_load_time = _meter.create_histogram(
        "crm.business.page_views.load_time",
        description="Client-reported page load time",
        unit="ms",
    )

    # ── Files ──────────────────────────────────────────────────────
    file_uploads = _meter.create_counter(
        "crm.business.files.uploads",
        description="File upload operations",
        unit="1",
    )
    file_downloads = _meter.create_counter(
        "crm.business.files.downloads",
        description="File download operations",
        unit="1",
    )

    # ── Reports ────────────────────────────────────────────────────
    reports_generated = _meter.create_counter(
        "crm.business.reports.created",
        description="Reports created/saved",
        unit="1",
    )
    reports_executed = _meter.create_counter(
        "crm.business.reports.executed",
        description="Custom report queries executed",
        unit="1",
    )

    # ── Dashboard ──────────────────────────────────────────────────
    dashboard_loads = _meter.create_counter(
        "crm.business.dashboard.loads",
        description="Dashboard summary loads (6+ DB queries each)",
        unit="1",
    )

    # ── Security ───────────────────────────────────────────────────
    security_events = _meter.create_counter(
        "crm.business.security.events",
        description="Security events detected by type and severity",
        unit="1",
    )

    _inited = True


# ── Recording functions ───────────────────────────────────────────
# Each function accepts only low-cardinality label values.

def record_order_created(total: float, source: str = "enterprise-crm"):
    """Labels: source (enterprise-crm | octo-drone-shop)."""
    _ensure()
    orders_created.add(1, {"source": source})
    order_value.record(total, {"source": source})


def record_invoice_paid(invoice_id: int):
    _ensure()
    invoice_paid.add(1)


def record_ticket_created(priority: str = "medium"):
    """Labels: priority (low | medium | high | critical)."""
    _ensure()
    tickets_created.add(1, {"priority": priority})


def record_login_success(method: str = "password", role: str = "user"):
    """Labels: method (password | sso), role (user | admin)."""
    _ensure()
    auth_login.add(1, {"method": method, "role": role})
    active_sessions.add(1, {"method": method})


def record_login_failure(reason: str = "invalid_password"):
    """Labels: reason (user_not_found | invalid_password)."""
    _ensure()
    auth_login_failed.add(1, {"reason": reason})


def record_logout():
    _ensure()
    active_sessions.add(-1)


def record_order_sync(created: int, updated: int, failed: int):
    """Labels: result (success | partial_failure)."""
    _ensure()
    order_sync_total.add(1, {"result": "success" if failed == 0 else "partial_failure"})


def record_security_event(vuln_type: str, severity: str):
    """Labels: type (sqli | xss_reflected | ...), severity (low | medium | high | critical)."""
    _ensure()
    security_events.add(1, {"type": vuln_type, "severity": severity})


def record_campaign_created(campaign_type: str = "email"):
    """Labels: type (email | social | display | referral)."""
    _ensure()
    campaigns_created.add(1, {"type": campaign_type})


def record_lead_captured(source: str = "web"):
    """Labels: source (web | referral | import | api)."""
    _ensure()
    leads_captured.add(1, {"source": source})


def record_lead_converted(new_status: str = "converted"):
    """Labels: status (qualified | converted)."""
    _ensure()
    leads_converted.add(1, {"status": new_status})


def record_shipment_created(carrier: str = "", origin_region: str = "", destination_region: str = ""):
    """Labels: carrier, origin_region, destination_region — all bounded by real-world values."""
    _ensure()
    attrs = {}
    if carrier:
        attrs["carrier"] = carrier[:30]
    if origin_region:
        attrs["origin"] = origin_region[:30]
    if destination_region:
        attrs["destination"] = destination_region[:30]
    shipments_created.add(1, attrs)


def record_shipment_delivered():
    _ensure()
    shipments_delivered.add(1)


def record_shipping_cost_value(cost: float, carrier: str = ""):
    _ensure()
    attrs = {}
    if carrier:
        attrs["carrier"] = carrier[:30]
    shipping_cost.record(cost, attrs)


def record_page_view(page: str, region: str = "", load_time_ms: int = 0):
    """Labels: page (URL path), region (cloud region code)."""
    _ensure()
    attrs = {"page": page[:50]}
    if region:
        attrs["region"] = region[:30]
    page_views_tracked.add(1, attrs)
    if load_time_ms > 0:
        page_load_time.record(float(load_time_ms), attrs)


def record_file_upload(content_type: str = "unknown"):
    """Labels: content_type (truncated to category)."""
    _ensure()
    # Reduce cardinality: use type category only (e.g., "image", "application")
    category = content_type.split("/")[0] if "/" in content_type else content_type
    file_uploads.add(1, {"type": category[:20]})


def record_file_download():
    _ensure()
    file_downloads.add(1)


def record_report_created(report_type: str = "custom"):
    """Labels: type (custom | standard | sql)."""
    _ensure()
    reports_generated.add(1, {"type": report_type[:20]})


def record_report_executed():
    _ensure()
    reports_executed.add(1)


def record_dashboard_load():
    _ensure()
    dashboard_loads.add(1)
