# Security Testing Add-On

!!! info "Optional Module"
    Security testing is an **optional add-on** for security workshops and detection training. The CRM Portal is fully secured by default. Enable this module when running security training exercises.

## Purpose

When enabled, the security testing module provides intentional OWASP Top 10 vulnerabilities that generate security spans with MITRE ATT&CK classification. This allows security teams to:

1. **Test detection** — Verify that OCI APM captures attack patterns
2. **Train analysts** — Practice identifying security events in OCI Log Analytics
3. **Validate WAF rules** — Confirm WAF protection rules block common attacks
4. **Demonstrate MELTS correlation** — Show how security events correlate across traces, logs, metrics, and SQL

## OWASP Top 10 Coverage

| OWASP | Category | Detection Span |
|---|---|---|
| A01 | Broken Access Control | `ATTACK:IDOR`, `ATTACK:PRIVILEGE_ESCALATION` |
| A02 | Cryptographic Failures | `ATTACK:TIMING_ATTACK` |
| A03 | Injection | `ATTACK:SQLI`, `ATTACK:XSS_REFLECTED`, `ATTACK:XXE` |
| A04 | Insecure Design | `ATTACK:MASS_ASSIGNMENT` |
| A05 | Security Misconfiguration | `ATTACK:INFO_DISCLOSURE` |
| A07 | Auth Failures | `ATTACK:BRUTE_FORCE` |
| A08 | Data Integrity | `ATTACK:DESERIALIZATION` |
| A09 | Logging Failures | `ATTACK:LOG_INJECTION` |
| A10 | SSRF | `ATTACK:SSRF` |

## Security Span Detection

Every detected attack generates a traced span:

```
ATTACK:{TYPE}
├── security.vuln_type: "sqli"
├── security.severity: "critical"
├── mitre.technique_id: "T1190"
├── mitre.tactic: "initial-access"
├── owasp.category: "A03:2021"
└── status: ERROR
```

24 vulnerability types are detected and classified against both MITRE ATT&CK and OWASP frameworks.

## OCI Correlation Path

1. **APM** → Trace Explorer → filter `security.vuln_type`
2. **Log Analytics** → search `oracleApmTraceId` from the span
3. **Monitoring** → security events counter
4. **Cloud Guard** → Problems feed from compartment activity

## Demo Scenarios

=== "SQL Injection"

    ```bash
    curl "https://crm.example.com/api/customers?search=1'%20OR%20'1'='1"
    # → Security span: ATTACK:SQLI
    # → Visible in OCI APM Trace Explorer
    ```

=== "XSS"

    ```bash
    curl -X POST "https://crm.example.com/api/tickets" \
      -d '{"subject": "<script>alert(1)</script>"}'
    # → Security span: ATTACK:XSS_REFLECTED
    ```

=== "Path Traversal"

    ```bash
    curl "https://crm.example.com/api/files/download?path=../../etc/passwd"
    # → Security span: ATTACK:PATH_TRAVERSAL
    ```
