"""Security span helpers — MITRE ATT&CK + OWASP classification for OCTO-CRM-APM.

When running with the shared platform libraries available, uses shared.security_mappings for canonical
MITRE/OWASP definitions. Falls back to local definitions for standalone use.
"""

import json

from sqlalchemy import text

from server.database import sync_engine
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import log_security_event


def _build_maps():
    """Build MITRE_MAP and OWASP_MAP, preferring shared canonical source."""
    try:
        from shared.security_mappings import VULNERABILITY_MAP
        mitre = {}
        owasp = {}
        for vuln_type, mapping in VULNERABILITY_MAP.items():
            m = mapping.mitre
            mitre[vuln_type] = (m.technique_id, m.tactic, m.technique_name)
            owasp[vuln_type] = (mapping.owasp.code, mapping.owasp.name)
        return mitre, owasp
    except ImportError:
        pass

    # Standalone fallback: local definitions
    # MITRE ATT&CK mapping: vuln_type -> (technique_id, tactic, technique_name)
    mitre = {
        "sqli":           ("T1190", "initial-access", "Exploit Public-Facing Application"),
        "xss":            ("T1059.007", "execution", "JavaScript"),
        "xxe":            ("T1203", "execution", "Exploitation for Client Execution"),
        "ssrf":           ("T1090", "command-and-control", "Proxy"),
        "path_traversal": ("T1083", "discovery", "File and Directory Discovery"),
        "idor":           ("T1078", "defense-evasion", "Valid Accounts"),
        "ssti":           ("T1059", "execution", "Command and Scripting Interpreter"),
        "csrf":           ("T1185", "collection", "Browser Session Hijacking"),
        "auth_bypass":    ("T1556", "credential-access", "Modify Authentication Process"),
        "mass_assign":    ("T1098", "persistence", "Account Manipulation"),
        "brute_force":    ("T1110", "credential-access", "Brute Force"),
        "deserialization": ("T1059", "execution", "Command and Scripting Interpreter"),
        "cmd_injection":  ("T1059.004", "execution", "Unix Shell"),
        "info_disclosure": ("T1087", "discovery", "Account Discovery"),
        "captcha_bypass": ("T1078", "defense-evasion", "Valid Accounts"),
        "rate_limit":     ("T1498", "impact", "Network Denial of Service"),
    }
    owasp = {
        "sqli":           ("A03:2021", "Injection"),
        "xss":            ("A03:2021", "Injection"),
        "xxe":            ("A05:2021", "Security Misconfiguration"),
        "ssrf":           ("A10:2021", "Server-Side Request Forgery"),
        "path_traversal": ("A01:2021", "Broken Access Control"),
        "idor":           ("A01:2021", "Broken Access Control"),
        "ssti":           ("A03:2021", "Injection"),
        "csrf":           ("A01:2021", "Broken Access Control"),
        "auth_bypass":    ("A07:2021", "Identification and Authentication Failures"),
        "mass_assign":    ("A04:2021", "Insecure Design"),
        "brute_force":    ("A07:2021", "Identification and Authentication Failures"),
        "deserialization": ("A08:2021", "Software and Data Integrity Failures"),
        "cmd_injection":  ("A03:2021", "Injection"),
        "info_disclosure": ("A02:2021", "Cryptographic Failures"),
        "captcha_bypass": ("A07:2021", "Identification and Authentication Failures"),
        "rate_limit":     ("A04:2021", "Insecure Design"),
    }
    return mitre, owasp


MITRE_MAP, OWASP_MAP = _build_maps()


def _persist_security_event(
    *,
    vuln_type: str,
    severity: str,
    payload: str,
    source_ip: str,
    endpoint: str,
    product_id: int | None,
    session_id: str,
    trace_id: str,
    mitre: tuple[str, str, str],
    owasp: tuple[str, str],
) -> None:
    if sync_engine is None:
        return
    try:
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO security_events "
                    "(attack_type, severity, endpoint, source_ip, payload, product_id, session_id, trace_id, details) "
                    "VALUES (:attack_type, :severity, :endpoint, :source_ip, :payload, :product_id, :session_id, :trace_id, :details)"
                ),
                {
                    "attack_type": vuln_type,
                    "severity": severity,
                    "endpoint": endpoint,
                    "source_ip": source_ip,
                    "payload": payload[:500] if payload else "",
                    "product_id": product_id,
                    "session_id": session_id,
                    "trace_id": trace_id,
                    "details": json.dumps(
                        {
                            "mitre_technique_id": mitre[0],
                            "mitre_tactic": mitre[1],
                            "owasp_category": owasp[0],
                            "owasp_name": owasp[1],
                        }
                    ),
                },
            )
    except Exception:
        # Security telemetry must not break the request path.
        pass


def security_span(
    vuln_type: str,
    *,
    severity: str = "medium",
    payload: str = "",
    source_ip: str = "",
    endpoint: str = "",
    product_id: int | None = None,
    session_id: str = "",
):
    tracer = get_tracer("security")
    mitre = MITRE_MAP.get(vuln_type, ("T0000", "Unknown", "Unknown"))
    owasp = OWASP_MAP.get(vuln_type, ("A00:2021", "Unknown"))

    span = tracer.start_span(f"ATTACK:{vuln_type.upper()}")
    trace_id = ""
    if span and span.get_span_context().trace_id:
        trace_id = format(span.get_span_context().trace_id, "032x")
    span.set_attributes({
        "security.event": True,
        "security.vuln_type": vuln_type,
        "security.severity": severity,
        "security.payload": payload[:500],
        "security.source_ip": source_ip,
        "security.endpoint": endpoint,
        "security.product_id": product_id or 0,
        "security.session_id": session_id or "n/a",
        "mitre.technique_id": mitre[0],
        "mitre.tactic": mitre[1],
        "mitre.technique_name": mitre[2],
        "owasp.category": owasp[0],
        "owasp.name": owasp[1],
    })
    span.end()

    # Push correlated log for OCI Log Analytics (oracleApmTraceId linkage)
    log_security_event(
        vuln_type=vuln_type,
        severity=severity,
        message=f"ATTACK:{vuln_type.upper()} detected on {endpoint}",
        source_ip=source_ip,
        payload=payload,
        endpoint=endpoint,
        mitre_technique_id=mitre[0],
        mitre_tactic=mitre[1],
        owasp_category=owasp[0],
    )
    _persist_security_event(
        vuln_type=vuln_type,
        severity=severity,
        payload=payload,
        source_ip=source_ip,
        endpoint=endpoint,
        product_id=product_id,
        session_id=session_id,
        trace_id=trace_id,
        mitre=mitre,
        owasp=owasp,
    )
    return span
