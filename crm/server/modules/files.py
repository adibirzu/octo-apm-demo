"""File management module — OWASP A04: Insecure Design + A01: Broken Access Control.

Vulnerabilities:
- Unrestricted file upload (no type/size validation)
- Path traversal in file download
- XXE in XML file processing
- SSRF via URL-based file import
"""

import os
import tempfile

from fastapi import APIRouter, Request, UploadFile, File, Query
from fastapi.responses import FileResponse
import httpx

from server.observability.otel_setup import get_tracer
from server.observability.security_spans import security_span
from server.observability.logging_sdk import log_security_event, push_log
from server.observability import business_metrics

router = APIRouter(prefix="/api/files", tags=["File Management"])
tracer_fn = get_tracer

UPLOAD_DIR = tempfile.mkdtemp(prefix="crm_uploads_")


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """Upload file — VULN: no type validation, no size limit, no malware scan."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("files.upload") as span:
        span.set_attribute("files.filename", file.filename or "unknown")
        span.set_attribute("files.content_type", file.content_type or "unknown")

        # VULN: No file type restriction
        dangerous_extensions = [".exe", ".bat", ".sh", ".php", ".jsp", ".py", ".ps1"]
        if file.filename and any(file.filename.lower().endswith(ext) for ext in dangerous_extensions):
            with security_span("file_upload", severity="high",
                             payload=file.filename, source_ip=client_ip):
                log_security_event("file_upload", "high",
                    f"Dangerous file upload: {file.filename}",
                    source_ip=client_ip, payload=file.filename)

        # VULN: Saves with original filename (path traversal possible)
        filepath = os.path.join(UPLOAD_DIR, file.filename or "unnamed")
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        business_metrics.record_file_upload(content_type=file.content_type or "unknown")
        push_log("INFO", f"File uploaded: {file.filename}", **{
            "files.filename": file.filename,
            "files.size_bytes": len(content),
        })
        return {"status": "uploaded", "filename": file.filename, "size": len(content)}


@router.get("/download")
async def download_file(request: Request, path: str = Query(description="File path")):
    """Download file — VULN: path traversal."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"

    with tracer.start_as_current_span("files.download") as span:
        span.set_attribute("files.requested_path", path)

        # VULN: Path traversal — no sanitization of '..'
        if ".." in path or path.startswith("/"):
            with security_span("path_traversal", severity="critical",
                             payload=path, source_ip=client_ip):
                log_security_event("path_traversal", "critical",
                    f"Path traversal attempt: {path}",
                    source_ip=client_ip, payload=path)

        # VULN: Direct file access without path validation
        business_metrics.record_file_download()
        filepath = os.path.join(UPLOAD_DIR, path)
        if os.path.exists(filepath):
            return FileResponse(filepath)
        return {"error": "File not found", "path": filepath}  # VULN: path disclosure


@router.post("/parse-xml")
async def parse_xml(request: Request):
    """Parse XML data — VULN: XXE (XML External Entity)."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.body()

    with tracer.start_as_current_span("files.parse_xml") as span:
        xml_content = body.decode("utf-8", errors="replace")

        # Detect XXE patterns
        if "<!ENTITY" in xml_content or "<!DOCTYPE" in xml_content:
            with security_span("xxe", severity="critical",
                             payload=xml_content[:500], source_ip=client_ip):
                log_security_event("xxe", "critical",
                    "XXE attempt in XML parsing",
                    source_ip=client_ip, payload=xml_content[:300])

        try:
            from lxml import etree
            # VULN: XXE — parser allows external entities
            parser = etree.XMLParser(resolve_entities=True, no_network=False)
            tree = etree.fromstring(body, parser=parser)
            result = etree.tostring(tree, pretty_print=True).decode()
            return {"status": "parsed", "result": result}
        except Exception as e:
            return {"error": f"XML parsing failed: {str(e)}"}  # VULN: error details


@router.post("/import-url")
async def import_from_url(request: Request):
    """Import file from URL — VULN: SSRF."""
    tracer = tracer_fn()
    client_ip = request.client.host if request.client else "unknown"
    body = await request.json()
    url = body.get("url", "")

    with tracer.start_as_current_span("files.import_url") as span:
        span.set_attribute("files.import_url", url)

        # Detect SSRF patterns
        internal_patterns = ["localhost", "127.0.0.1", "169.254.169.254", "10.", "192.168.", "172."]
        if any(p in url.lower() for p in internal_patterns):
            with security_span("ssrf", severity="critical",
                             payload=url, source_ip=client_ip):
                log_security_event("ssrf", "critical",
                    f"SSRF attempt targeting internal resource: {url}",
                    source_ip=client_ip, payload=url)

        # VULN: SSRF — fetches arbitrary URL without validation
        try:
            resp = httpx.get(url, timeout=10.0, follow_redirects=True)
            return {
                "status": "imported",
                "url": url,
                "status_code": resp.status_code,
                "content_length": len(resp.content),
                "headers": dict(resp.headers),  # VULN: leaks response headers
            }
        except Exception as e:
            return {"error": f"Import failed: {str(e)}"}
