# Security Events

## MITRE ATT&CK Security Spans

The application detects and classifies 19 vulnerability types with MITRE ATT&CK technique IDs and OWASP 2021 codes:

| Vulnerability | MITRE ID | OWASP Code | Severity |
|---|---|---|---|
| SQL Injection | T1190 | A03:2021 | Critical |
| XSS | T1059.007 | A03:2021 | High |
| Command Injection | T1059.004 | A03:2021 | Critical |
| SSRF | T1090 | A10:2021 | High |
| Path Traversal | T1083 | A01:2021 | High |
| IDOR | T1078 | A01:2021 | Medium |
| Brute Force | T1110 | A07:2021 | High |
| CSRF | T1185 | A01:2021 | Medium |
| Auth Bypass | T1556 | A07:2021 | Critical |
| Mass Assignment | T1098 | A04:2021 | Medium |
| Rate Limit | T1498 | A04:2021 | High |

Each detected attack creates:

1. **APM Span** — `ATTACK:<type>` with all classification attributes
2. **Structured Log** — via OCI Logging SDK with `oracleApmTraceId`
3. **Database Record** — in `security_events` table with trace linkage

## OCI WAF Protection Rules

| Rule | CRS ID | Mode | Rate Limit |
|---|---|---|---|
| SQL Injection | 941100 | BLOCK | - |
| XSS | 942100 | BLOCK | - |
| Command Injection | 932100 | BLOCK | - |
| Path Traversal | 930100 | BLOCK | - |
| Global rate limit | - | BLOCK | 120 req/min per IP |
| Login rate limit | - | BLOCK | 10 req/5min per IP |
| Checkout rate limit | - | BLOCK | 5 req/min per IP |

## OCI Cloud Guard

- **Target**: Compartment-scoped with Activity + Configuration detectors
- **Responder recipes**: Auto-remediation for detected problems
- **Security score**: Tracked and visible in OCI Console

## OCI Security Zones

Compliance policies enforced at compartment level:

- ATP databases must use Vault-managed encryption keys
- Object Storage buckets must be private
- Network Security Groups must restrict ingress

## OCI Vault

Secrets managed with HSM-backed AES-256 master key:

- `AUTH_TOKEN_SECRET` — Bearer token signing key
- `INTERNAL_SERVICE_KEY` — Service-to-service auth
- `ORACLE_PASSWORD` — ATP admin password

## OCI Vulnerability Scanning (VSS)

Host and container scan results surfaced in the 360 observability dashboard via the `/api/observability/360` endpoint.
