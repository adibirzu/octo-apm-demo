"""Enterprise CRM Portal — Main application entry point.

A deliberately vulnerable CRM/ERP application for security testing and
observability demonstration. Includes OCI APM (OTel), RUM, OCI Logging SDK,
structured security logging, and chaos engineering capabilities.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text

from server.bootstrap import bootstrap_database
from server.config import cfg
from server.database import engine, get_db
from server.db_compat import HEALTH_CHECK_SQL
from server.observability.otel_setup import init_otel, get_tracer
from server.observability.logging_sdk import push_log
from server.observability.metrics import init_metrics, runtime_metrics
from server.middleware.tracing import TracingMiddleware
from server.middleware.metrics_mw import MetricsMiddleware
from server.middleware.chaos import ChaosMiddleware
from server.middleware.geo_latency import GeoLatencyMiddleware
from server.middleware.session_gate import SessionGateMiddleware
from server.order_sync import sync_external_orders

# Module routers
from server.modules.auth import router as auth_router
from server.modules.customers import router as customers_router
from server.modules.orders import router as orders_router
from server.modules.products import router as products_router
from server.modules.shops import router as shops_router
from server.modules.invoices import router as invoices_router
from server.modules.tickets import router as tickets_router
from server.modules.reports import router as reports_router
from server.modules.admin import router as admin_router
from server.modules.files import router as files_router
from server.modules.dashboard import router as dashboard_router
from server.modules.api_keys import router as api_keys_router
from server.modules.simulation import router as simulation_router
from server.modules.campaigns import router as campaigns_router
from server.modules.shipping import router as shipping_router
from server.modules.analytics import router as analytics_router
from server.modules.integrations import router as integrations_router
from server.modules.observability_frontend import router as observability_router
from server.modules.observability_dashboard import router as observability_dashboard_router

logger = logging.getLogger(__name__)
cfg.validate()


# ── Pre-initialize OTel provider + exporters (before app creation) ────
def _sync_database_url() -> str:
    url = cfg.database_sync_url or cfg.database_url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("oracle+oracledb_async://"):
        return url.replace("oracle+oracledb_async://", "oracle+oracledb://", 1)
    return url


_sync_url = _sync_database_url()
_sync_engine = create_engine(_sync_url) if _sync_url else None
init_otel(sync_engine=_sync_engine)
init_metrics()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Enterprise CRM Portal starting — APM: %s, RUM: %s, Logging: %s, Metrics: enabled",
                cfg.apm_configured, cfg.rum_configured, cfg.logging_configured)
    for warning in cfg.warn_deprecations():
        logger.warning(warning)
    runtime_metrics.setup()
    await bootstrap_database()
    sync_task = None
    if cfg.orders_sync_enabled:
        sync_task = asyncio.create_task(_orders_sync_loop())
    push_log("INFO", "Enterprise CRM Portal started", **{
        "app.name": cfg.app_name,
        "app.runtime": cfg.app_runtime,
        "app.apm_configured": cfg.apm_configured,
        "app.rum_configured": cfg.rum_configured,
        "orders.sync_enabled": cfg.orders_sync_enabled,
    })
    yield
    if sync_task is not None:
        sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_task
    push_log("INFO", "Enterprise CRM Portal shutting down")


async def _orders_sync_loop() -> None:
    await asyncio.sleep(10)
    while True:
        try:
            await sync_external_orders(correlation_id="background-sync")
        except Exception as exc:
            push_log("ERROR", "Background order sync failed", **{"error.message": str(exc)})
        await asyncio.sleep(max(cfg.orders_sync_interval_seconds, 60))


app = FastAPI(
    title=cfg.brand_name,
    description="CRM/ERP application with full observability stack and cross-service correlation",
    version=cfg.app_version,
    lifespan=lifespan,
)

# Instrument FastAPI BEFORE adding custom middleware (must happen before startup)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

# ── Middleware (order matters — outermost first) ─────────────────
if cfg.cors_allowed_origins:
    # Explicit method + header allowlists. `allow_credentials=True`
    # combined with `allow_methods=["*"]` used to accept TRACE/CONNECT
    # on preflight — tighten here to the methods the app actually uses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "X-Internal-Service-Key",
            "X-Request-Id",
            "X-Run-Id",
            "X-Workflow-Id",
            "traceparent",
            "tracestate",
        ],
        allow_credentials=True,
    )
else:
    logger.warning("CORS middleware not installed because no allowed origins were configured")
app.add_middleware(GeoLatencyMiddleware)
app.add_middleware(ChaosMiddleware)
app.add_middleware(SessionGateMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(TracingMiddleware)
# Security layer (additive).
from server.security.headers import SecurityHeadersMiddleware as _SecHeaders
from server.security.request_id import RequestIdMiddleware as _ReqId
from server.observability.workflow_context import WorkflowContextMiddleware as _WfCtx
from server.observability.log_enricher import install_enricher as _install_enricher
_ops_domain = os.getenv("OPS_DOMAIN", "")
app.add_middleware(
    _SecHeaders,
    allow_framing_from=(f"https://{_ops_domain}" if _ops_domain else None),
)
app.add_middleware(_WfCtx)
app.add_middleware(_ReqId)
_install_enricher()

# Chaos DB fault hooks.
try:
    from server.chaos.db_faults import install as _install_chaos_db
    if _sync_engine is not None:
        _install_chaos_db(_sync_engine)
    if engine is not None:
        _install_chaos_db(engine)
except Exception as _exc:
    logger.warning("chaos db hook install failed: %s", _exc)

# ── Mount static files and templates ─────────────────────────────
_server_dir = os.path.dirname(os.path.abspath(__file__))
_static_dir = os.path.join(_server_dir, "static")
_templates_dir = os.path.join(_server_dir, "templates")

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> RedirectResponse:
    return RedirectResponse(url="/static/img/octo-icon.png", status_code=307)

# ── Register API routers ─────────────────────────────────────────
app.include_router(auth_router)
app.include_router(customers_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(shops_router)
app.include_router(invoices_router)
app.include_router(tickets_router)
app.include_router(reports_router)
app.include_router(admin_router)
app.include_router(files_router)
app.include_router(dashboard_router)
app.include_router(api_keys_router)
app.include_router(simulation_router)
app.include_router(campaigns_router)
app.include_router(shipping_router)
app.include_router(analytics_router)
app.include_router(integrations_router)
app.include_router(observability_router)
app.include_router(observability_dashboard_router)

# Chaos control surface (CRM only — shop has no write endpoints).
from server.chaos.admin import router as chaos_admin_router, page_router as chaos_admin_page_router
app.include_router(chaos_admin_router)
app.include_router(chaos_admin_page_router)


# ── Prometheus /metrics endpoint ──────────────────────────────────
try:
    from prometheus_client import make_asgi_app as _make_prom_app
    app.mount("/metrics", _make_prom_app())
    logger.info("Prometheus /metrics endpoint mounted")
except ImportError:
    logger.info("prometheus_client not installed — /metrics not available")


# ── Health & readiness endpoints ─────────────────────────────────

@app.get("/health")
async def health():
    """Liveness probe — fast, no I/O."""
    return {"status": "ok", "service": cfg.app_name}


@app.get("/api/modules")
async def list_modules():
    """Return the application module graph with inter-module dependencies."""
    return {
        "modules": [
            {"name": "customers", "label": "Customers", "endpoints": 4, "related_to": ["orders", "tickets", "leads", "invoices"]},
            {"name": "orders", "label": "Orders", "endpoints": 6, "related_to": ["customers", "products", "invoices", "shipping"]},
            {"name": "products", "label": "Products", "endpoints": 4, "related_to": ["orders"]},
            {"name": "shops", "label": "Storefronts", "endpoints": 4, "related_to": ["products", "integrations"]},
            {"name": "invoices", "label": "Invoices", "endpoints": 3, "related_to": ["orders"]},
            {"name": "tickets", "label": "Support Tickets", "endpoints": 4, "related_to": ["customers"]},
            {"name": "campaigns", "label": "Campaigns", "endpoints": 6, "related_to": ["leads", "customers", "analytics"]},
            {"name": "leads", "label": "Leads", "endpoints": 3, "related_to": ["campaigns", "customers"]},
            {"name": "shipping", "label": "Shipping", "endpoints": 6, "related_to": ["orders", "warehouses", "analytics"]},
            {"name": "warehouses", "label": "Warehouses", "endpoints": 1, "related_to": ["shipping"]},
            {"name": "analytics", "label": "Analytics", "endpoints": 6, "related_to": ["customers", "orders", "campaigns", "shipping", "leads"]},
            {"name": "reports", "label": "Reports", "endpoints": 3, "related_to": ["customers", "orders", "products"]},
            {"name": "admin", "label": "Admin", "endpoints": 3, "related_to": ["users", "audit_logs"]},
            {"name": "files", "label": "Files", "endpoints": 4, "related_to": ["admin"]},
            {"name": "dashboard", "label": "Dashboard", "endpoints": 4, "related_to": ["customers", "orders", "invoices", "tickets"]},
            {"name": "simulation", "label": "Simulation", "endpoints": 5, "related_to": ["dashboard"]},
            {"name": "integrations", "label": "Integrations", "endpoints": 6,
             "related_to": ["customers", "orders", "drone-shop-portal"],
             "cross_service": True},
            {"name": "observability", "label": "360 Monitoring", "endpoints": 5,
             "related_to": ["integrations", "dashboard", "analytics"],
             "cross_service": True},
        ],
        "total_modules": 18,
        "total_endpoints": 77,
    }


@app.get("/ready")
async def ready():
    """Readiness probe — checks database connectivity."""
    tracer = get_tracer()
    with tracer.start_as_current_span("health.readiness") as span:
        db_ok = False
        try:
            async with get_db() as db:
                await db.execute(text(HEALTH_CHECK_SQL))
                db_ok = True
        except Exception as e:
            span.set_attribute("health.db_error", str(e))

        result = {
            "ready": db_ok,
            "database": "connected" if db_ok else "disconnected",
            "database_target": cfg.database_target_label,
            "atp_ocid": cfg.atp_ocid or None,
            "atp_connection_name": cfg.atp_connection_name or None,
            "apm_configured": cfg.apm_configured,
            "rum_configured": cfg.rum_configured,
            "logging_configured": cfg.logging_configured,
        }
        if not db_ok:
            return JSONResponse(result, status_code=503)
        return result


# ── Frontend pages (HTML with RUM) ──────────────────────────────

def _render_page(request: Request, page: str, title: str, **context):
    """Render an HTML page with RUM injection."""
    if templates is None:
        return HTMLResponse(f"<h1>{title}</h1><p>Templates not configured</p>")
    # Starlette >= 0.46 — must pass request as first positional arg.
    return templates.TemplateResponse(
        request,
        f"{page}.html",
        {
            "title": title,
            "rum_endpoint": cfg.oci_apm_rum_endpoint,
            "rum_public_key": cfg.oci_apm_rum_public_datakey,
            "rum_configured": cfg.rum_configured,
            "app_name": cfg.app_name,
            "brand_name": cfg.brand_name,
            "service_name": cfg.otel_service_name,
            "app_version": cfg.app_version,
            "apm_console_url": cfg.apm_console_url,
            "opsi_console_url": cfg.opsi_console_url,
            "db_management_console_url": cfg.db_management_console_url,
            "log_analytics_console_url": cfg.log_analytics_console_url,
            "atp_connection_name": cfg.atp_connection_name,
            **context,
        }
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render_page(request, "dashboard", "Dashboard", nav_key="dashboard")


@app.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    return _render_page(request, "page", "Customers", module="customers", nav_key="customers")


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    return _render_page(request, "orders", "Orders", module="orders", nav_key="orders")


@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    return _render_page(request, "products", "Product Catalog", nav_key="products")


@app.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request):
    return _render_page(request, "catalog", "Storefront Operations", nav_key="catalog")


@app.get("/invoices", response_class=HTMLResponse)
async def invoices_page(request: Request):
    return _render_page(request, "page", "Invoices", module="invoices", nav_key="invoices")


@app.get("/tickets", response_class=HTMLResponse)
async def tickets_page(request: Request):
    return _render_page(request, "page", "Support Tickets", module="tickets", nav_key="tickets")


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return _render_page(request, "page", "Reports", module="reports", nav_key="reports")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return _render_page(request, "page", "Admin Panel", module="admin", nav_key="admin")


@app.get("/files", response_class=HTMLResponse)
async def files_page(request: Request):
    return _render_page(request, "page", "File Manager", module="files", nav_key="files")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return _render_page(request, "simulation", "Simulation Lab", nav_key="settings")


@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    return _render_page(request, "page", "Campaigns", module="campaigns", nav_key="campaigns")


@app.get("/shipping", response_class=HTMLResponse)
async def shipping_page(request: Request):
    return _render_page(request, "page", "Shipping & Logistics", module="shipping", nav_key="shipping")


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return _render_page(request, "page", "Analytics", module="analytics", nav_key="analytics")


@app.get("/leads", response_class=HTMLResponse)
async def leads_page(request: Request):
    return _render_page(request, "page", "Lead Management", module="leads", nav_key="campaigns")


@app.get("/warehouses", response_class=HTMLResponse)
async def warehouses_page(request: Request):
    return _render_page(request, "page", "Warehouses", module="warehouses", nav_key="shipping")


@app.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request):
    return _render_page(request, "integrations", "Integrations", nav_key="integrations")


@app.get("/observability", response_class=HTMLResponse)
async def observability_page(request: Request):
    return _render_page(request, "observability", "360 Monitoring", nav_key="observability")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render_page(request, "login", "Login", nav_key="login", idcs_configured=cfg.idcs_configured)


# ── Error handlers ───────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    push_log("ERROR", f"Unhandled exception: {str(exc)}", **{
        "error.type": type(exc).__name__,
        "error.message": str(exc),
        "http.url.path": request.url.path,
        "http.method": request.method,
        "correlation.id": getattr(request.state, "correlation_id", ""),
    })
    # VULN: Verbose error in non-production (but also in production — intentional)
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "type": type(exc).__name__,
            "path": request.url.path,
            "correlation_id": getattr(request.state, "correlation_id", ""),
        }
    )
