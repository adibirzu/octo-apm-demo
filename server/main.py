"""Enterprise CRM Portal — Main application entry point.

A deliberately vulnerable CRM/ERP application for security testing and
observability demonstration. Includes OCI APM (OTel), RUM, OCI Logging SDK,
structured security logging, and chaos engineering capabilities.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text

from server.config import cfg
from server.database import engine, get_db
from server.observability.otel_setup import init_otel, get_tracer
from server.observability.logging_sdk import push_log
from server.middleware.tracing import TracingMiddleware
from server.middleware.chaos import ChaosMiddleware

# Module routers
from server.modules.auth import router as auth_router
from server.modules.customers import router as customers_router
from server.modules.orders import router as orders_router
from server.modules.products import router as products_router
from server.modules.invoices import router as invoices_router
from server.modules.tickets import router as tickets_router
from server.modules.reports import router as reports_router
from server.modules.admin import router as admin_router
from server.modules.files import router as files_router
from server.modules.dashboard import router as dashboard_router
from server.modules.api_keys import router as api_keys_router
from server.modules.simulation import router as simulation_router

logger = logging.getLogger(__name__)


# ── Pre-initialize OTel provider + exporters (before app creation) ────
_sync_engine = create_engine(cfg.database_sync_url) if cfg.database_sync_url else None
init_otel(sync_engine=_sync_engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Enterprise CRM Portal starting — APM: %s, RUM: %s, Logging: %s",
                cfg.apm_configured, cfg.rum_configured, cfg.logging_configured)
    push_log("INFO", "Enterprise CRM Portal started", **{
        "app.name": cfg.app_name,
        "app.runtime": cfg.app_runtime,
        "app.apm_configured": cfg.apm_configured,
        "app.rum_configured": cfg.rum_configured,
    })
    yield
    push_log("INFO", "Enterprise CRM Portal shutting down")


app = FastAPI(
    title="Enterprise CRM Portal",
    description="CRM/ERP application with full observability stack (OCI APM, RUM, Logging, Splunk)",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI BEFORE adding custom middleware (must happen before startup)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

# ── Middleware (order matters — outermost first) ─────────────────
app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"], allow_credentials=True)
app.add_middleware(ChaosMiddleware)
app.add_middleware(TracingMiddleware)

# ── Mount static files and templates ─────────────────────────────
import os
_server_dir = os.path.dirname(os.path.abspath(__file__))
_static_dir = os.path.join(_server_dir, "static")
_templates_dir = os.path.join(_server_dir, "templates")

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

templates = Jinja2Templates(directory=_templates_dir) if os.path.isdir(_templates_dir) else None

# ── Register API routers ─────────────────────────────────────────
app.include_router(auth_router)
app.include_router(customers_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(invoices_router)
app.include_router(tickets_router)
app.include_router(reports_router)
app.include_router(admin_router)
app.include_router(files_router)
app.include_router(dashboard_router)
app.include_router(api_keys_router)
app.include_router(simulation_router)


# ── Health & readiness endpoints ─────────────────────────────────

@app.get("/health")
async def health():
    """Liveness probe — fast, no I/O."""
    return {"status": "ok", "service": cfg.app_name}


@app.get("/ready")
async def ready():
    """Readiness probe — checks database connectivity."""
    tracer = get_tracer()
    with tracer.start_as_current_span("health.readiness") as span:
        db_ok = False
        try:
            async with get_db() as db:
                await db.execute(text("SELECT 1"))
                db_ok = True
        except Exception as e:
            span.set_attribute("health.db_error", str(e))

        result = {
            "ready": db_ok,
            "database": "connected" if db_ok else "disconnected",
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
    return templates.TemplateResponse(
        f"{page}.html",
        {
            "request": request,
            "title": title,
            "rum_endpoint": cfg.oci_apm_rum_endpoint,
            "rum_public_key": cfg.oci_apm_rum_public_datakey,
            "rum_configured": cfg.rum_configured,
            "app_name": cfg.app_name,
            **context,
        }
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _render_page(request, "dashboard", "Dashboard")


@app.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    return _render_page(request, "page", "Customers", module="customers")


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    return _render_page(request, "page", "Orders", module="orders")


@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    return _render_page(request, "page", "Products", module="products")


@app.get("/invoices", response_class=HTMLResponse)
async def invoices_page(request: Request):
    return _render_page(request, "page", "Invoices", module="invoices")


@app.get("/tickets", response_class=HTMLResponse)
async def tickets_page(request: Request):
    return _render_page(request, "page", "Support Tickets", module="tickets")


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return _render_page(request, "page", "Reports", module="reports")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return _render_page(request, "page", "Admin Panel", module="admin")


@app.get("/files", response_class=HTMLResponse)
async def files_page(request: Request):
    return _render_page(request, "page", "File Manager", module="files")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return _render_page(request, "page", "Settings", module="settings")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render_page(request, "login", "Login")


# ── Error handlers ───────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    push_log("ERROR", f"Unhandled exception: {str(exc)}", **{
        "error.type": type(exc).__name__,
        "error.message": str(exc),
        "http.url.path": request.url.path,
        "http.method": request.method,
    })
    # VULN: Verbose error in non-production (but also in production — intentional)
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "type": type(exc).__name__,
            "path": request.url.path,
        }
    )
