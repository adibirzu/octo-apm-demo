# OCTO Drone Shop

ATP-backed drone commerce demo for OCI monitored-app scenarios.

## What is in this repo

- Oracle ATP is the primary backend for products, customers, carts, orders, shipments, page views, and assistant conversations.
- A separate Go workflow gateway adds backend workflow menus, scheduled ATP query sweeps, query-lab probes, and Select AI execution paths for the shop UI.
- OCI APM captures backend traces through OpenTelemetry and browser telemetry through OCI APM RUM.
- OCI Logging receives structured app logs with `oracleApmTraceId` correlation fields.
- OCI Generative AI powers the drone technical assistant when configured, with a grounded fallback when it is not.
- OCI Load Balancer stays in front of the app in OKE. WAF, LB logs, and forwarding guidance are documented in [docs/technical-architecture.md](docs/technical-architecture.md).

## Documentation

- Install guide: [docs/install-guide.md](docs/install-guide.md)
- Technical architecture: [docs/technical-architecture.md](docs/technical-architecture.md)
- OKE deployment manifest: [deploy/k8s/deployment.yaml](deploy/k8s/deployment.yaml)
- Workflow gateway manifest: [deploy/k8s/workflow-gateway.yaml](deploy/k8s/workflow-gateway.yaml)
- API Gateway renderer: [deploy/oci/render_workflow_gateway_api_spec.sh](deploy/oci/render_workflow_gateway_api_spec.sh)

## Key files

- App entry: [server/main.py](server/main.py)
- Store backend helpers: [server/store_service.py](server/store_service.py)
- Storefront presentation: [server/storefront.py](server/storefront.py)
- Drone assistant integration: [server/genai_service.py](server/genai_service.py)
- Workflow gateway: [services/workflow-gateway/cmd/workflow-gateway/main.go](services/workflow-gateway/cmd/workflow-gateway/main.go)
- OKE deployment: [deploy/k8s/deployment.yaml](deploy/k8s/deployment.yaml)

## Tenancy portability

Set **one variable** — `DNS_DOMAIN` — and all URLs, CORS origins, SSO redirect URIs, and CRM integration endpoints are derived at runtime. No tenancy OCIDs, regions, or hostnames are hardcoded.

```bash
export DNS_DOMAIN="yourcompany.cloud"
# → shop.yourcompany.cloud, crm.yourcompany.cloud, SSO callback, CORS
```

See [docs/install-guide.md § 1b](docs/install-guide.md) for the full standalone deployment quickstart.

## Required production inputs

- **`DNS_DOMAIN`**: your tenancy's DNS zone. All public URLs derive from this.
- **`AUTH_TOKEN_SECRET`**: bearer-token signing key (required in production, auto-generated in dev).
- ATP: `ORACLE_DSN`, `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_WALLET_PASSWORD`, wallet at `/opt/oracle/wallet`
- APM: `OCI_APM_ENDPOINT`, `OCI_APM_PRIVATE_DATAKEY`, `OCI_APM_PUBLIC_DATAKEY`, `OCI_APM_RUM_ENDPOINT`
- SSO (optional): `IDCS_DOMAIN_URL`, `IDCS_CLIENT_ID`, `IDCS_CLIENT_SECRET` (redirect URIs auto-derive from DNS_DOMAIN)
- Service key (optional): `INTERNAL_SERVICE_KEY` for CRM→shop simulation proxy
- GenAI: `OCI_COMPARTMENT_ID`, `OCI_GENAI_ENDPOINT`, `OCI_GENAI_MODEL_ID`
- Workflow gateway: `WORKFLOW_API_BASE_URL`, `WORKFLOW_SERVICE_NAME`, `WORKFLOW_POLL_SECONDS`
- Logging: `OCI_LOG_ID`, optional `OCI_LOG_GROUP_ID`, `SPLUNK_HEC_URL`, `SPLUNK_HEC_TOKEN`

## ATP provisioning helper

Use `deploy/oci/ensure_atp.sh` to verify or create the ATP for this component. In the
customer-facing OCI-DEMO deployment, CRM and Drone Shop share `oci-demo-shared-atp`.

Example:

```bash
COMPARTMENT_ID="<database compartment ocid>" \
DISPLAY_NAME="oci-demo-shared-atp" \
DB_NAME="ocidemoatp" \
./deploy/oci/ensure_atp.sh
```

After ATP creation, download the wallet, mount it into the runtime, and populate:

```bash
export ORACLE_DSN="<atp_low or atp_tp alias>"
export ORACLE_USER="ADMIN"
export ORACLE_PASSWORD="<admin password>"
export ORACLE_WALLET_DIR="/opt/oracle/wallet"
export ORACLE_WALLET_PASSWORD="<wallet password>"
```

For OCI observability drill-downs, also enable native ADB services:

```bash
oci db autonomous-database enable-autonomous-database-management --autonomous-database-id <atp_ocid>
oci db autonomous-database enable-operations-insights --autonomous-database-id <atp_ocid>
```

## Local env templates

- Copy `.env.local.example` to `.env.local` and fill in values.
- Keep `.env.local` and any local overrides out of Git; `.gitignore` excludes local env files and wallet artifacts.

## Git leak guard

Enable repo hooks so commits are blocked when `gitleaks` detects secrets:

```bash
./scripts/setup-hooks.sh
```

The pre-commit hook scans staged changes using `.gitleaks.toml`.

## Install paths

- OKE and ATP install/config steps are in [docs/install-guide.md](docs/install-guide.md).
- OCI APM endpoint and data key configuration is documented in [docs/install-guide.md](docs/install-guide.md#oci-apm-and-rum-configuration).
- OCI API Gateway, workflow gateway, Select AI, and DB observability steps are documented in [docs/install-guide.md](docs/install-guide.md).

## Store flows

- `/api/shop/storefront` reads the full catalog from ATP and enriches products with generated visuals and technical summaries.
- `/api/cart/*`, `/api/shop/checkout`, and `/api/orders` persist cart and order activity in the backend.
- `/api/shop/assistant/query` stores conversation turns in ATP and emits traceable assistant activity.
- The new shop workflow menus call the Go workflow gateway through `WORKFLOW_API_BASE_URL` to inspect order/CRM/component rollups, execute investigation queries, and submit Select AI prompts to ATP.
