"""Reports module — OWASP A03: Injection (SQL) + A08: Integrity Failures.

Vulnerabilities:
- Arbitrary SQL execution in custom reports
- Insecure deserialization of report parameters
- No authorization on report execution
- Command injection via export format
"""

import pickle
import base64
import subprocess

from fastapi import APIRouter, Request, Query
from sqlalchemy import text

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.observability import business_metrics
from server.database import get_db

router = APIRouter(prefix="/api/reports", tags=["Reports"])
tracer_fn = get_tracer


@router.get("")
async def list_reports(request: Request):
    """List saved reports."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("reports.list"):
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.reports_list"):
                result = await db.execute(text("SELECT * FROM reports ORDER BY created_at DESC"))
                rows = result.fetchall()
        return {"reports": [dict(r._mapping) for r in rows]}


@router.post("")
async def create_report(request: Request):
    """Create a report — VULN: stores arbitrary SQL query."""
    tracer = tracer_fn()
    body = await request.json()

    with tracer.start_as_current_span("reports.create"):
        async with get_db() as db:
            with tracer.start_as_current_span("db.query.report_insert"):
                await db.execute(
                    text("INSERT INTO reports (name, report_type, query, parameters, created_by) "
                         "VALUES (:n, :t, :q, :p, :cb)"),
                    {
                        "n": body.get("name", ""),
                        "t": body.get("report_type", "custom"),
                        "q": body.get("query", ""),  # VULN: arbitrary SQL stored
                        "p": body.get("parameters", ""),
                        "cb": body.get("created_by", 1),
                    }
                )
        business_metrics.record_report_created(report_type=body.get("report_type", "custom"))
        return {"status": "created"}


@router.post("/execute")
async def execute_report(request: Request):
    """Execute a custom report — VULN: arbitrary SQL execution."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("reports.execute") as span:
        query = body.get("query", "")
        span.set_attribute("reports.query_preview", query[:200])

        # Detect dangerous SQL
        dangerous = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE"]
        if any(d in query.upper() for d in dangerous):
            with security_span("sqli", severity="critical",
                             payload=query, source_ip=client_ip):
                log_security_event("sqli", "critical",
                    "Dangerous SQL in custom report execution",
                    source_ip=client_ip, payload=query)

        async with get_db() as db:
            with tracer.start_as_current_span("db.query.report_execute"):
                try:
                    # VULN: Executes arbitrary SQL from user input
                    result = await db.execute(text(query))
                    rows = result.fetchall()
                    data = [dict(r._mapping) for r in rows]
                except Exception as e:
                    data = []
                    return {"error": f"Query failed: {str(e)}", "query": query}  # VULN: error leak

        business_metrics.record_report_executed()
        push_log("WARNING", f"Custom report executed: {query[:100]}",
                 **{"reports.query": query[:200], "http.client_ip": client_ip})
        return {"data": data, "row_count": len(data)}


@router.post("/import")
async def import_report_config(request: Request):
    """Import report config — VULN: insecure deserialization (pickle)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()

    with tracer.start_as_current_span("reports.import") as span:
        encoded_data = body.get("data", "")

        with security_span("deserialization", severity="critical",
                         payload=encoded_data[:200], source_ip=client_ip):
            log_security_event("deserialization", "critical",
                "Pickle deserialization of user-provided data",
                source_ip=client_ip, payload=encoded_data[:100])

        try:
            # VULN: Insecure deserialization — pickle.loads on user data
            decoded = base64.b64decode(encoded_data)
            config = pickle.loads(decoded)  # CRITICAL VULN
            return {"status": "imported", "config": str(config)}
        except Exception as e:
            return {"error": f"Import failed: {str(e)}"}


@router.get("/export")
async def export_report(
    request: Request,
    report_id: int = Query(description="Report ID"),
    format: str = Query(default="csv", description="Export format"),
):
    """Export report — VULN: command injection in format parameter."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("reports.export") as span:
        span.set_attribute("reports.export_format", format)

        # VULN: Command injection via format parameter
        if any(c in format for c in [";", "|", "&", "`", "$", "(", ")"]):
            with security_span("command_injection", severity="critical",
                             payload=format, source_ip=client_ip):
                log_security_event("command_injection", "critical",
                    "Command injection attempt in export format",
                    source_ip=client_ip, payload=format)

        # VULN: Shell command with user input
        cmd = f"echo 'Report {report_id}' | head -1"  # simplified; real vuln would use format
        try:
            output = subprocess.check_output(cmd, shell=True, timeout=5).decode()  # VULN
        except Exception as e:
            output = str(e)

        return {"report_id": report_id, "format": format, "preview": output}
