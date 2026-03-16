"""SQLAlchemy event listeners to enrich OTel spans with db.statement, Oracle SQL_ID,
and topology attributes for OCI APM Trace Explorer.

Attaches to before_cursor_execute so that EVERY query (sync or async, raw SQL or ORM)
gets DbStatement, DbOracleSqlId, and peer.service attributes on the active
OpenTelemetry span — making them visible in APM Trace Explorer and Topology view.
"""

import hashlib
import logging
import struct

from sqlalchemy import event
from opentelemetry import trace

from server.config import cfg

logger = logging.getLogger(__name__)

# Oracle base-32 alphabet used for SQL_ID encoding (note: no 'e', 'i', 'l', 'o')
_ORACLE_B32 = "0123456789abcdfghjkmnpqrstuvwxyz"


def compute_oracle_sql_id(sql_text: str) -> str:
    """Compute Oracle SQL_ID from SQL text using the MD5-based algorithm.

    Oracle computes SQL_ID as:
    1. MD5(sql_text + '\\0')
    2. Take last 8 bytes as big-endian uint64
    3. Encode in Oracle's base-32 alphabet → 13 chars
    """
    md5_hash = hashlib.md5((sql_text + "\0").encode("utf-8")).digest()
    # Last 8 bytes as unsigned 64-bit big-endian
    msb, lsb = struct.unpack(">II", md5_hash[8:16])
    sqln = (msb << 32) | lsb

    # Encode as 13-char base-32
    result = []
    for _ in range(13):
        result.append(_ORACLE_B32[sqln & 0x1F])
        sqln >>= 5
    return "".join(reversed(result))


def _enrich_span_before_execute(conn, cursor, statement, parameters, context, executemany):
    """SQLAlchemy before_cursor_execute listener — sets db.statement, db.oracle.sql_id,
    and topology attributes for OCI APM."""
    span = trace.get_current_span()
    if not span or not span.is_recording():
        return

    if statement:
        import re
        normalized = re.sub(r"\s+", " ", statement.strip())
        sql_id = compute_oracle_sql_id(normalized)
        # OCI APM Trace Explorer SQL drilldown (PascalCase required by APM)
        span.set_attribute("DbStatement", normalized)
        span.set_attribute("DbOracleSqlId", sql_id)
        # Standard OTel semantic conventions (kept for compatibility)
        span.set_attribute("db.statement", normalized[:4096])
        span.set_attribute("db.oracle.sql_id", sql_id)

    # Standard OTel semantic conventions for DB spans
    span.set_attribute("db.system", "oracle")
    span.set_attribute("db.name", cfg.oracle_dsn or "oracle-atp")
    span.set_attribute("db.user", cfg.oracle_user or "ADMIN")
    # APM topology: component identifies the technology in the span list
    span.set_attribute("component", "oracle")

    # Topology attributes — these make Oracle ATP appear as a separate node in APM topology
    span.set_attribute("peer.service", f"OracleATP:{cfg.oracle_dsn}" if cfg.oracle_dsn else "OracleATP")
    span.set_attribute("server.address", cfg.oracle_dsn or "oracle-atp")
    span.set_attribute("db.connection_string", cfg.oracle_dsn or "")
    if cfg.atp_ocid:
        span.set_attribute("db.oracle.atp_ocid", cfg.atp_ocid)


def register_db_span_events(engine):
    """Register SQLAlchemy event listeners on an engine (sync or async's sync_engine).

    This must be called once at startup so that all queries automatically
    populate DbStatement, DbOracleSqlId, and topology in OCI APM Trace Explorer.
    """
    # For async engines, get the underlying sync engine
    target = getattr(engine, "sync_engine", engine)

    event.listen(target, "before_cursor_execute", _enrich_span_before_execute)
    logger.info("Registered DB span enrichment events (db.statement + db.oracle.sql_id + topology)")
