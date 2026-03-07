# OCTO Drone Shop Install Guide

## 1. Repository

Clone the renamed repository:

```bash
git clone https://github.com/adibirzu/octo-drone-shop.git
cd octo-drone-shop
```

## 2. Python environment

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Install local Git hooks (recommended):

```bash
./scripts/setup-hooks.sh
```

This enables a pre-commit `gitleaks` scan of staged changes.

## 3. Local smoke test (ATP only)

This repository is ATP-only. `docker-compose.yml` expects Oracle ATP inputs and a wallet mount.

Prepare local environment file:

```bash
cp .env.local.example .env.local
# edit .env.local with your local values
```

```bash
docker compose up --build
```

Or run the app directly after exporting environment variables:

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8080 --reload
```

## 4. Oracle ATP configuration

Production and OKE deployments require ATP.

Required environment variables:

```bash
export ORACLE_DSN="<your ATP TNS alias or DSN>"
export ORACLE_USER="ADMIN"
export ORACLE_PASSWORD="<password>"
export ORACLE_WALLET_DIR="/opt/oracle/wallet"
export ORACLE_WALLET_PASSWORD="<wallet password>"
```

Notes:

- Mount the ATP wallet into the path used by `ORACLE_WALLET_DIR`.
- ATP configuration is mandatory; startup fails if required Oracle inputs are missing.
- The readiness check runs `SELECT 1 FROM DUAL` and reports `db_type: oracle_atp`.

Optional helper to ensure/create ATP:

```bash
COMPARTMENT_ID="<database compartment ocid>" \
DISPLAY_NAME="mushop-cloudnative-atp" \
DB_NAME="mushopcnatp" \
./deploy/oci/ensure_atp.sh
```

## 5. OCI APM and RUM configuration

Set these environment variables:

```bash
export OCI_APM_ENDPOINT="https://<apm-domain>.apm-agt.<region>.oci.oraclecloud.com"
export OCI_APM_PRIVATE_DATAKEY="<private data key>"
export OCI_APM_PUBLIC_DATAKEY="<public data key>"
export OCI_APM_RUM_ENDPOINT="https://<apm-domain>.apm-agt.<region>.oci.oraclecloud.com"
export OCI_APM_WEB_APPLICATION="octo-drone-shop-web"
```

How the app uses them:

- `OCI_APM_ENDPOINT` and `OCI_APM_PRIVATE_DATAKEY` are used for OTLP trace export.
- The trace exporter posts to:

```text
${OCI_APM_ENDPOINT}/20200101/opentelemetry/private/v1/traces
```

- `OCI_APM_RUM_ENDPOINT` and `OCI_APM_PUBLIC_DATAKEY` are injected into the browser shell so the OCI APM RUM agent can load.
- `OCI_APM_WEB_APPLICATION` identifies the browser application value sent with RUM bootstrap.

Validation steps:

1. Start the app.
2. Open `/ready` and verify `apm_configured: true` and `rum_configured: true`.
3. Open `/shop`, add a product, and complete checkout.
4. Verify request, DB, checkout, and assistant traces appear in OCI APM.

## 6. OCI GenAI configuration

```bash
export OCI_COMPARTMENT_ID="<compartment ocid>"
export OCI_GENAI_ENDPOINT="https://inference.generativeai.<region>.oci.oraclecloud.com"
export OCI_GENAI_MODEL_ID="<model ocid or model id>"
```

When these are present, `/api/shop/assistant/query` uses OCI Generative AI. Otherwise it falls back to grounded local responses.

## 7. OCI Logging, Log Analytics, and Splunk

Application logs:

```bash
export OCI_LOG_ID="<oci log ocid>"
export OCI_LOG_GROUP_ID="<oci log group ocid>"
export SPLUNK_HEC_URL="https://<splunk-host>:8088"
export SPLUNK_HEC_TOKEN="<hec token>"
```

Edge logs:

1. Enable OCI Load Balancer access logs and error logs to OCI Logging.
2. Enable OCI WAF logs to OCI Logging.
3. Route OCI Logging data into Log Analytics and your external Splunk pipeline.

## 8. OKE deployment

The production manifest is [deploy/k8s/deployment.yaml](../deploy/k8s/deployment.yaml).

Create the required secrets first:

- `octo-atp`
- `octo-atp-wallet`
- `octo-apm`
- `octo-logging`
- `octo-genai`
- `octo-integrations`
- `octo-auth` with key `token-secret` for stable signed bearer tokens across replicas

Then deploy:

```bash
kubectl apply -f deploy/k8s/deployment.yaml
```

## 9. Post-install checks

- `/ready` returns `database: connected` and `db_type: oracle_atp`
- `/api/shop/storefront` returns `backend.database = oracle_atp`
- `/api/shop/checkout` creates orders and shipments
- `/api/shop/assistant/query` stores conversation rows
- OCI APM shows traces
- OCI Logging and Log Analytics show correlated logs
- OCI Load Balancer and WAF logs are enabled in OCI
