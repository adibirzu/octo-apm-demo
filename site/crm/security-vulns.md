# Security Vulnerabilities

The CRM Portal includes **intentional OWASP Top 10 vulnerabilities** for security training. Every exploitation attempt generates security spans with MITRE ATT&CK classification.

!!! warning "Intentional Vulnerabilities"
    These vulnerabilities exist for **security training and observability demonstration only**. The Drone Shop implements production-grade security controls.

## OWASP Top 10 (2021) Coverage

| OWASP | Category | Affected Modules | Example |
|---|---|---|---|
| **A01** | Broken Access Control | customers, orders, invoices, admin | IDOR: `GET /api/customers/{id}` without auth |
| **A02** | Cryptographic Failures | auth, api_keys | Weak MD5 session hashing, timing attack on API key validation |
| **A03** | Injection | customers, products, reports, files | SQLi in search/sort, command injection in reports, XXE in files |
| **A04** | Insecure Design | orders, invoices | Price manipulation, no request signing |
| **A05** | Security Misconfiguration | products, admin | Verbose errors, config endpoint, debug info |
| **A07** | Auth Failures | auth, api_keys | Brute force (no rate limit), mass assignment (role) |
| **A08** | Data Integrity | reports | Pickle deserialization |
| **A09** | Logging Failures | tickets | Log injection via description |
| **A10** | SSRF | files | `POST /api/files/import-url` |

## Security Span Detection

Every detected attack generates:

```
ATTACK:{TYPE}
├── security.vuln_type: "sqli"
├── security.severity: "critical"
├── mitre.technique_id: "T1190"
├── mitre.tactic: "initial-access"
├── owasp.category: "A03:2021"
├── security.payload: "1' OR '1'='1"
├── security.source_ip: "10.244.0.1"
└── status: ERROR
```

**24 vulnerability types detected**: sqli, xss_reflected, xss_stored, xss_dom, xxe, ssrf, idor, path_traversal, command_injection, ssti, csrf, broken_auth, jwt_bypass, mass_assignment, brute_force, deserialization, captcha_bypass, rate_limit, info_disclosure, open_redirect, log_injection, file_upload, timing_attack, privilege_escalation

## Demo Scenarios

### SQL Injection
```bash
curl "https://crm.octodemo.cloud/api/customers?search=1'%20OR%20'1'='1"
# → Parameterized query prevents actual injection
# → Security span: ATTACK:SQLI with full classification
# → Visible in OCI APM → filter security.vuln_type=sqli
```

### XSS
```bash
curl -X POST "https://crm.octodemo.cloud/api/customers" \
  -d '{"name": "Test", "notes": "<script>alert(1)</script>"}'
# → Input stored (intentionally vulnerable)
# → Security span: ATTACK:XSS_STORED
```

### Path Traversal
```bash
curl "https://crm.octodemo.cloud/api/files/download?path=../../etc/passwd"
# → Security span: ATTACK:PATH_TRAVERSAL
```

## Correlation

All security events correlate across the MELTS stack:

1. **APM** → Trace Explorer → filter `security.vuln_type`
2. **Log Analytics** → search `oracleApmTraceId` from the span
3. **Monitoring** → `crm.business.security.events` counter
4. **Cloud Guard** → Problems feed from compartment activity
