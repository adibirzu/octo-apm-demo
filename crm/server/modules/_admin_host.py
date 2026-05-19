"""Shared admin-host enforcement helpers.

Single source of truth for the host-bound admin boundary enforced on
admin-only FastAPI surfaces (e.g. `/api/admin/coordinator/*`,
`/api/admin/stress/*`). Do not duplicate this logic in other modules —
import from here.

Phase 5 contract (admin.octodemo.cloud only) and Phase 7 extension
(stress-test surface) both depend on these helpers behaving identically.
A structural test in `tests/test_admin_host_helper.py` asserts that the
coordinator module imports these helpers rather than re-implementing them.
"""
from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

from server.config import cfg

_ADMIN_SURFACE = "admin.octodemo.cloud"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


def _request_host(request: Request) -> str:
    raw_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.hostname
        or ""
    )
    raw_host = raw_host.split(",", 1)[0].strip().lower()
    if raw_host.startswith("[") and "]" in raw_host:
        return raw_host[1:raw_host.index("]")]
    return raw_host.rsplit(":", 1)[0] if ":" in raw_host else raw_host


def _configured_admin_hosts() -> set[str]:
    hosts = {_ADMIN_SURFACE}
    parsed = urlparse(cfg.crm_base_url or "")
    if parsed.hostname:
        hosts.add(parsed.hostname)
    dns_domain = (getattr(cfg, "dns_domain", "") or "").strip()
    if dns_domain:
        hosts.add(f"admin.{dns_domain}")
        hosts.add(f"crm.{dns_domain}")
    return hosts


def _require_admin_host(request: Request) -> str:
    host = _request_host(request)
    if host in _LOCAL_HOSTS or host in _configured_admin_hosts():
        return host
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="OCI Coordinator is only available from admin.octodemo.cloud.",
    )
