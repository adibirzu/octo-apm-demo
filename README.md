# OCTO Drone Shop

ATP-backed drone commerce demo for OCI monitored-app scenarios.

## What is in this repo

- Oracle ATP is the primary backend for products, customers, carts, orders, shipments, page views, and assistant conversations.
- OCI APM captures backend traces through OpenTelemetry and browser telemetry through OCI APM RUM.
- OCI Logging receives structured app logs with `oracleApmTraceId` correlation fields.
- OCI Generative AI powers the drone technical assistant when configured, with a grounded fallback when it is not.
- OCI Load Balancer stays in front of the app in OKE. WAF, LB logs, and forwarding guidance are documented in [docs/technical-architecture.md](docs/technical-architecture.md).

## Documentation

- Install guide: [docs/install-guide.md](docs/install-guide.md)
- Technical architecture: [docs/technical-architecture.md](docs/technical-architecture.md)
- OKE deployment manifest: [deploy/k8s/deployment.yaml](deploy/k8s/deployment.yaml)

## Key files

- App entry: [server/main.py](server/main.py)
- Store backend helpers: [server/store_service.py](server/store_service.py)
- Storefront presentation: [server/storefront.py](server/storefront.py)
- Drone assistant integration: [server/genai_service.py](server/genai_service.py)
- OKE deployment: [deploy/k8s/deployment.yaml](deploy/k8s/deployment.yaml)

## Required production inputs

- ATP: `ORACLE_DSN`, `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_WALLET_PASSWORD`, wallet mounted at `/opt/oracle/wallet`
- APM: `OCI_APM_ENDPOINT`, `OCI_APM_PRIVATE_DATAKEY`, `OCI_APM_PUBLIC_DATAKEY`, `OCI_APM_RUM_ENDPOINT`, `OCI_APM_WEB_APPLICATION`
- GenAI: `OCI_COMPARTMENT_ID`, `OCI_GENAI_ENDPOINT`, `OCI_GENAI_MODEL_ID`
- Logging: `OCI_LOG_ID`, optional `OCI_LOG_GROUP_ID`, `SPLUNK_HEC_URL`, `SPLUNK_HEC_TOKEN`
- Runtime: `OCI_AUTH_MODE`, optional `AUTH_TOKEN_SECRET`

## ATP provisioning helper

Use `deploy/oci/ensure_atp.sh` to verify or create the dedicated ATP for this component.

Example:

```bash
COMPARTMENT_ID="<database compartment ocid>" \
DISPLAY_NAME="mushop-cloudnative-atp" \
DB_NAME="mushopcnatp" \
./deploy/oci/ensure_atp.sh
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

## Store flows

- `/api/shop/storefront` reads the full catalog from ATP and enriches products with generated visuals and technical summaries.
- `/api/cart/*`, `/api/shop/checkout`, and `/api/orders` persist cart and order activity in the backend.
- `/api/shop/assistant/query` stores conversation turns in ATP and emits traceable assistant activity.
