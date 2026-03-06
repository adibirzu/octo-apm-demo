"""OCTO-CRM-APM — Main application entry point.

A cloud-native e-commerce portal with full OCI observability stack
(APM/OTel, RUM, Logging SDK, Splunk HEC) and deliberate security
vulnerabilities for testing and demonstration.
"""

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
from server.database import engine, get_db, init_tables, seed_data
from server.observability.otel_setup import init_otel, get_tracer
from server.observability.logging_sdk import push_log
from server.middleware.tracing import TracingMiddleware
from server.middleware.chaos import ChaosMiddleware
from server.middleware.geo_latency import GeoLatencyMiddleware

# Module routers
from server.modules.auth import router as auth_router
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

logger = logging.getLogger(__name__)

# ── Pre-initialize OTel ────────────────────────────────────────
init_otel(
    service_name=f"{cfg.otel_service_name}-{cfg.app_runtime}",
    service_version="1.0.0",
    apm_endpoint=cfg.oci_apm_endpoint,
    apm_private_key=cfg.oci_apm_private_datakey,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OCTO-CRM-APM starting — APM: %s, RUM: %s, DB: %s",
                cfg.apm_configured, cfg.rum_configured,
                "Oracle ATP" if cfg.use_oracle else "PostgreSQL")

    # Create tables and seed data on startup
    try:
        init_tables()
        seed_data()
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error("Database initialization failed: %s (app will still start)", e)

    push_log("INFO", "OCTO-CRM-APM started", **{
        "app.name": cfg.app_name,
        "app.runtime": cfg.app_runtime,
        "app.apm_configured": cfg.apm_configured,
        "app.db_type": "oracle" if cfg.use_oracle else "postgresql",
    })
    yield
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
app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"], allow_credentials=True)
app.add_middleware(GeoLatencyMiddleware)
app.add_middleware(ChaosMiddleware)
app.add_middleware(TracingMiddleware)

# ── Static files and templates ────────────────────────────────
_server_dir = os.path.dirname(os.path.abspath(__file__))
_static_dir = os.path.join(_server_dir, "static")
_templates_dir = os.path.join(_server_dir, "templates")

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None

# ── Register API routers ──────────────────────────────────────
app.include_router(auth_router)
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


# ── Health & readiness ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": cfg.app_name}


@app.get("/ready")
async def ready():
    tracer = get_tracer()
    with tracer.start_as_current_span("health.readiness") as span:
        db_ok = False
        try:
            async with get_db() as db:
                await db.execute(text("SELECT 1 FROM DUAL" if cfg.use_oracle else "SELECT 1"))
                db_ok = True
        except Exception as e:
            span.set_attribute("health.db_error", str(e))

        return {
            "ready": db_ok,
            "database": "connected" if db_ok else "disconnected",
            "db_type": "oracle_atp" if cfg.use_oracle else "postgresql",
            "apm_configured": cfg.apm_configured,
            "rum_configured": cfg.rum_configured,
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
            {"name": "analytics", "label": "Analytics", "endpoints": 4,
             "related_to": ["orders", "campaigns", "shipping", "page_views"]},
            {"name": "admin", "label": "Admin", "endpoints": 3,
             "related_to": ["users", "audit_logs"]},
            {"name": "dashboard", "label": "Dashboard", "endpoints": 4,
             "related_to": ["orders", "catalogue", "customers"]},
            {"name": "simulation", "label": "Simulation", "endpoints": 5,
             "related_to": ["dashboard"]},
            {"name": "integrations", "label": "Integrations", "endpoints": 5,
             "related_to": ["orders", "customers", "enterprise-crm-portal"],
             "cross_service": True},
        ],
        "total_modules": 10,
        "total_endpoints": 50,
    }


# ── Frontend pages ────────────────────────────────────────────

def _render_page(request: Request, page: str, title: str, **ctx):
    if templates is None:
        return HTMLResponse(f"<h1>{title}</h1><p>Templates not configured</p>")
    return templates.TemplateResponse(
        f"{page}.html",
        {"request": request, "title": title,
         "rum_endpoint": cfg.oci_apm_rum_endpoint,
         "rum_public_key": cfg.oci_apm_public_datakey,
         "rum_configured": cfg.rum_configured,
         "app_name": cfg.app_name, **ctx},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render_page(request, "dashboard", "Dashboard")


@app.get("/shop", response_class=HTMLResponse)
async def shop_page(request: Request):
    return _render_page(request, "page", "Drone Shop", module="shop")


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


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render_page(request, "login", "Login")


# ── Error handler ─────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    push_log("ERROR", f"Unhandled exception: {str(exc)}", **{
        "error.type": type(exc).__name__,
        "error.message": str(exc),
        "http.url.path": request.url.path,
    })
    # VULN: Verbose error in all environments
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__, "path": request.url.path},
    )
