"""Oracle DB session tagging for OPSI and DB Management correlation.

Sets MODULE, ACTION, and CLIENT_IDENTIFIER on Oracle DB connections so that
OCI Operations Insights (OPSI), DB Management SQL Performance, and V$SESSION
can correlate SQL execution back to specific application requests and APM traces.

This is the critical bridge between APM traces and database performance data:
  - MODULE = service name (e.g., 'octo-drone-shop')
  - ACTION = HTTP route or operation (e.g., 'GET /api/products')
  - CLIENT_IDENTIFIER = trace_id for APM drilldown
"""

import logging
from contextvars import ContextVar

from sqlalchemy import event

from server.config import cfg

logger = logging.getLogger(__name__)

_db_action: ContextVar[str] = ContextVar("db_action", default="")
_db_client_id: ContextVar[str] = ContextVar("db_client_id", default="")


def set_db_context(action: str = "", client_identifier: str = ""):
    """Set the DB context for the current request (called from middleware)."""
    _db_action.set(action[:64])
    _db_client_id.set(client_identifier[:64])


def _tag_connection(dbapi_connection, connection_record, connection_proxy):
    """SQLAlchemy pool checkout event — tag the Oracle session."""
    try:
        action = _db_action.get("")
        client_id = _db_client_id.get("")
        module = cfg.otel_service_name[:48]

        if hasattr(dbapi_connection, 'module'):
            dbapi_connection.module = module
            dbapi_connection.action = action or "idle"
            dbapi_connection.clientinfo = cfg.app_version[:64]
            dbapi_connection.client_identifier = client_id or ""
        else:
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
        logger.debug("DB session tagging failed", exc_info=True)


def _clear_connection(dbapi_connection, connection_record):
    """SQLAlchemy pool checkin event — reset session tags for pool reuse."""
    try:
        if hasattr(dbapi_connection, 'module'):
            dbapi_connection.action = "idle"
            dbapi_connection.client_identifier = ""
    except Exception:
        pass


def register_session_tagging(engine):
    """Register pool checkout/checkin event listeners for Oracle session tagging."""
    if cfg.use_postgres:
        return  # Only tag Oracle sessions

    target = getattr(engine, "sync_engine", engine)
    pool = target.pool

    event.listen(pool, "checkout", _tag_connection)
    event.listen(pool, "checkin", _clear_connection)
    logger.info(
        "Oracle DB session tagging registered (MODULE=%s) — "
        "V$SESSION.MODULE/ACTION/CLIENT_IDENTIFIER for OPSI/DB Management",
        cfg.otel_service_name,
    )
