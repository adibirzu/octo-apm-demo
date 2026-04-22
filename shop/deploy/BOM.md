# Deployment Bill of Materials

Minimal set of tenancy resources, secrets, tools, and container images
required to redeploy the OCTO Drone Shop + Enterprise CRM Portal (and
optionally the OCI Coordinator) from a blank slate. Each row points at
the script that creates or validates it so a new operator can work
top-down without reading code.

The BOM is the authoritative input for:

- `deploy/pre-flight-check.sh` (validates that required env vars are set
  and not placeholder-leaked)
- `deploy/init-tenancy.sh` (creates the OCIR repo, K8s namespace, bootstrap secrets)
- `deploy/oci/ensure_apm.sh` + `ensure_stack_monitoring.sh` (provisions the observability surface)
- `deploy/resource-manager/` (Console-driven subset)
- `deploy/vm/` (unified single-VM path)

---

## 0. Operator workstation prerequisites

| Item | Minimum version | Required by |
|---|---|---|
| `oci` CLI | 3.40+ | init-tenancy, ensure_*.sh |
| `kubectl` | 1.28+ | OKE path |
| `terraform` | **1.6+** | `deploy/terraform/`, RM module, APM module |
| `docker` | 24+ | image build (or SSH to remote x86_64 builder) |
| `envsubst` | gettext 0.21+ | K8s manifest templating |
| `jq` | 1.6+ | output parsing in scripts |
| `python3` | 3.11+ | `tools/create_la_source.py` |
| `gh` CLI | 2.40+ | PR creation, workflow checks |

## 1. OCI tenancy — one-time

| Item | Notes | Stored in |
|---|---|---|
| Tenancy OCID | From the OCI Console → Administration → Tenancy Details | `TF_VAR_tenancy_ocid` at RM plan time |
| Home region | Pick the region that hosts APM + Stack Monitoring | `OCIR_REGION` |
| Object Storage namespace | Same as OCIR namespace | `OCIR_TENANCY` |
| Terraform remote-state bucket | Optional but recommended for shared ops | `backend.tf` |

## 2. Compartment

| Item | Default name | Created by | Notes |
|---|---|---|---|
| Application compartment | `octo` | Manual in Console | Owns all app-specific resources — simplifies IAM + cost tracking |

Set as `OCI_COMPARTMENT_ID` in every script.

## 3. Identity & policies

| Item | Purpose | Notes |
|---|---|---|
| Dynamic group — OKE nodes | Grants instance principal on workers | `ALL {instance.compartment.id = '<comp-ocid>'}` |
| Dynamic group — build host | OCIR push from remote builder VM | Same pattern, restricted to builder compartment |
| Policy — app runtime | Allow dynamic group to `use` APM domain, Logging, Monitoring, GenAI | See `deploy/oci/ensure_*.sh` for exact statements |
| IDCS identity domain | OIDC SSO | Hosts the confidential application |
| IDCS confidential application | Authorization Code + PKCE | Scopes: `openid profile email` |

## 4. Network

| Item | Quantity | Notes |
|---|---|---|
| VCN | 1 | 10.0.0.0/16 typical |
| Public subnet (LB) | 1 | For OCI LoadBalancer Service, WAF attach point |
| Private subnet (OKE workers) | 1–2 | Worker node pool |
| Internet gateway / NAT gateway | 1 each | NAT for private subnet egress |
| LB subnet OCID | 1 | `OCI_LB_SUBNET_OCID` env var consumed by K8s Service annotation |

## 5. Autonomous Database (ATP)

| Item | Default | Notes |
|---|---|---|
| Shape | 1 OCPU / 1 TB storage | Free tier sufficient for demos |
| Workload | Transaction Processing | Shop + CRM share one instance |
| Admin password | Strong — stored in K8s secret `octo-atp/password` | Env: `ORACLE_PASSWORD` |
| Wallet password | Separate from admin password | Env: `ORACLE_WALLET_PASSWORD` |
| Connection descriptor | e.g. `myatp_low` | Env: `ORACLE_DSN` |
| Wallet zip | Download from Console → DB Connection | Mount at `/opt/oracle/wallet` |

## 6. Container registry

| Repository (OCIR) | Image | Image tag pattern |
|---|---|---|
| `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop` | Drone Shop | `latest` + `YYYYMMDDHHMMSS` |
| `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal` | CRM Portal | same |
| `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/oci-coordinator` | Coordinator (optional) | same |

Auth: instance principal from the builder host's dynamic group + `docker login` once per host.

## 7. Observability

| Resource | Created by | Env var(s) |
|---|---|---|
| APM Domain | `ensure_apm.sh` / RM module / `apm_domain` TF module | `OCI_APM_ENDPOINT` |
| APM public data key | Same | `OCI_APM_PUBLIC_DATAKEY` |
| APM private data key | Same | `OCI_APM_PRIVATE_DATAKEY` (sensitive) |
| RUM Web Application | `ensure_apm.sh` (WEB_APPLICATION config) | `OCI_APM_WEB_APPLICATION` |
| Logging log group | OCI Console / Terraform | `OCI_LOG_GROUP_ID` |
| Application log (inside group) | OCI Console / Terraform | `OCI_LOG_ID` |
| Log Analytics namespace | One per tenancy (usually auto) | `LA_NAMESPACE` |
| Log Analytics log group | OCI Console / Terraform | `LA_LOG_GROUP_ID` |
| Log Analytics source `octo-shop-app-json` | `tools/create_la_source.py --apply` | — |
| Service Connector (app log → LA) | `la_pipeline_app_logs` module | — |
| Stack Monitoring MonitoredResource (ATP) | `ensure_stack_monitoring.sh` | — |
| Custom metrics + alarms | `ensure_monitoring.sh` | `OCI_MONITORING_NAMESPACE` |

## 8. WAF (optional but recommended)

| Resource | Quantity | Notes |
|---|---|---|
| WAF policy per frontend | 4 | shop, crm, ops, coordinator — all created by `modules/waf` |
| WAF log group | 1 | `WAF_LOG_GROUP_ID` |
| Per-frontend WAF log | 4 | `WAF_LOG_ID_SHOP`, `_CRM`, `_OPS`, `_COORDINATOR` — populated after WAF attach |

## 9. DNS & TLS

| Item | Purpose |
|---|---|
| `DNS_DOMAIN` (e.g. `tenant-a.customer.example`) | One variable that derives every public URL |
| A record `shop.${DNS_DOMAIN}` | → OCI LB / VM IP |
| A record `crm.${DNS_DOMAIN}` | → OCI LB / VM IP |
| A record `ops.${DNS_DOMAIN}` | optional |
| A record `coordinator.${DNS_DOMAIN}` | optional |
| TLS certificate per hostname | LetsEncrypt (VM path) or OCI Certificates (OKE path) |

## 10. Secrets (minimum for a clean deploy)

All are read via `cfg._env_secret()` which supports either inline env
vars or `*_FILE` mount paths (OCI Vault + Secrets Store CSI compatible).

| Secret | Shape | Used by |
|---|---|---|
| `AUTH_TOKEN_SECRET` | 32-byte url-safe random | Bearer-token HMAC signing (shop) |
| `INTERNAL_SERVICE_KEY` | 32-byte url-safe random | Cross-service `X-Internal-Service-Key` (shop, CRM, coordinator) |
| `APP_SECRET_KEY` | 32-byte url-safe random | Session signing (CRM) |
| `BOOTSTRAP_ADMIN_PASSWORD` | strong | CRM bootstrap admin user |
| `ORACLE_PASSWORD` | ATP admin password | Both apps (DB) |
| `ORACLE_WALLET_PASSWORD` | Wallet password | Both apps (DB) |
| `IDCS_CLIENT_SECRET` | From IDCS confidential app | OIDC SSO |
| `OCI_APM_PRIVATE_DATAKEY` | Auto-generated with APM Domain | OTel exporter |
| `OCI_APM_PUBLIC_DATAKEY` | Auto-generated with APM Domain | Browser RUM SDK |

Generate random ones: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

## 11. Runtime

One of:

| Runtime | Artifacts | Use when |
|---|---|---|
| **OKE cluster** | Cluster, node pool, OCI LB, K8s Services, Deployments, optional Secrets Store CSI driver | Production / HA |
| **Single VM** | Compute instance (4 OCPU / 16 GB), Docker, `deploy/vm/docker-compose-unified.yml`, nginx + LetsEncrypt | Demos, workshops, air-gapped |

## 12. Container images to build

| Project | Dockerfile | Push target |
|---|---|---|
| octo-drone-shop | `Dockerfile` (multi-stage, `ARG PYTHON_BASE=python:3.12-slim`) | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:<tag>` |
| enterprise-crm-portal | `Dockerfile` | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal:<tag>` |
| oci-coordinator (optional) | `Dockerfile` | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/oci-coordinator:<tag>` |

Apple Silicon hosts MUST cross-build with `--platform linux/amd64` or
delegate to an x86_64 remote builder (see `deploy/deploy.sh`).

---

## 13. Smallest viable deploy (demo)

If you only want to see the platform running:

- 1 compartment
- 1 ATP (free tier)
- 1 Compute VM (VM.Standard.E5.Flex, 2 OCPU, 16 GB)
- `deploy/vm/` path
- No WAF, no IDCS (local auth only), no Coordinator
- Skip APM on first boot — add later without redeploying

Total provisioning time: **~15 minutes** from a fresh tenancy.

## 14. Full production deploy

- 1 compartment, dynamic groups + IAM policies
- 1 ATP (20+ OCPU)
- 1 OKE cluster (3+ nodes)
- 1 OCI LB, 4 WAF policies (DETECTION mode first, promote to BLOCK)
- APM Domain + RUM + Log Analytics + Stack Monitoring
- IDCS identity domain + confidential app per frontend
- OCI Vault + Secrets Store CSI driver
- Terraform remote state in Object Storage
- Resource Manager stack (`deploy/resource-manager/`) for the observability + WAF surface
- Optional Coordinator deploy for auto-remediation

Total provisioning time: **45–90 minutes** for the first tenancy; subsequent tenancies ~15 minutes with the RM stack.

---

## 15. Variable → script map

| Variable | Validated by | Created/used by |
|---|---|---|
| `DNS_DOMAIN` | `pre-flight-check.sh` | every script |
| `OCIR_REGION`, `OCIR_TENANCY` | pre-flight, init-tenancy | `deploy.sh`, `deploy/vm/`, RM stack |
| `OCI_COMPARTMENT_ID` | pre-flight (recommended) | `ensure_apm.sh`, `ensure_stack_monitoring.sh`, init-tenancy |
| `ORACLE_DSN`, `ORACLE_PASSWORD`, `ORACLE_WALLET_PASSWORD` | init-tenancy (writes Secret) | app runtime |
| `INTERNAL_SERVICE_KEY` | init-tenancy (generates if missing) | shop, CRM, coordinator |
| `AUTH_TOKEN_SECRET`, `APP_SECRET_KEY`, `BOOTSTRAP_ADMIN_PASSWORD` | init-tenancy | app runtime |
| `IDCS_DOMAIN_URL`, `IDCS_CLIENT_ID`, `IDCS_CLIENT_SECRET` | `validate()` at startup | OIDC |
| `OCI_APM_*`, `OCI_LOG_ID`, `OCI_LOG_GROUP_ID` | `validate()` at startup | OTel, logging SDK |
| `OCI_LB_SUBNET_OCID` | pre-flight (recommended) | K8s Service annotation |

## 16. BOM version

This BOM matches the platform state as of commit `459acce` on
`octo-drone-shop/main`. When the platform changes in a way that adds or
removes a required resource, the same PR must update this document —
the pre-flight and Resource Manager schema both depend on it being
accurate.
