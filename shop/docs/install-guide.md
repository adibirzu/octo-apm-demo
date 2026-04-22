# OCTO Drone Shop Install Guide

## 1. Repository

```bash
git clone https://github.com/adibirzu/octo-drone-shop.git
cd octo-drone-shop
```

## 1b. Standalone deployment (any OCI tenancy, without external orchestration)

The app is fully portable — set **one domain variable** and all URLs, CORS
origins, and SSO redirects are derived automatically. No hardcoded tenancy
OCIDs, IPs, or hostnames remain in the codebase.

Use [deploy/credentials.template](../deploy/credentials.template) for secret-only
values. Every sensitive variable also supports a `*_FILE` variant so mounted
Docker/Kubernetes/OCI Vault secrets can be consumed without copying them into
tracked env files.

### Prerequisites

| Prerequisite | What to set | Notes |
|---|---|---|
| DNS domain | `DNS_DOMAIN=<your-domain>` | All `shop.<domain>` and `crm.<domain>` URLs derive from this |
| Oracle ATP | `ORACLE_DSN`, `ORACLE_PASSWORD`, wallet | See section 4 |
| OCI APM domain | `OCI_APM_ENDPOINT`, `OCI_APM_PRIVATE_DATAKEY` | Create via OCI Console → APM → Create domain |
| Auth secret | `AUTH_TOKEN_SECRET` | Required in production; 32+ random bytes |
| IDCS SSO (optional) | `IDCS_DOMAIN_URL`, `IDCS_CLIENT_ID`, `IDCS_CLIENT_SECRET` | See section 11; `IDCS_REDIRECT_URI` auto-derives from `DNS_DOMAIN` |
| CRM integration (optional) | `ENTERPRISE_CRM_URL`, `CRM_PUBLIC_URL` | Use an internal/backend URL for server-to-server calls and a public URL for browser links |
| Service key (optional) | `INTERNAL_SERVICE_KEY` | For CRM→shop simulation proxy; some deployment wrappers may derive it automatically |

### Quick start — standalone on OKE

```bash
# 1. Set your domain and OCI resources
export DNS_DOMAIN="<your-domain>"
export AUTH_TOKEN_SECRET="$(openssl rand -hex 32)"
export CRM_PUBLIC_URL="https://crm.${DNS_DOMAIN}"
export ORACLE_DSN="myatp_low"
export ORACLE_PASSWORD="<your-atp-password>"
export OCI_APM_ENDPOINT="https://<apm-data-upload-endpoint>"
export OCI_APM_PRIVATE_DATAKEY="<private-data-key>"
export OCI_LB_SUBNET_OCID="ocid1.subnet.oc1.<region>...."

# 2. Build and push (on an x86 build VM or CI)
docker build -t <region>.ocir.io/<namespace>/octo-drone-shop:latest .
docker push <region>.ocir.io/<namespace>/octo-drone-shop:latest

# 3. Render and apply K8s manifests
export OCIR_REPO="<region>.ocir.io/<namespace>"
export SHOP_HOST="shop.${DNS_DOMAIN}"
export TLS_SECRET_NAME="shop-tls"
export WORKFLOW_ALLOWED_ORIGINS="https://shop.${DNS_DOMAIN},https://crm.${DNS_DOMAIN}"
envsubst < deploy/k8s/deployment.yaml | kubectl apply -f -

# 4. Optional: SSO (IDCS) — set these 3 and the rest auto-derives
export IDCS_DOMAIN_URL="https://idcs-xxxxx.identity.oraclecloud.com"
export IDCS_CLIENT_ID="<from IDCS app>"
export IDCS_CLIENT_SECRET="<from IDCS app>"
kubectl -n octo-drone-shop create secret generic octo-sso \
  --from-literal=idcs-domain-url="${IDCS_DOMAIN_URL}" \
  --from-literal=idcs-client-id="${IDCS_CLIENT_ID}" \
  --from-literal=idcs-client-secret="${IDCS_CLIENT_SECRET}" \
  --from-literal=idcs-redirect-uri="https://shop.${DNS_DOMAIN}/api/auth/sso/callback"
kubectl -n octo-drone-shop rollout restart deploy/octo-drone-shop
```

All CORS origins and SSO redirect URIs derive from `DNS_DOMAIN` at runtime. If
the CRM or workflow gateway use private backend service URLs, set
`CRM_PUBLIC_URL` and `WORKFLOW_PUBLIC_API_BASE_URL` so browsers never receive
private service hostnames.

### If you use a deployment wrapper

If you have a separate deployment wrapper around this repo, it should inject
the same `DNS_DOMAIN`, auth secret, CRM URL, and OCI variables documented in
this guide. The shop manifests are designed to stay portable whether they are
rendered directly with `envsubst` or fed by a higher-level automation layer.

## 2. Python environment

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Verify critical runtime modules are present:

```bash
python -c "import fastapi, uvicorn, sqlalchemy, oracledb; print('runtime-ok')"
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

This starts both the FastAPI storefront and the Go workflow gateway. The shop UI reads `WORKFLOW_API_BASE_URL`; keep it at `http://localhost:8090` locally and switch it to the OCI API Gateway deployment endpoint in-tenancy.

Or run the app directly after exporting environment variables:

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8080 --reload
```

If startup fails with `ModuleNotFoundError: No module named 'oracledb'`, reinstall dependencies in the active environment:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -c "import oracledb; print(oracledb.__version__)"
```

Optional validation:

```bash
python -m py_compile server/main.py server/config.py server/modules/integrations.py server/modules/admin.py server/database.py
pytest
```

## 4. Oracle ATP configuration

Production and OKE deployments require ATP.

Treat ATP creation and wallet download as a hard prerequisite before you deploy the application manifests.

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
COMPARTMENT_ID="<database compartment ocid>" DISPLAY_NAME="shared-atp" DB_NAME="sharedatp" ./deploy/oci/ensure_atp.sh
```

Recommended OCI-native post-create steps:

```bash
oci db autonomous-database enable-autonomous-database-management --autonomous-database-id <atp_ocid>
oci db autonomous-database enable-operations-insights --autonomous-database-id <atp_ocid>
```

These services improve the drilldown path from APM traces into DB Management and Operations Insights.

You can also run the helper wrapper:

```bash
AUTONOMOUS_DATABASE_ID="<atp_ocid>" ./deploy/oci/ensure_db_observability.sh
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
5. In Trace Explorer, confirm spans now include page and module attributes such as `app.page.name`, `app.module`, `db.operation`, `db.connection_name`, and request runtime fields.

## 6. OCI GenAI configuration

```bash
export OCI_COMPARTMENT_ID="<compartment ocid>"
export OCI_GENAI_ENDPOINT="https://inference.generativeai.<region>.oci.oraclecloud.com"
export OCI_GENAI_MODEL_ID="<model ocid or model id>"
```

When these are present, `/api/shop/assistant/query` uses OCI Generative AI. Otherwise it falls back to grounded local responses.

## 7. Workflow Gateway and Select AI

The new backend workflow menus in `/shop` are served by the Go workflow gateway.

Required or recommended runtime values:

```bash
export WORKFLOW_API_BASE_URL="http://localhost:8090"
export WORKFLOW_SERVICE_NAME="octo-workflow-gateway"
export WORKFLOW_POLL_SECONDS="90"
export WORKFLOW_FAULTY_QUERY_ENABLED="false"
export SELECTAI_PROFILE_NAME="OCTO_DRONE_PROFILE"
```

Notes:

- `WORKFLOW_API_BASE_URL` is the only shop-facing endpoint you switch between local and tenancy.
- In tenancy, set `WORKFLOW_API_BASE_URL` to the OCI API Gateway deployment URL that fronts the Go service.
- The workflow gateway records scheduled runs in `workflow_runs`, query activity in `query_executions`, and component health snapshots in `component_snapshots`.
- Intentionally broken probe queries are available in the Query Lab and are isolated from the normal cart/checkout paths.

Starter assets:

```bash
./deploy/oci/render_workflow_gateway_api_spec.sh
cat deploy/oci/selectai-profile.example.sql
```

## 8. OCI Logging, Log Analytics, and Splunk

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
4. Route workflow gateway stdout logs into the same OCI Logging group or a dedicated workflow log group.
5. Keep `oracleApmTraceId` in the structured log payload so Log Analytics can correlate app, workflow, and DB investigation events.

## 9. OKE deployment

The production manifests are [deploy/k8s/deployment.yaml](../deploy/k8s/deployment.yaml) and [deploy/k8s/workflow-gateway.yaml](../deploy/k8s/workflow-gateway.yaml).

Create the required secrets first:

- `octo-atp`
- `octo-atp-wallet`
- `octo-apm`
- `octo-logging`
- `octo-genai` with optional key `selectai-profile-name`
- `octo-integrations` with optional key `workflow-api-base-url`
- `octo-auth` with key `token-secret` for stable signed bearer tokens across replicas

### Tenancy-portable rendering

`deploy/k8s/deployment.yaml` does NOT pin a tenancy/region/subnet. Render it
with `envsubst` so the same manifest can target any OCI tenancy:

```bash
export OCIR_REPO=<region-key>.ocir.io/<tenancy-namespace>
export OCI_LB_SUBNET_OCID=ocid1.subnet.oc1.<region>....
envsubst < deploy/k8s/deployment.yaml | kubectl apply -f -
envsubst < deploy/k8s/workflow-gateway.yaml | kubectl apply -f -
```

Recommended secret workflow:

```bash
cp deploy/credentials.template deploy/credentials.env
# fill secrets or *_FILE pointers in deploy/credentials.env
set -a
source deploy/credentials.env
set +a
```

The same rendering pattern applies if you call these manifests from a higher-level
deploy script or CI job. Keep the rendered values in environment variables or
secrets rather than hardcoding them into the manifest.

Or, if you prefer to skip templating, run kubectl directly:

```bash
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/workflow-gateway.yaml
```

Recommended image build and push flow for OCIR / OKE:

```bash
docker build -t <region-key>.ocir.io/<tenancy-namespace>/octo-drone-shop:latest .
docker push <region-key>.ocir.io/<tenancy-namespace>/octo-drone-shop:latest
docker build -t <region-key>.ocir.io/<tenancy-namespace>/octo-workflow-gateway:latest ./services/workflow-gateway
docker push <region-key>.ocir.io/<tenancy-namespace>/octo-workflow-gateway:latest
```

For direct VM or OCI x86 validation, use the same `.env.local` file and run:

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080
```

For Docker-based validation:

```bash
docker compose up --build
```

## 10. Post-install checks

- `/ready` returns `database: connected` and `db_type: oracle_atp`
- `/api/shop/storefront` returns `backend.database = oracle_atp`
- `/api/shop/checkout` creates orders and shipments
- `/api/shop/assistant/query` stores conversation rows
- `WORKFLOW_API_BASE_URL/api/workflows/overview` returns scheduler, order, CRM, inventory, and component data
- `/shop` shows the Workflow Gateway, DB Query Lab, and Select AI panels without breaking cart or assistant flows
- Manual broken queries appear in `query_executions` and are available for DB Management / OPSI investigation
- OCI APM shows traces
- OCI Logging and Log Analytics show correlated logs
- OCI Load Balancer and WAF logs are enabled in OCI

## 11. IDCS / OCI IAM Identity Domain SSO

The shop supports OIDC Authorization Code + PKCE against any OCI Identity
Domain. JWT signature verification is on by default and uses the IDCS JWKS
endpoint, so the integration is safe to expose to the internet.

### Register a Confidential Application in IDCS

1. OCI Console → **Identity & Security** → **Domains** → pick the domain.
2. **Integrated applications** → **Add application** → **Confidential App**.
3. **Resource server**: leave disabled.
4. **Client configuration**:
   - Allowed grant types: **Authorization Code**.
   - Allowed operations: **Introspect**.
   - Redirect URL: `https://shop.example.cloud/api/auth/sso/callback`
     (or your hostname).
   - Post-logout redirect URL: `https://shop.example.cloud/login`.
   - Client type: **Confidential**.
   - Scopes: `openid`, `profile`, `email`.
5. **Activate** the app and copy the **Client ID** and **Client Secret**.

### Set the secrets

Local dev (`.env.local`):

```env
IDCS_DOMAIN_URL=https://idcs-xxxxx.identity.oraclecloud.com
IDCS_CLIENT_ID=...
IDCS_CLIENT_SECRET=...
IDCS_REDIRECT_URI=http://localhost:8080/api/auth/sso/callback
```

Kubernetes:

```bash
kubectl -n octo-drone-shop create secret generic octo-sso \
  --from-literal=idcs-domain-url="https://idcs-xxxxx.identity.oraclecloud.com" \
  --from-literal=idcs-client-id="..." \
  --from-literal=idcs-client-secret="..." \
  --from-literal=idcs-redirect-uri="https://shop.example.cloud/api/auth/sso/callback" \
  --from-literal=idcs-post-logout-redirect="https://shop.example.cloud/login"
kubectl -n octo-drone-shop rollout restart deploy/octo-drone-shop
```

### Verify

- `GET /api/auth/sso/status` returns `{"configured": true, ...}`
- `/login` shows a "Sign in with OCI IAM (IDCS)" button
- The button redirects to `${IDCS_DOMAIN_URL}/oauth2/v1/authorize?...`
- After authentication, the callback verifies the ID token signature against
  `${IDCS_DOMAIN_URL}/admin/v1/SigningCert/jwk` and issues an httpOnly
  `octo_session` bearer cookie scoped to the app.

### Troubleshooting

| Symptom                                 | Cause                                                                 | Fix                                                              |
|-----------------------------------------|-----------------------------------------------------------------------|------------------------------------------------------------------|
| `503 SSO is not configured`             | One of the four IDCS env vars is missing                              | Set all four (`Config.idcs_configured` returns `True`)           |
| `502 IDCS JWKS unreachable`             | Egress firewall or wrong `IDCS_DOMAIN_URL`                            | Allow egress to `*.identity.oraclecloud.com:443`                 |
| `401 ID token verification failed`      | Clock skew, wrong audience, or expired key                            | Sync clock; recheck `IDCS_CLIENT_ID`; restart to refetch JWKS    |
| Callback redirects to `/login?sso_error=invalid_state` | PKCE cookie missing — usually a domain/path mismatch  | Ensure `IDCS_REDIRECT_URI` host matches the user-facing host     |
| `RuntimeError: AUTH_TOKEN_SECRET is required` at startup | Production but no signing secret               | Set `AUTH_TOKEN_SECRET` (32+ random bytes) before starting       |

## 12. Enhancement rollout plan

After the baseline deployment is stable, use this sequence to turn the platform
into a full OCI observability showcase:

1. **Golden workflows first** — verify checkout, CRM sync, AI assistant, and a
   simulated-fault path all generate traces.
2. **APM next** — confirm Trace Explorer and Topology show the complete
   cross-service path, then add widgets for checkout, sync, assistant, and DB
   latency.
3. **Logging and Log Analytics** — route structured logs into OCI Logging, then
   into Log Analytics, preserving `oracleApmTraceId`.
4. **Drilldowns** — publish the trace, log-search, and SQL-investigation pivots
   so operators can move between OCI services quickly.
5. **DB observability** — enable Database Management and Operations Insights for
   ATP and verify session-tag correlation.

Detailed plan: [docs/observability-enhancement-plan.md](observability-enhancement-plan.md)
