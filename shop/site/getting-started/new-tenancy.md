# Deploying to a New OCI Tenancy

This guide bootstraps the OCTO Drone Shop + Enterprise CRM Portal stack
in a fresh Oracle Cloud tenancy. Every step is env-driven — no tenancy
OCIDs, region slugs, or public hostnames are committed to source.

## 1. Prerequisites

- OCI tenancy with:
    - OKE cluster and kubectl context configured
    - Autonomous Database (ATP) provisioned (wallet download access)
    - OCIR namespace + compartment for container images
- Local tools on PATH: `terraform >= 1.6`, `oci` CLI, `kubectl`, `envsubst`, `docker`, `ssh`.
- Remote build host (x86_64 VM) reachable over SSH for image builds. Apple Silicon CI hosts cannot build the x86 image directly without QEMU.

## 2. Pre-flight check

Before any infrastructure is created, run the pre-flight validator:

```bash
DNS_DOMAIN=tenant-a.customer.example \
OCIR_REPO=<region>.ocir.io/<tenancy-ns>/octo-drone-shop \
K8S_NAMESPACE=octo-drone-shop \
./deploy/pre-flight-check.sh
```

The script fails fast if:

- `DNS_DOMAIN`, `OCIR_REPO`, or `K8S_NAMESPACE` is unset
- any required variable still contains placeholder text
  (`example.cloud`, `example.invalid`, `changeme`, `TODO`, `PLACEHOLDER`)
- `kubectl` has no current context

Recommended variables (warnings only, feature-specific):

| Variable | Feature |
|---|---|
| `OCI_COMPARTMENT_ID` | All OCI service calls (APM, Logging, Monitoring) |
| `OCI_APM_ENDPOINT`, `OCI_APM_PRIVATE_DATAKEY` | APM traces |
| `OCI_LOG_ID` | App log ingestion to OCI Logging → Log Analytics |
| `OCI_LB_SUBNET_OCID` | OCI LoadBalancer annotation on the Service |
| `IDCS_DOMAIN_URL`, `IDCS_CLIENT_ID`, `IDCS_CLIENT_SECRET` | OIDC SSO via IAM identity domain |

## 3. Bootstrap the tenancy

```bash
DNS_DOMAIN=tenant-a.customer.example \
OCIR_REGION=<region> \
OCIR_TENANCY=<tenancy-ns> \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxx \
K8S_NAMESPACE=octo-drone-shop \
ORACLE_DSN=<adb-connection-string> \
ORACLE_PASSWORD=<admin-password> \
./deploy/init-tenancy.sh
```

The script is idempotent and performs:

1. **OCIR repository** — creates `octo-drone-shop` if missing.
2. **Kubernetes namespace** — creates it if missing.
3. **Bootstrap secrets** — `octo-auth` (token + internal service key), `octo-atp` (DSN, user, password, wallet password). Keys are auto-generated when not supplied.
4. **Terraform init** — downloads the OCI provider in `deploy/terraform/`.

Remaining secrets (IDCS, APM, RUM) are populated by the observability scripts in the next step.

## 4. Provision observability

### APM Domain + RUM Web Application

```bash
COMPARTMENT_ID=$OCI_COMPARTMENT_ID \
./deploy/oci/ensure_apm.sh --plan     # review
PLAN_ONLY=false \
COMPARTMENT_ID=$OCI_COMPARTMENT_ID \
./deploy/oci/ensure_apm.sh --apply     # actually create
./deploy/oci/ensure_apm.sh --print     # emit `export OCI_APM_*=...`
```

The script prints a block of `export` lines. Pipe them into a Kubernetes secret:

```bash
./deploy/oci/ensure_apm.sh --print | grep '^export' > /tmp/apm.env
# ... create octo-apm secret from /tmp/apm.env ...
```

### Log Analytics source registration

```bash
python3 tools/create_la_source.py \
    --la-namespace <la-namespace> \
    --la-log-group-id <la-log-group-ocid>     # dry run — prints payload
python3 tools/create_la_source.py \
    --la-namespace <la-namespace> \
    --la-log-group-id <la-log-group-ocid> \
    --apply                                    # actually call OCI
```

This registers the `octo-shop-app-json` source + JSON parser so Log
Analytics indexes `trace_id`, `oracleApmTraceId`, `level`, `request_id`,
and other app fields as searchable columns.

### App log pipeline (Service Connector)

The terraform root module exposes `module.la_pipeline_app_logs`. Set the following in your `terraform.tfvars`:

```hcl
app_log_id         = "ocid1.log.oc1..xxx"        # same OCID as OCI_LOG_ID
app_log_group_id   = "ocid1.loggroup.oc1..xxx"
la_namespace       = "<log-analytics-namespace>"
la_log_group_id    = "ocid1.loganalyticsloggroup.oc1..xxx"
```

Then `terraform plan` / `terraform apply` in `deploy/terraform/` to create the Service Connector.

### Stack Monitoring for the Autonomous Database

```bash
COMPARTMENT_ID=$OCI_COMPARTMENT_ID \
AUTONOMOUS_DATABASE_ID=<atp-ocid> \
SM_RESOURCE_NAME=octo-atp \
./deploy/oci/ensure_stack_monitoring.sh          # dry run by default
DRY_RUN=false ... ./deploy/oci/ensure_stack_monitoring.sh
```

The ATP is registered as a MonitoredResource so it joins the Stack
Monitoring topology alongside the OKE workloads.

## 5. First deploy

```bash
DNS_DOMAIN=tenant-a.customer.example \
OCIR_REPO=<region>.ocir.io/<tenancy-ns>/octo-drone-shop \
./deploy/deploy.sh
```

The script builds on the remote VM, pushes to OCIR, and rolls out the
OKE Deployment. `--build-only` skips the rollout; `--rollout-only`
redeploys the existing `:latest` image.

## 6. Validate

```bash
curl -s https://shop.<your-domain>/ready | jq
curl -s https://shop.<your-domain>/api/observability/360 | jq
curl -s https://shop.<your-domain>/api/integrations/schema | jq
```

If `/api/integrations/schema` returns an OpenAPI document that includes
`InternalServiceKey` in `components.securitySchemes`, the cross-service
contract is live.
