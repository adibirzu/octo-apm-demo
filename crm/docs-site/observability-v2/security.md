# Security hardening

- Security headers middleware — HSTS, CSP with per-request nonce,
  `X-Frame-Options` allowing iframe embedding only from `OPS_DOMAIN`.
- Request-id middleware — `X-Request-Id` generated if absent and echoed
  on the response, consumed by the WAF parser for log correlation.
- Role-gated admin surfaces via `server/security/auth_deps.py`.
  `chaos-operator` is enforced on `/admin/chaos` and `/api/admin/chaos/*`.
- OIDC session cookies: `Secure`, `HttpOnly`, `SameSite=Lax`.
- CI gates: `.github/workflows/security-gates.yml`
  (bandit, pip-audit, ruff S-rules, semgrep OWASP, gitleaks, tflint, trivy).
