# Deployment Bill of Materials

The authoritative minimal list of tenancy resources, secrets, CLIs, and
container images required to redeploy the platform from a blank slate.
Mirrored from [`deploy/BOM.md`](https://github.com/adibirzu/octo-drone-shop/blob/main/deploy/BOM.md)
in the repo so both `pre-flight-check.sh` and new operators are reading
the same source of truth.

!!! note "Why this page exists"
    Every deploy failure in a new tenancy this year has traced back to
    a single missing thing — usually a policy statement, an LB subnet
    OCID, or a wallet password. The BOM is the checklist the pre-flight
    script validates against. Skip it at your peril.

## At a glance

| Category | Item count | Who creates it |
|---|---|---|
| Operator workstation CLIs | 8 | you, once per laptop |
| OCI tenancy prereqs | 4 | Console, one-time |
| Compartment | 1 | Console |
| IAM (dynamic groups, policies, IDCS) | 5 | Console or Terraform |
| Network (VCN, subnets, gateways) | 5 | Console or Terraform |
| Autonomous Database (ATP) | 1 + wallet | Console |
| OCIR repositories | 2–3 | `init-tenancy.sh` |
| Observability (APM, RUM, Logging, LA, Stack Monitoring) | 9 | `ensure_apm.sh`, `ensure_stack_monitoring.sh`, Terraform |
| WAF | 4 policies + log group | `deploy/terraform/modules/waf` |
| DNS + TLS | 2–4 A records + certs | Your DNS provider + certbot / OCI Certificates |
| Secrets | 9 | `init-tenancy.sh` + OCI Vault |
| Runtime | OKE cluster **OR** 1 Compute VM | Console or Terraform |
| Container images | 2–3 | `deploy/deploy.sh` |

Full row-by-row detail in [`deploy/BOM.md`](https://github.com/adibirzu/octo-drone-shop/blob/main/deploy/BOM.md).

## Smallest viable deploy (workshop/demo)

- 1 compartment, 1 ATP (free tier), 1 Compute VM
- `deploy/vm/` path — no Kubernetes, no WAF, no IDCS
- **~15 minutes** from blank tenancy to green `/ready`

## Full production deploy

- Dynamic groups + IAM + IDCS
- OKE cluster + OCI LB + 4 WAF policies (DETECTION → BLOCK)
- APM + RUM + Log Analytics + Stack Monitoring
- OCI Vault + Secrets Store CSI driver
- Resource Manager stack for the observability + WAF surface
- **45–90 minutes** first time; **~15 minutes** for subsequent tenancies via the RM stack.

## Variable → script map (excerpt)

| Variable | Validated by | Used by |
|---|---|---|
| `DNS_DOMAIN` | `pre-flight-check.sh` | every script |
| `OCIR_REGION`, `OCIR_TENANCY` | pre-flight, init-tenancy | build + rollout |
| `OCI_COMPARTMENT_ID` | pre-flight | `ensure_apm.sh`, `ensure_stack_monitoring.sh` |
| `ORACLE_DSN`, `ORACLE_PASSWORD`, `ORACLE_WALLET_PASSWORD` | `init-tenancy.sh` (writes Secret) | app runtime |
| `INTERNAL_SERVICE_KEY` | `init-tenancy.sh` (generates if missing) | shop, CRM, coordinator |
| `IDCS_CLIENT_SECRET` | `cfg.validate()` at startup | OIDC SSO |
| `OCI_APM_*`, `OCI_LOG_ID` | `cfg.validate()` at startup | OTel, logging SDK |

Full map in the source BOM.
