"""Database dialect compatibility — provides SQL fragments that work on both Oracle and PostgreSQL.

Detects the database dialect from the connection URL at import time and
exposes constants/helpers that modules can use instead of hardcoding
dialect-specific SQL.
"""

from server.config import cfg

# Detect dialect from the DATABASE_URL
_url = (cfg.database_url or "").lower()
IS_ORACLE = "oracle" in _url or bool(cfg.oracle_dsn)
IS_POSTGRES = not IS_ORACLE

# ── SQL fragments ────────────────────────────────────────────────

# Health-check query
HEALTH_CHECK_SQL = "SELECT 1 FROM dual" if IS_ORACLE else "SELECT 1"

# Boolean literals — ORM uses Integer (not Boolean) for Oracle compatibility,
# so always compare with 1/0 on both dialects.
BOOL_TRUE = "1"
BOOL_FALSE = "0"

# Database version query
DB_VERSION_SQL = (
    "SELECT banner FROM v$version WHERE ROWNUM = 1"
    if IS_ORACLE
    else "SELECT version()"
)

# Active connections query
DB_ACTIVE_CONNECTIONS_SQL = (
    "SELECT count(*) FROM v$session WHERE status = 'ACTIVE'"
    if IS_ORACLE
    else "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
)


def paginate(query: str, offset: int, limit: int) -> str:
    """Append pagination clause (SQL:2008 standard — works on both dialects)."""
    return f"{query} OFFSET {int(offset)} ROWS FETCH NEXT {int(limit)} ROWS ONLY"
