"""OCI Vulnerability Scanning Service (VSS) integration.

Fetches host and container scan results from OCI VSS and surfaces them
in the 360 observability dashboard for MELTS-Security correlation.

When deployed on OKE, uses resource principal auth. Falls back to
config file auth for local development.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from server.config import cfg

logger = logging.getLogger(__name__)

_scan_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 5 minutes


def _get_vss_client():
    """Lazy-init OCI VulnerabilityScanning client."""
    try:
        import oci
        auth_mode = cfg.oci_auth_mode.lower()
        if auth_mode == "resource_principal":
            signer = oci.auth.signers.get_resource_principals_signer()
            return oci.vulnerability_scanning.VulnerabilityScanningClient(config={}, signer=signer)
        elif auth_mode == "instance_principal":
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            return oci.vulnerability_scanning.VulnerabilityScanningClient(config={}, signer=signer)
        else:
            config = oci.config.from_file()
            return oci.vulnerability_scanning.VulnerabilityScanningClient(config)
    except Exception as exc:
        logger.debug("VSS client init failed: %s", exc)
        return None


def get_vulnerability_summary() -> dict[str, Any]:
    """Return cached vulnerability scan summary.

    Returns a dict with host_scans, container_scans, and vulnerability counts
    suitable for the 360 observability dashboard.
    """
    with _cache_lock:
        if _scan_cache and time.time() - _scan_cache.get("_ts", 0) < _CACHE_TTL:
            return _scan_cache

    compartment_id = cfg.oci_compartment_id
    if not compartment_id:
        return {"configured": False, "reason": "OCI_COMPARTMENT_ID not set"}

    client = _get_vss_client()
    if client is None:
        return {"configured": False, "reason": "VSS client unavailable"}

    result: dict[str, Any] = {"configured": True}

    # Host scans
    try:
        host_scans = client.list_host_scan_recipes(compartment_id=compartment_id)
        result["host_scan_recipes"] = len(host_scans.data.items) if host_scans.data.items else 0
    except Exception as exc:
        result["host_scan_recipes"] = 0
        result["host_scan_error"] = str(exc)

    # Container scans
    try:
        container_scans = client.list_container_scan_recipes(compartment_id=compartment_id)
        result["container_scan_recipes"] = len(container_scans.data.items) if container_scans.data.items else 0
    except Exception as exc:
        result["container_scan_recipes"] = 0
        result["container_scan_error"] = str(exc)

    # Host vulnerabilities
    try:
        vulns = client.list_host_vulnerabilities(compartment_id=compartment_id, limit=100)
        items = vulns.data.items or []
        result["host_vulnerabilities"] = {
            "total": len(items),
            "critical": sum(1 for v in items if getattr(v, "severity", "") == "CRITICAL"),
            "high": sum(1 for v in items if getattr(v, "severity", "") == "HIGH"),
            "medium": sum(1 for v in items if getattr(v, "severity", "") == "MEDIUM"),
            "low": sum(1 for v in items if getattr(v, "severity", "") == "LOW"),
        }
    except Exception as exc:
        result["host_vulnerabilities"] = {"total": 0, "error": str(exc)}

    # Container image vulnerabilities
    try:
        container_vulns = client.list_container_scan_results(compartment_id=compartment_id, limit=20)
        items = container_vulns.data.items or []
        result["container_scan_results"] = {
            "total": len(items),
            "latest": [
                {
                    "repository": getattr(r, "repository", ""),
                    "highest_severity": getattr(r, "highest_problem_severity", "NONE"),
                    "problem_count": getattr(r, "problem_count", 0),
                }
                for r in items[:5]
            ],
        }
    except Exception as exc:
        result["container_scan_results"] = {"total": 0, "error": str(exc)}

    result["_ts"] = time.time()
    with _cache_lock:
        _scan_cache.update(result)

    return result
