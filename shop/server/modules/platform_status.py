"""Aggregated platform status — one endpoint gives operator the
version + health of every in-cluster service.

GET /api/platform/status returns:
    {
      "services": [
        {"name":"octo-drone-shop","reachable":true,"image_tag":"...","ready":true},
        {"name":"enterprise-crm-portal","reachable":true,...},
        ...
      ],
      "overall_ok": true
    }

Consumers:
- Operators (curl from laptop during cutover).
- Rollout validator — sanity check every service in one shot.
- Workshop Lab 01 (smoke).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])


# Map of service name → in-cluster base URL. Override via env for VM
# deployments where everything talks to localhost:port.
_DEFAULT_TARGETS: dict[str, str] = {
    "octo-drone-shop": "http://localhost:8080",
    "enterprise-crm-portal": "http://enterprise-crm-portal.octo-backend-prod.svc.cluster.local:8080",
    "octo-load-control": "http://load-control.octo-load-control:8080",
    "octo-remediator": "http://remediator.octo-remediator:8080",
    "octo-object-pipeline": "http://object-pipeline.octo-object:8080",
    "octo-otel-gateway": "http://gateway.octo-otel:13133",
    "octo-async-worker": "",   # no HTTP surface
    "octo-cache": "",          # Redis, no HTTP
    "octo-traffic-generator": "",
    "octo-browser-runner": "",
    "octo-edge-fuzz": "",
}


def _targets() -> dict[str, str]:
    overrides = os.getenv("OCTO_PLATFORM_STATUS_TARGETS", "")
    if not overrides:
        return _DEFAULT_TARGETS
    # Format: name1=url1,name2=url2,...
    out = dict(_DEFAULT_TARGETS)
    for chunk in overrides.split(","):
        if "=" in chunk:
            n, u = chunk.split("=", 1)
            out[n.strip()] = u.strip()
    return out


async def _probe(name: str, base: str) -> dict[str, Any]:
    if not base:
        return {"name": name, "reachable": False, "reason": "no-http-surface"}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            # Try /api/version first (richer), fall back to /health
            for path in ("/api/version", "/health", "/ready", "/"):
                try:
                    r = await client.get(f"{base}{path}")
                    if r.status_code < 500:
                        body: dict[str, Any] = {}
                        try:
                            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                        except Exception:
                            body = {}
                        return {
                            "name": name,
                            "reachable": True,
                            "status_code": r.status_code,
                            "path": path,
                            "image_tag": body.get("image_tag", ""),
                            "git_sha": body.get("git_sha", ""),
                            "schema_version": body.get("schema_version", ""),
                        }
                except httpx.HTTPError:
                    continue
    except Exception as exc:
        return {"name": name, "reachable": False, "error": str(exc)}
    return {"name": name, "reachable": False, "error": "no route returned"}


@router.get("/api/platform/status")
async def platform_status() -> dict[str, Any]:
    targets = _targets()
    results = await asyncio.gather(*(_probe(n, u) for n, u in targets.items()))
    reachable_with_http = [r for r in results if r.get("reachable")]
    expected = [n for n, u in targets.items() if u]
    overall_ok = len(reachable_with_http) == len(expected)
    return {
        "services": results,
        "overall_ok": overall_ok,
        "summary": {
            "total": len(results),
            "reachable": len(reachable_with_http),
            "expected_with_http": len(expected),
        },
    }
