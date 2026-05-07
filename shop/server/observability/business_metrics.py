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
assistant_latency = None
assistant_tokens = None
assistant_errors = None
service_bookings = None
payment_authorizations = None
payment_risk_score = None
java_app_server_calls = None
java_app_server_latency = None
synthetic_user_runs = None
synthetic_user_records = None
synthetic_orders_created = None
attack_stages = None
api_gateway_events = None


def _ensure():
    global _inited, _m
    global orders_created, order_value, cart_additions, checkout_total, checkout_failures
    global products_viewed, search_queries, auth_login, auth_login_failed, active_sessions
    global shipments_created, shipments_delivered, campaigns_created, leads_captured
    global page_views_tracked, security_events, crm_sync_total, assistant_queries
    global assistant_latency, assistant_tokens, assistant_errors, service_bookings
    global payment_authorizations, payment_risk_score, java_app_server_calls, java_app_server_latency
    global synthetic_user_runs, synthetic_user_records, synthetic_orders_created, attack_stages, api_gateway_events

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
    assistant_latency = _m.create_histogram(
        "shop.business.assistant.latency",
        description="AI assistant request latency by provider and outcome",
        unit="ms",
    )
    assistant_tokens = _m.create_counter(
        "shop.business.assistant.tokens",
        description="AI assistant token usage by provider and token direction",
        unit="token",
    )
    assistant_errors = _m.create_counter(
        "shop.business.assistant.errors",
        description="AI assistant guardrail and provider error outcomes",
        unit="1",
    )
    service_bookings = _m.create_counter("shop.business.services.bookings", description="Service bookings", unit="1")
    payment_authorizations = _m.create_counter(
        "shop.business.payment.authorizations",
        description="Payment authorization decisions",
        unit="1",
    )
    payment_risk_score = _m.create_histogram(
        "shop.business.payment.risk_score",
        description="Simulated payment risk score",
        unit="1",
    )
    java_app_server_calls = _m.create_counter(
        "shop.business.java_app_server.calls",
        description="Java APM sidecar calls by operation and status",
        unit="1",
    )
    java_app_server_latency = _m.create_histogram(
        "shop.business.java_app_server.latency",
        description="Java APM sidecar call latency",
        unit="ms",
    )
    synthetic_user_runs = _m.create_counter(
        "shop.business.synthetic_user.runs",
        description="Synthetic user generation runs",
        unit="1",
    )
    synthetic_user_records = _m.create_counter(
        "shop.business.synthetic_user.records",
        description="Synthetic user records created, updated, or deleted",
        unit="1",
    )
    synthetic_orders_created = _m.create_counter(
        "shop.business.synthetic_user.orders.created",
        description="Orders created by synthetic user runs",
        unit="1",
    )
    attack_stages = _m.create_counter(
        "shop.business.attack_lab.stages",
        description="Attack-lab stages emitted for investigation demos",
        unit="1",
    )
    api_gateway_events = _m.create_counter(
        "shop.business.api_gateway.events",
        description="API Gateway route-policy events by action, route family, and status family",
        unit="1",
    )
    _inited = True


def _label(value: object, fallback: str = "unknown", limit: int = 30) -> str:
    normalized = str(value or fallback).strip().lower().replace(" ", "_")
    return (normalized or fallback)[:limit]


def _java_operation_label(operation: object) -> str:
    parts = [
        part
        for part in str(operation or "unknown").replace("/", ".").split(".")
        if part and part not in {"java_app_server", "get", "post", "api", "java-apm", "java_apm"}
    ]
    if not parts:
        return "unknown"
    if parts[0] == "simulate" and len(parts) > 1:
        return ".".join(parts[:2])[:64]
    return ".".join(parts[-2:])[:64] if len(parts) >= 2 else parts[0][:64]


def record_order_created(total: float, source: str = "drone-shop"):
    _ensure()
    orders_created.add(1, {"source": source})
    order_value.record(total, {"source": source})
    try:
        from server.observability.oci_monitoring import increment_orders
        increment_orders()
    except Exception:
        pass

def record_cart_addition(category: str = ""):
    _ensure()
    cart_additions.add(1, {"category": category[:30]} if category else {})

def record_checkout(success: bool = True):
    _ensure()
    checkout_total.add(1, {"result": "success" if success else "failure"})
    if not success:
        checkout_failures.add(1)
    try:
        from server.observability.oci_monitoring import increment_checkouts
        increment_checkouts()
    except Exception:
        pass

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

def record_assistant_query(
    *,
    provider: str = "",
    status: str = "success",
    latency_ms: int | float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
):
    _ensure()
    attrs = {
        "provider": _label(provider or "unknown", limit=40),
        "status": _label(status or "success", limit=30),
    }
    assistant_queries.add(1, attrs)
    if latency_ms is not None:
        try:
            assistant_latency.record(float(latency_ms), attrs)
        except (TypeError, ValueError):
            pass
    for direction, value in (("input", input_tokens), ("output", output_tokens)):
        if value is None:
            continue
        try:
            token_count = max(int(value), 0)
        except (TypeError, ValueError):
            continue
        if token_count:
            assistant_tokens.add(token_count, {**attrs, "direction": direction})
    if attrs["status"] not in {"success", "ok"}:
        assistant_errors.add(1, attrs)

def record_service_booking(service_type: str = ""):
    _ensure()
    service_bookings.add(1, {"type": service_type[:30]} if service_type else {})


def record_payment_authorization(
    *,
    status: str,
    provider: str = "",
    source: str = "checkout",
    risk_score: int | float | None = None,
):
    _ensure()
    attrs = {
        "status": _label(status),
        "provider": _label(provider or "unknown", limit=30),
        "source": _label(source, limit=30),
    }
    payment_authorizations.add(1, attrs)
    if risk_score is not None:
        try:
            payment_risk_score.record(float(risk_score), attrs)
        except (TypeError, ValueError):
            return


def record_java_app_server_call(*, operation: str, status: str, latency_ms: float = 0.0):
    _ensure()
    attrs = {
        "operation": _java_operation_label(operation),
        "status": _label(status),
    }
    java_app_server_calls.add(1, attrs)
    if latency_ms > 0:
        java_app_server_latency.record(float(latency_ms), attrs)


def record_synthetic_user_run(
    *,
    created: int,
    updated: int,
    deleted: int,
    orders_created: int,
    generator: str = "manual",
):
    _ensure()
    attrs = {"generator": _label(generator, limit=30)}
    synthetic_user_runs.add(1, attrs)
    for operation, value in (("created", created), ("updated", updated), ("deleted", deleted)):
        count = max(int(value or 0), 0)
        if count:
            synthetic_user_records.add(count, {"operation": operation, **attrs})
    order_count = max(int(orders_created or 0), 0)
    if order_count:
        synthetic_orders_created.add(order_count, {"source": "synthetic-user-cron", **attrs})


def record_attack_stage(*, stage: str, severity: str, technique_id: str):
    _ensure()
    attack_stages.add(
        1,
        {
            "stage": _label(stage, limit=40),
            "severity": _label(severity, limit=20),
            "technique_id": str(technique_id or "unknown")[:24],
        },
    )


def record_api_gateway_event(*, action: str, route_family: str, status_code: int, scope: str):
    _ensure()
    try:
        status = int(status_code)
    except (TypeError, ValueError):
        status = 0
    status_family = f"{status // 100}xx" if status >= 100 else "unknown"
    api_gateway_events.add(
        1,
        {
            "action": _label(action, limit=30),
            "route_family": _label(route_family, limit=40),
            "status_family": status_family,
            "scope": _label(scope, limit=20),
        },
    )
