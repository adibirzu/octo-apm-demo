"""Security span helpers — MITRE ATT&CK + OWASP classification for MuShop."""

from server.observability.otel_setup import get_tracer

MITRE_MAP = {
    "sqli":           ("T1190", "Exploit Public-Facing Application", "Initial Access"),
    "xss":            ("T1059.007", "JavaScript", "Execution"),
    "xxe":            ("T1203", "Exploitation for Client Execution", "Execution"),
    "ssrf":           ("T1090", "Proxy", "Command and Control"),
    "path_traversal": ("T1083", "File and Directory Discovery", "Discovery"),
    "idor":           ("T1078", "Valid Accounts", "Defense Evasion"),
    "ssti":           ("T1059", "Command and Scripting Interpreter", "Execution"),
    "csrf":           ("T1185", "Browser Session Hijacking", "Collection"),
    "auth_bypass":    ("T1556", "Modify Authentication Process", "Credential Access"),
    "mass_assign":    ("T1098", "Account Manipulation", "Persistence"),
    "brute_force":    ("T1110", "Brute Force", "Credential Access"),
    "deserialization": ("T1059", "Command and Scripting Interpreter", "Execution"),
    "cmd_injection":  ("T1059.004", "Unix Shell", "Execution"),
    "info_disclosure": ("T1087", "Account Discovery", "Discovery"),
    "captcha_bypass": ("T1078", "Valid Accounts", "Defense Evasion"),
    "rate_limit":     ("T1498", "Network Denial of Service", "Impact"),
}

OWASP_MAP = {
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


def security_span(vuln_type: str, *, severity: str = "medium",
                  payload: str = "", source_ip: str = "",
                  endpoint: str = ""):
    tracer = get_tracer("security")
    mitre = MITRE_MAP.get(vuln_type, ("T0000", "Unknown", "Unknown"))
    owasp = OWASP_MAP.get(vuln_type, ("A00:2021", "Unknown"))

    span = tracer.start_span(f"ATTACK:{vuln_type.upper()}")
    span.set_attributes({
        "security.event": True,
        "security.vuln_type": vuln_type,
        "security.severity": severity,
        "security.payload": payload[:500],
        "security.source_ip": source_ip,
        "security.endpoint": endpoint,
        "mitre.technique_id": mitre[0],
        "mitre.technique_name": mitre[1],
        "mitre.tactic": mitre[2],
        "owasp.category": owasp[0],
        "owasp.name": owasp[1],
    })
    span.end()
    return span
