"""Security span helper — enriches OTel traces with MITRE ATT&CK + OWASP attributes.

When running with the shared platform libraries available, uses shared.security_mappings for canonical
MITRE/OWASP definitions. Falls back to local definitions for standalone use.
"""

from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from server.observability.otel_setup import get_tracer


def _build_maps():
    """Build MITRE_MAP and OWASP_MAP, preferring shared canonical source."""
    try:
        from shared.security_mappings import VULNERABILITY_MAP
        # Convert dataclass-based canonical map to tuple format for backward compat.
        mitre = {}
        owasp = {}
        for vuln_type, mapping in VULNERABILITY_MAP.items():
            m = mapping.mitre
            mitre[vuln_type] = (m.technique_id, m.tactic, m.technique_name)
            owasp[vuln_type] = f"{mapping.owasp.code}-{mapping.owasp.name}"
        return mitre, owasp
    except ImportError:
        pass

    # Standalone fallback: local definitions
    # MITRE ATT&CK mapping: vuln_type -> (technique_id, tactic, technique_name)
    mitre = {
        "sqli":             ("T1190", "initial-access", "Exploit Public-Facing Application"),
        "xss_reflected":    ("T1059.007", "execution", "JavaScript Execution"),
        "xss_stored":       ("T1059.007", "execution", "JavaScript Execution"),
        "xss_dom":          ("T1059.007", "execution", "JavaScript Execution"),
        "xxe":              ("T1611", "execution", "XML External Entity Processing"),
        "ssrf":             ("T1090", "command-and-control", "Server-Side Request Forgery"),
        "idor":             ("T1078", "privilege-escalation", "Valid Accounts / Broken Access"),
        "path_traversal":   ("T1083", "discovery", "File and Directory Discovery"),
        "command_injection":("T1059", "execution", "Command and Scripting Interpreter"),
        "ssti":             ("T1059", "execution", "Server-Side Template Injection"),
        "csrf":             ("T1557", "credential-access", "Cross-Site Request Forgery"),
        "broken_auth":      ("T1110", "credential-access", "Brute Force"),
        "jwt_bypass":       ("T1539", "credential-access", "Steal Web Session Cookie"),
        "mass_assignment":  ("T1565", "impact", "Data Manipulation"),
        "nosql_injection":  ("T1190", "initial-access", "NoSQL Injection"),
        "ldap_injection":   ("T1190", "initial-access", "LDAP Injection"),
        "deserialization":  ("T1055", "defense-evasion", "Insecure Deserialization"),
        "file_upload":      ("T1105", "command-and-control", "Ingress Tool Transfer"),
        "open_redirect":    ("T1566.002", "initial-access", "Phishing via Link"),
        "security_misconfig": ("T1562", "defense-evasion", "Impair Defenses"),
        "sensitive_data":   ("T1552", "credential-access", "Unsecured Credentials"),
        "rate_limit_bypass":("T1110.003", "credential-access", "Password Spraying"),
        "privilege_escalation": ("T1068", "privilege-escalation", "Exploitation for Privilege Escalation"),
        "log_injection":    ("T1070", "defense-evasion", "Indicator Removal"),
        "cache_poisoning":  ("T1557", "credential-access", "Adversary-in-the-Middle"),
    }
    owasp = {
        "sqli":             "A03:2021-Injection",
        "xss_reflected":    "A03:2021-Injection",
        "xss_stored":       "A03:2021-Injection",
        "xss_dom":          "A03:2021-Injection",
        "xxe":              "A05:2021-Security Misconfiguration",
        "ssrf":             "A10:2021-SSRF",
        "idor":             "A01:2021-Broken Access Control",
        "path_traversal":   "A01:2021-Broken Access Control",
        "command_injection":"A03:2021-Injection",
        "ssti":             "A03:2021-Injection",
        "csrf":             "A01:2021-Broken Access Control",
        "broken_auth":      "A07:2021-Identification and Authentication Failures",
        "jwt_bypass":       "A02:2021-Cryptographic Failures",
        "mass_assignment":  "A04:2021-Insecure Design",
        "deserialization":  "A08:2021-Software and Data Integrity Failures",
        "file_upload":      "A04:2021-Insecure Design",
        "open_redirect":    "A01:2021-Broken Access Control",
        "security_misconfig": "A05:2021-Security Misconfiguration",
        "sensitive_data":   "A02:2021-Cryptographic Failures",
        "rate_limit_bypass":"A07:2021-Identification and Authentication Failures",
        "privilege_escalation": "A01:2021-Broken Access Control",
        "log_injection":    "A09:2021-Security Logging and Monitoring Failures",
        "cache_poisoning":  "A05:2021-Security Misconfiguration",
    }
    return mitre, owasp


MITRE_MAP, OWASP_MAP = _build_maps()


@contextmanager
def security_span(
    vuln_type: str,
    severity: str = "medium",
    payload: str = "",
    source_ip: str = "",
    username: str = "",
    extra_attrs: dict | None = None,
):
    """Create a span enriched with security/attack metadata."""
    tracer = get_tracer()
    mitre = MITRE_MAP.get(vuln_type, ("T0000", "unknown", "Unknown"))
    owasp = OWASP_MAP.get(vuln_type, "Unknown")

    span_name = f"ATTACK:{vuln_type.upper()}"

    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("security.attack.detected", True)
        span.set_attribute("security.attack.type", vuln_type)
        span.set_attribute("security.attack.severity", severity)
        span.set_attribute("security.attack.mitre_id", mitre[0])
        span.set_attribute("security.attack.mitre_tactic", mitre[1])
        span.set_attribute("security.attack.mitre_technique", mitre[2])
        span.set_attribute("security.attack.owasp", owasp)
        if payload:
            span.set_attribute("security.attack.payload", payload[:512])
        if source_ip:
            span.set_attribute("security.source_ip", source_ip)
        if username:
            span.set_attribute("security.username", username)
        if extra_attrs:
            for k, v in extra_attrs.items():
                span.set_attribute(k, v)
        span.set_status(StatusCode.ERROR, f"Security event: {vuln_type}")
        # Record security event as a metric for alerting
        try:
            from server.observability.business_metrics import record_security_event
            record_security_event(vuln_type, severity)
        except Exception:
            pass  # metrics not yet initialized during startup
        yield span
