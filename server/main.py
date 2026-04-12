"""OCTO Drone Shop main application entry point."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from server.config import cfg
from server.database import engine, get_db, init_tables, seed_data, sync_engine
from server.observability.correlation import runtime_snapshot
from server.observability.otel_setup import init_otel, get_tracer
from server.observability.logging_sdk import push_log
from server.observability.metrics import init_metrics, runtime_metrics
from server.observability.oci_monitoring import start_monitoring, stop_monitoring, increment_requests, increment_errors
from server.middleware.tracing import TracingMiddleware
from server.middleware.metrics_mw import MetricsMiddleware
from server.middleware.chaos import ChaosMiddleware
from server.middleware.geo_latency import GeoLatencyMiddleware
from server.security.headers import SecurityHeadersMiddleware
from server.security.request_id import RequestIdMiddleware
from server.observability.workflow_context import WorkflowContextMiddleware
from server.observability.log_enricher import install_enricher

# Module routers
from server.modules.auth import router as auth_router
from server.modules.sso import router as sso_router
from server.modules.catalogue import router as catalogue_router
from server.modules.orders import router as orders_router
from server.modules.shipping import router as shipping_router
from server.modules.analytics import router as analytics_router
from server.modules.campaigns import router as campaigns_router
from server.modules.admin import router as admin_router
from server.modules.shop import router as shop_router
from server.modules.simulation import router as simulation_router
from server.modules.dashboard import router as dashboard_router
from server.modules.integrations import router as integrations_router
from server.modules.services import router as services_router
from server.modules.observability_dashboard import router as observability_dashboard_router

logger = logging.getLogger(__name__)

# ── Pre-initialize OTel + Metrics ─────────────────────────────
init_otel(
    service_name=cfg.otel_service_name,
    service_version=cfg.app_version,
    apm_endpoint=cfg.oci_apm_endpoint,
    apm_private_key=cfg.oci_apm_private_datakey,
    sync_engine=sync_engine,
    async_engine=engine,
)
init_metrics()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg.validate()
    runtime_metrics.setup()
    logger.info(
        "OCTO Drone Shop starting — APM: %s, RUM: %s, Metrics: enabled, DB: %s",
        cfg.apm_configured,
        cfg.rum_configured,
        cfg.database_target_label,
    )

    # Create tables and seed data on startup
    try:
        init_tables()
        seed_data()
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error("Database initialization failed: %s (app will still start)", e)

    start_monitoring()  # OCI Monitoring custom metrics (if OCI_COMPARTMENT_ID is set)

    push_log("INFO", "OCTO-CRM-APM started", **{
        "app.name": cfg.app_name,
        "app.runtime": cfg.app_runtime,
        "app.apm_configured": cfg.apm_configured,
        "app.db_type": cfg.database_target_label,
    })
    yield
    stop_monitoring()
    push_log("INFO", "OCTO-CRM-APM shutting down")


app = FastAPI(
    title="OCTO-CRM-APM",
    description="Cloud-native e-commerce with full observability (OCI APM, RUM, Logging, Splunk)",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

# ── Middleware (outermost first) ──────────────────────────────
# CORS — never silently fall back to wildcard. An empty list disables CORS
# entirely (FastAPI's CORSMiddleware short-circuits when allow_origins is
# empty), which is the correct safe default. Wildcard with credentials is
# explicitly forbidden by the CORS spec; we refuse the combination.
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", cfg.cors_origins_default).split(",")
    if o.strip() and o.strip() != "*"
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Correlation-Id", "X-Session-Id"],
        allow_credentials=True,
    )
else:
    logger.warning("CORS disabled — CORS_ALLOWED_ORIGINS produced no valid origins")
app.add_middleware(GeoLatencyMiddleware)
app.add_middleware(ChaosMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(TracingMiddleware)
# Security layer (outermost so headers wrap all responses incl. errors).
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(WorkflowContextMiddleware)
app.add_middleware(RequestIdMiddleware)

install_enricher()

# Chaos DB fault hooks (no-op unless CHAOS_ENABLED + active scenario).
try:
    from server.chaos.db_faults import install as _install_chaos_db
    _install_chaos_db(sync_engine)
    if engine is not None:
        _install_chaos_db(engine)
except Exception as _exc:  # defensive — chaos must never break boot
    logger.warning("chaos db hook install failed: %s", _exc)

# ── Static files and templates ────────────────────────────────
_server_dir = os.path.dirname(os.path.abspath(__file__))
_static_dir = os.path.join(_server_dir, "static")
_templates_dir = os.path.join(_server_dir, "templates")

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None

# ── Register API routers ──────────────────────────────────────
app.include_router(auth_router)
app.include_router(sso_router)
app.include_router(catalogue_router)
app.include_router(orders_router)
app.include_router(shipping_router)
app.include_router(analytics_router)
app.include_router(campaigns_router)
app.include_router(admin_router)
app.include_router(shop_router)
app.include_router(simulation_router)
app.include_router(dashboard_router)
app.include_router(integrations_router)
app.include_router(services_router)
app.include_router(observability_dashboard_router)

# Chaos readers (shop is reader-only; control surface lives on CRM + Ops).
from server.chaos.router import router as chaos_reader_router
app.include_router(chaos_reader_router)


# ── Prometheus /metrics endpoint ──────────────────────────────
try:
    from prometheus_client import make_asgi_app as _make_prom_app
    app.mount("/metrics", _make_prom_app())
    logger.info("Prometheus /metrics endpoint mounted")
except ImportError:
    logger.info("prometheus_client not installed — /metrics not available")


# ── Health & readiness ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": cfg.app_name}


@app.get("/ready")
async def ready():
    tracer = get_tracer()
    with tracer.start_as_current_span("health.readiness") as span:
        db_ok = False
        _db_start = __import__("time").monotonic()
        try:
            async with get_db() as db:
                await db.execute(text("SELECT 1 FROM DUAL"))
                db_ok = True
        except Exception as e:
            span.set_attribute("health.db_error", str(e))
        from server.observability.oci_monitoring import set_db_latency
        set_db_latency(round((__import__("time").monotonic() - _db_start) * 1000, 2))

        return {
            "ready": db_ok,
            "database": "connected" if db_ok else "disconnected",
            "db_type": cfg.database_target_label,
            "apm_configured": cfg.apm_configured,
            "rum_configured": cfg.rum_configured,
            "workflow_gateway_configured": cfg.workflow_gateway_configured,
            "selectai_configured": cfg.selectai_configured,
            "runtime": runtime_snapshot(),
        }


@app.get("/api/modules")
async def list_modules():
    """Module dependency graph."""
    return {
        "modules": [
            {"name": "catalogue", "label": "Catalogue", "endpoints": 5,
             "related_to": ["orders", "shop", "reviews"]},
            {"name": "orders", "label": "Orders", "endpoints": 6,
             "related_to": ["catalogue", "shipping", "customers"]},
            {"name": "shop", "label": "Drone Shop", "endpoints": 8,
             "related_to": ["catalogue", "orders", "coupons", "wallet"]},
            {"name": "shipping", "label": "Shipping", "endpoints": 5,
             "related_to": ["orders", "warehouses", "analytics"]},
            {"name": "campaigns", "label": "Campaigns", "endpoints": 5,
             "related_to": ["leads", "analytics", "customers"]},
            {"name": "analytics", "label": "Analytics", "endpoints": 6,
             "related_to": ["orders", "campaigns", "shipping", "page_views"]},
            {"name": "admin", "label": "Admin", "endpoints": 3,
             "related_to": ["users", "audit_logs"]},
            {"name": "dashboard", "label": "Dashboard", "endpoints": 4,
             "related_to": ["orders", "catalogue", "customers"]},
            {"name": "simulation", "label": "Simulation", "endpoints": 5,
             "related_to": ["dashboard"]},
            {"name": "integrations", "label": "Integrations", "endpoints": 7,
             "related_to": ["orders", "customers", "enterprise-crm-portal"],
             "cross_service": True},
            {"name": "observability", "label": "360 Monitoring", "endpoints": 4,
             "related_to": ["integrations", "dashboard", "analytics"],
             "cross_service": True},
        ],
        "total_modules": 11,
        "total_endpoints": 58,
    }


# ── Frontend pages ────────────────────────────────────────────

def _render_page(request: Request, page: str, title: str, **ctx):
    if templates is None:
        return HTMLResponse(f"<h1>{title}</h1><p>Templates not configured</p>")
    request.state.page_name = ctx.get("module") or page
    request.state.module_name = ctx.get("module") or page
    request.state.template_name = f"{page}.html"
    return templates.TemplateResponse(
        f"{page}.html",
        {"request": request, "title": title,
         "rum_endpoint": cfg.oci_apm_rum_endpoint,
         "rum_public_key": cfg.oci_apm_public_datakey,
         "rum_web_application": cfg.oci_apm_web_application,
         "rum_configured": cfg.rum_configured,
         "apm_configured": cfg.apm_configured,
         "workflow_api_base_url": cfg.workflow_api_base_url,
         "workflow_gateway_configured": cfg.workflow_gateway_configured,
         "selectai_profile_name": cfg.selectai_profile_name,
         "selectai_configured": cfg.selectai_configured,
         "idcs_configured": cfg.idcs_configured,
         "genai_configured": bool(cfg.oci_genai_endpoint and cfg.oci_genai_model_id),
         "app_name": cfg.app_name, **ctx},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render_page(request, "dashboard", "Dashboard")


@app.get("/shop", response_class=HTMLResponse)
async def shop_page(request: Request):
    return _render_page(request, "shop", "Drone Shop", module="shop")


@app.get("/services", response_class=HTMLResponse)
async def services_page(request: Request):
    return _render_page(request, "services", "Services & Support", module="services")


@app.get("/catalogue", response_class=HTMLResponse)
async def catalogue_page(request: Request):
    return _render_page(request, "page", "Catalogue", module="catalogue")


@app.get("/orders-page", response_class=HTMLResponse)
async def orders_page(request: Request):
    return _render_page(request, "page", "Orders", module="orders")


@app.get("/shipping-page", response_class=HTMLResponse)
async def shipping_page(request: Request):
    return _render_page(request, "page", "Shipping", module="shipping")


@app.get("/campaigns-page", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    return _render_page(request, "page", "Campaigns", module="campaigns")


@app.get("/analytics-page", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return _render_page(request, "page", "Analytics", module="analytics")


@app.get("/admin-page", response_class=HTMLResponse)
async def admin_page(request: Request):
    return _render_page(request, "page", "Admin", module="admin")


@app.get("/observability", response_class=HTMLResponse)
async def observability_page(request: Request):
    return _render_page(request, "page", "360 Monitoring", module="observability")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render_page(request, "login", "Login")


# ── Error handler ─────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log full detail server-side; return only an opaque error in production."""
    push_log("ERROR", f"Unhandled exception: {exc}", **{
        "error.type": type(exc).__name__,
        "error.message": str(exc),
        "http.url.path": request.url.path,
    })
    if cfg.is_production:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "type": type(exc).__name__,
            "path": request.url.path,
        },
    )
