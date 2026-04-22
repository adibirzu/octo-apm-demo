"""Oracle DB session tagging for OPSI and DB Management correlation.

Sets MODULE, ACTION, and CLIENT_IDENTIFIER on Oracle DB connections so that
OCI Operations Insights (OPSI), DB Management SQL Performance, and V$SESSION
can correlate SQL execution back to specific application requests and APM traces.

This is the critical bridge between APM traces and database performance data:
  - MODULE = service name (e.g., 'enterprise-crm-portal')
  - ACTION = HTTP route or operation (e.g., 'GET /api/orders')
  - CLIENT_IDENTIFIER = trace_id for APM drilldown

Without this, all SQL appears as generic ADMIN workload in OPSI/DB Management.
"""

import logging
from contextvars import ContextVar

from sqlalchemy import event

from server.config import cfg

logger = logging.getLogger(__name__)

# Context vars set by middleware before DB calls
_db_action: ContextVar[str] = ContextVar("db_action", default="")
_db_client_id: ContextVar[str] = ContextVar("db_client_id", default="")


def set_db_context(action: str = "", client_identifier: str = ""):
    """Set the DB context for the current request (called from middleware)."""
    _db_action.set(action[:64])  # Oracle limits ACTION to 64 chars
    _db_client_id.set(client_identifier[:64])  # CLIENT_IDENTIFIER limit: 64 chars


def _tag_connection(dbapi_connection, connection_record, connection_proxy):
    """SQLAlchemy pool checkout event — tag the Oracle session."""
    try:
        action = _db_action.get("")
        client_id = _db_client_id.get("")
        module = cfg.otel_service_name[:48]  # Oracle MODULE limit: 48 chars

        # Use oracledb's session attributes (thin or thick mode)
        if hasattr(dbapi_connection, 'module'):
            dbapi_connection.module = module
            dbapi_connection.action = action or "idle"
            dbapi_connection.clientinfo = cfg.app_version[:64]
            dbapi_connection.client_identifier = client_id or ""
        else:
            # Fallback: use DBMS_APPLICATION_INFO via cursor
            cursor = dbapi_connection.cursor()
            cursor.execute(
                "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(:module, :action); END;",
                {"module": module, "action": action or "idle"},
            )
            if client_id:
                cursor.execute(
                    "BEGIN DBMS_SESSION.SET_IDENTIFIER(:client_id); END;",
                    {"client_id": client_id},
                )
            cursor.close()
    except Exception:
        # Never fail the request due to tagging
        logger.debug("DB session tagging failed", exc_info=True)


def _clear_connection(dbapi_connection, connection_record):
    """SQLAlchemy pool checkin event — reset session tags for pool reuse."""
    try:
        if hasattr(dbapi_connection, 'module'):
            dbapi_connection.action = "idle"
            dbapi_connection.client_identifier = ""
        else:
            cursor = dbapi_connection.cursor()
            cursor.execute(
                "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(:module, :action); END;",
                {"module": cfg.otel_service_name[:48], "action": "idle"},
            )
            cursor.execute(
                "BEGIN DBMS_SESSION.SET_IDENTIFIER(:client_id); END;",
                {"client_id": ""},
            )
            cursor.close()
    except Exception:
        pass


def register_session_tagging(engine):
    """Register pool checkout/checkin event listeners for Oracle session tagging.

    Must be called once at startup for both sync and async engines.
    The async engine's underlying sync_engine is used for event registration.
    """
    target = getattr(engine, "sync_engine", engine)
    pool = target.pool

    event.listen(pool, "checkout", _tag_connection)
    event.listen(pool, "checkin", _clear_connection)
    logger.info(
        "Oracle DB session tagging registered (MODULE=%s) — "
        "V$SESSION.MODULE/ACTION/CLIENT_IDENTIFIER will reflect app context for OPSI/DB Management",
        cfg.otel_service_name,
    )
