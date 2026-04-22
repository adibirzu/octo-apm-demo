# Prerequisites

## Required

| Prerequisite | Purpose |
|---|---|
| `DNS_DOMAIN` | All public URLs derive from this single variable |
| Oracle ATP | Backend database (shared with CRM) |
| OCI APM Domain | Trace collection (create via OCI Console) |
| `AUTH_TOKEN_SECRET` | Bearer token signing (32+ random bytes) |
| OCI OKE Cluster | Container orchestration (for production) |
| Docker | Container build (on x86_64 build VM) |

## Optional

| Prerequisite | Purpose |
|---|---|
| IDCS SSO | `IDCS_DOMAIN_URL`, `IDCS_CLIENT_ID`, `IDCS_CLIENT_SECRET` |
| CRM Integration | `ENTERPRISE_CRM_URL` for cross-service sync |
| Splunk | `SPLUNK_HEC_URL` + `SPLUNK_HEC_TOKEN` for external logging |
| OCI GenAI | `OCI_GENAI_ENDPOINT` + `OCI_GENAI_MODEL_ID` for AI assistant |
| Select AI | `SELECTAI_PROFILE_NAME` for natural language queries |

## OCI Services Used

- **OKE** — Kubernetes cluster
- **ATP** — Autonomous Transaction Processing database
- **APM** — Application Performance Monitoring (traces + RUM)
- **Logging** — Structured log ingestion
- **Monitoring** — Custom metrics and alarms
- **WAF** — Web Application Firewall
- **IAM Identity Domain** — OIDC SSO
- **Vault** — Secret management
- **Cloud Guard** — Security posture monitoring
- **VSS** — Vulnerability Scanning Service
- **Health Checks** — HTTP endpoint monitoring
- **Notifications** — Alarm delivery
