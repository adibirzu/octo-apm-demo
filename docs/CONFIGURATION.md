---
title: Configuration
---

# Configuration Reference

This reference documents every environment variable, Helm value, and Kubernetes
secret consumed by `octo-apm-demo`. Each entry lists the canonical source file,
the default (if any), and the code path that reads the value. Operators
deploying the stack should treat this document as the authoritative surface for
runtime configuration.

> **Convention.** Placeholders such as `${DNS_DOMAIN}`, `<COMPARTMENT_OCID>`,
> `<TENANCY_NAMESPACE>`, `<OCIR_REGION>`, and `<OCIR_TENANCY>` are used
> throughout. Fill them in from the target tenancy — never commit real values
> into Git.

---

## A. Configuration Surface

Configuration lives in five layers. Pick the one that matches the deployment
target.

| Layer | File | Used by |
|-------|------|---------|
| VM / Podman | `deploy/vm/.env.template` | Unified single-host deployment (`deploy/vm/docker-compose-unified.yml`) |
| OCI Compute (two-instance) | `deploy/compute/runtime.env.template` | `deploy/compute/install.sh` + systemd units in `deploy/compute/systemd/` |
| Per-service local dev | `shop/.env.example`, `crm/.env.example` | Service-local containers and `make` targets |
| Helm | `deploy/helm/octo-apm-demo/values.yaml` | `helm install/upgrade` against OKE |
| Kubernetes secrets | `deploy/helm/octo-apm-demo/templates/secrets.yaml` | Mounted into pods via `envFrom: secretRef` |

The Helm chart references **named secrets** rather than embedding values:
`octo-atp`, `octo-auth`, `octo-apm`, `octo-logging`, `octo-oci-config`,
`octo-sso`, and `octo-atp-wallet`. The chart only creates them when
`secrets.create=true` (default: `false`).

---

## B. OCI Observability

### APM (Traces) and RUM (Browser)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OCI_APM_ENDPOINT` | URL | _empty_ | OCI APM private upload endpoint. Source: APM Domain → "Data Upload Endpoint". Read by `shop/.env.example:71`, `crm/.env.example:61`. |
| `OCI_APM_PRIVATE_DATAKEY` | secret | _empty_ | Private datakey used by backend OTel exporters. Prefer `OCI_APM_PRIVATE_DATAKEY_FILE` for mounted secrets. |
| `OCI_APM_PUBLIC_DATAKEY` | secret | _empty_ | Public datakey (browser/RUM uploads). |
| `OCI_APM_RUM_ENDPOINT` | URL | _empty_ | RUM ingestion endpoint for browser beacons. |
| `OCI_APM_RUM_PUBLIC_DATAKEY` | secret | _empty_ | RUM public datakey injected into the browser bootstrap script. |
| `OCI_APM_WEB_APPLICATION` | string | `octo-drone-shop-web` | RUM web application identifier rendered into HTML templates. Default declared at `deploy/vm/.env.template:58`, `shop/.env.example:76`. |
| `OTEL_TRACES_SAMPLER` | enum | `always_on` | OpenTelemetry sampler for the Python SDK. <!-- VERIFY: production sampling overrides may be required to stay within APM ingestion quota --> |
| `OTEL_PYTHON_LOG_CORRELATION` | bool | `true` | Injects `trace_id`/`span_id` into Python log records. |
| `OTLP_LOG_EXPORT_ENABLED` | bool | `false` | When `true`, exports application logs via OTLP in addition to OCI Logging. |

### OCI Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OCI_LOG_ID` | OCID | _empty_ | Primary application log OCID for the Logging SDK. Read by `shop/.env.example:108`, `deploy/vm/.env.template:60`. |
| `OCI_LOG_GROUP_ID` | OCID | _empty_ | Parent log group OCID. |
| `OCI_LOG_CHAOS_AUDIT_ID` | OCID | _empty_ | Dedicated log OCID for chaos / simulation events. Declared at `deploy/vm/.env.template:62`. |
| `OCI_LOG_SECURITY_ID` | OCID | _empty_ | Dedicated log OCID for security/audit events. |

### OCI Monitoring

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OCI_MONITORING_NAMESPACE` | string | `octo_apm_demo` | Custom metrics namespace used by `shop/server/observability/oci_monitoring.py` and `crm/server/observability/oci_monitoring.py`. Default declared at `deploy/vm/.env.template:41` and `deploy/helm/octo-apm-demo/values.yaml:21` (`global.monitoringNamespace`). |
| `OCI_MONITORING_INTERVAL_SECONDS` | int (seconds) | `60` | Publish cadence. Read at `shop/server/observability/oci_monitoring.py:55` and `crm/server/observability/oci_monitoring.py:37`. |

### Common OCI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OCI_COMPARTMENT_ID` | OCID | _empty_ | Compartment that owns APM, Logging, ATP, GenAI resources. Required for any OCI-backed feature. |
| `OCI_REGION` | string | _empty_ | OCI region identifier (e.g., `eu-frankfurt-1`). Distinct from `OCIR_REGION`. |
| `OCI_AUTH_MODE` | enum | `instance_principal` | One of `instance_principal`, `workload_identity`, `config_file`. `instance_principal` requires the node pool's dynamic group to have policies for APM/Logging/Monitoring/GenAI. |

### Generative AI / Select AI

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OCI_GENAI_ENDPOINT` | URL | _empty_ | OCI Generative AI inference endpoint. Required when the assistant features are enabled. |
| `OCI_GENAI_MODEL_ID` | OCID | _empty_ | Model OCID (chat completions). |
| `SELECTAI_PROFILE_NAME` | string | _empty_ | Select AI profile name used by the Workflow Gateway for natural-language SQL. |
| `SELECTAI_TIMEOUT_SECONDS` | int (seconds) | `30` | Per-request timeout for Select AI calls. Default declared at `deploy/vm/.env.template:80`. |

### LLMetry and optional Langfuse

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LLMETRY_ENABLED` | bool | `true` | Master switch for assistant telemetry capture. |
| `LLMETRY_STORE_ENABLED` | bool | `true` | Persist captured spans to the local store. |
| `LLMETRY_CAPTURE_CONTENT` | bool | `false` | When `true`, captures prompt/response bodies. Leave `false` in production unless data classification permits. |
| `LANGFUSE_ENABLED` | bool | `false` | Enable parallel Langfuse export for comparison. |
| `LANGFUSE_HOST` | URL | _empty_ | Langfuse instance host (self-hosted or cloud). <!-- VERIFY: Langfuse host must be reachable from each pod's egress path --> |
| `LANGFUSE_PUBLIC_KEY` | secret | _empty_ | Project public key. Prefer `LANGFUSE_PUBLIC_KEY_FILE` for mounted secrets. |
| `LANGFUSE_SECRET_KEY` | secret | _empty_ | Project secret key. Prefer `LANGFUSE_SECRET_KEY_FILE`. |
| `LANGFUSE_OTEL_EXPORT_ENABLED` | bool | `true` | Use OTLP exporter rather than the legacy ingestion API. |
| `LANGFUSE_TIMEOUT_SECONDS` | float | `2.0` | Per-request timeout. |
| `LANGFUSE_INGESTION_VERSION` | int | `4` | API version pinning. |

---

## C. Application Configuration

### Environment and identity

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENVIRONMENT` | enum | `production` | One of `production`, `staging`, `dev`. Influences logging verbosity and feature flags. |
| `SERVICE_NAMESPACE` | string | `octo` (VM), `crm` (CRM per-service) | OTel `service.namespace` resource attribute. Declared at `deploy/vm/.env.template:42`, `crm/.env.example:44`. |
| `DEMO_STACK_NAME` | string | `octo-vm` / `octo-compute` / `octo-apm-demo` | Stack identity tag emitted into metrics and logs. |
| `APP_TOPOLOGY_PROFILE` | enum | `single-vm` (VM), unset (compute) | Topology hint consumed by the dashboards. |

### Per-service OTel identifiers

| Variable | Default | Bound service |
|----------|---------|---------------|
| `SHOP_OTEL_SERVICE_NAME` | `octo-drone-shop` | Drone Shop (FastAPI) |
| `CRM_OTEL_SERVICE_NAME` | `enterprise-crm-portal` | Enterprise CRM (FastAPI) |
| `SHOP_SERVICE_INSTANCE_ID` | `octo-drone-shop-vm` | Shop instance identifier |
| `CRM_SERVICE_INSTANCE_ID` | `enterprise-crm-portal-vm` | CRM instance identifier |
| `JAVA_APM_SERVICE_INSTANCE_ID` | `octo-java-app-server-vm` | Java APM payment sidecar |
| `WORKFLOW_SERVICE_INSTANCE_ID` | `octo-workflow-gateway-vm` | Workflow Gateway (Select AI proxy) |

### Cross-service URLs

The Shop and the CRM call each other over private cluster URLs while
publishing public URLs to the browser. Configure both sides.

| Variable | Read by | Description |
|----------|---------|-------------|
| `SERVICE_CRM_URL` | Shop | **Canonical** in-cluster CRM URL. `ENTERPRISE_CRM_URL` remains accepted as a deprecated alias (`shop/.env.example:37-40`). |
| `ENTERPRISE_CRM_URL` | Shop | Deprecated alias for `SERVICE_CRM_URL`. |
| `CRM_PUBLIC_URL` | Shop | Public browser URL for CRM links in status payloads. |
| `CRM_BASE_URL` | CRM | Public base URL the CRM serves itself under (used for redirect derivation). |
| `SERVICE_SHOP_URL` | CRM | **Canonical** in-cluster Shop URL. `OCTO_DRONE_SHOP_URL` and `MUSHOP_CLOUDNATIVE_URL` are accepted as deprecated aliases (`crm/.env.example:83-89`). |
| `EXTERNAL_ORDERS_URL` | CRM | Override for the orders-sync source URL. |
| `EXTERNAL_ORDERS_PATH` | CRM | Path appended to `SERVICE_SHOP_URL`. Default `/api/orders` (`crm/.env.example:91`). |

### Shared service auth

| Variable | Type | Description |
|----------|------|-------------|
| `INTERNAL_SERVICE_KEY` | secret | Server-to-server token shared between Shop and CRM. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Required for the simulation proxy. Prefer `INTERNAL_SERVICE_KEY_FILE` for mounted secrets. |
| `AUTH_TOKEN_SECRET` | secret | Application JWT signing secret. |
| `APP_SECRET_KEY` | secret | Flask/Starlette session secret. |
| `BOOTSTRAP_ADMIN_PASSWORD` | secret | Initial admin password for the CRM. Used only on first boot. |

---

## D. Database (Oracle ATP)

The platform targets Oracle Autonomous Transaction Processing. The wallet is
mounted at `ORACLE_WALLET_DIR` and must be readable by the container user.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ORACLE_DSN` | string | _empty_ | TNS alias from `tnsnames.ora` (e.g., `myatp_low`). |
| `ORACLE_USER` | string | `ADMIN` | Database user. |
| `ORACLE_PASSWORD` | secret | _empty_ | Database password. Prefer `ORACLE_PASSWORD_FILE`. |
| `ORACLE_WALLET_DIR` | path | `/opt/oracle/wallet` (compute) / `/app/wallet` (per-service) | Mount path containing the unzipped ATP wallet. |
| `ORACLE_WALLET_PASSWORD` | secret | _empty_ | Wallet password. Prefer `ORACLE_WALLET_PASSWORD_FILE`. |
| `ATP_OCID` | OCID | _empty_ | ATP instance OCID, exposed in dashboards. |
| `DATABASE_OBSERVABILITY_ENABLED` | bool | `true` | Enables the DB observability collectors (slow query, session tracking). |

### Wallet mount user/group

Compute deployments must mount the wallet so the container user can read it.
The Dockerfiles for both Shop and CRM use UID/GID `10001`:

| Variable | Default | Source |
|----------|---------|--------|
| `APP_CONTAINER_UID` | `10001` | `deploy/compute/runtime.env.template:37` |
| `APP_CONTAINER_GID` | `10001` | `deploy/compute/runtime.env.template:38` |

### Local PostgreSQL (CRM, optional)

The CRM supports a local PostgreSQL workflow for laptop development. These
variables are ignored when ATP is configured.

| Variable | Default | Description |
|----------|---------|-------------|
| `CRM_DB_NAME` | `crm_db` | Database name. |
| `CRM_DB_USER` | `crm_user` | Database user. |
| `CRM_DB_PASSWORD` | _empty_ | Password. Prefer `CRM_DB_PASSWORD_FILE`. |
| `DATABASE_URL` | _empty_ | Override the full async SQLAlchemy URL. |
| `DATABASE_SYNC_URL` | _empty_ | Override the sync SQLAlchemy URL. |

### Pool tuning (CRM)

Declared at `crm/.env.example:47-55`. Defaults are conservative for ATP shared
infra:

| Variable | Default |
|----------|---------|
| `DB_POOL_SIZE` | `10` |
| `DB_MAX_OVERFLOW` | `20` |
| `DB_POOL_TIMEOUT` | `30` |
| `DB_AUTH_POOL_SIZE` | `5` |
| `DB_AUTH_MAX_OVERFLOW` | `10` |
| `DB_AUTH_POOL_TIMEOUT` | `5` |
| `AUTH_EXECUTOR_MAX_WORKERS` | `15` |

---

## E. Payment, Java APM, and Workflow Gateway

### Payment simulator

The platform never bills a real card. The simulator is the default provider.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PAYMENT_PROVIDER` | enum | `simulated` | Payment provider identifier. Only `simulated` is supported in this release. |
| `PAYMENT_GATEWAY_SIMULATION_ENABLED` | bool | `true` | Master switch for the simulator. |
| `PAYMENT_SIMULATION_MODE` | enum | `approve` | One of `approve`, `decline`, `random`. Drives demo failure scenarios. |
| `PAYMENT_SIMULATION_CURRENCY` | string | `usd` | ISO 4217 currency code applied to simulated charges. |

### Java APM payment app-server

The Java sidecar exists to produce realistic Java-agent traces in APM.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JAVA_APM_ENABLED` | bool | `true` (VM), `false` (compute) | Enable the Java sidecar. Shop talks to it for the payment leg. |
| `JAVA_APM_SERVICE_URL` | URL | `http://java-apm:8080` (VM) | Cluster-local URL to reach the sidecar. |
| `JAVA_APM_SERVICE_NAME` | string | `octo-java-app-server` | OTel service name. |
| `JAVA_APM_TIMEOUT_SECONDS` | float | `3.0` | HTTP client timeout from the Shop. |
| `JAVA_APM_IMAGE` | container ref | _empty_ | OCIR image when deploying via compute. |
| `JAVA_APM_PORT` | int | `18080` | Listening port on the sidecar. Default declared at `deploy/compute/runtime.env.template:58`. |

### Workflow Gateway (Select AI proxy)

A FastAPI sidecar that translates assistant requests into OCI Generative AI and
Select AI calls.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `WORKFLOW_GATEWAY_ENABLED` | bool | `false` (compute), implicit `true` (Helm `workflowGateway.enabled`) | Whether to deploy the sidecar. |
| `WORKFLOW_API_BASE_URL` | URL | `http://workflow-gateway:8090` (VM) | In-cluster backend URL. |
| `WORKFLOW_PUBLIC_API_BASE_URL` | URL | `/api/workflow-gateway` | Same-origin browser path through the reverse proxy. |
| `WORKFLOW_SERVICE_NAME` | string | `octo-workflow-gateway` | OTel service name. |
| `WORKFLOW_PORT` | int | `8090` | Listening port. |
| `WORKFLOW_POLL_SECONDS` | int (seconds) | `90` | Browser long-poll interval for workflow runs. |
| `WORKFLOW_FAULTY_QUERY_ENABLED` | bool | `false` | Demo toggle: inject a known-bad SQL pattern to surface in APM. |
| `WORKFLOW_ALLOWED_ORIGINS` | CSV | _derived from `DNS_DOMAIN`_ | CORS allow-list (e.g., `https://shop.<domain>,https://crm.<domain>`). |

---

## F. SSO (IDCS / OCI Identity Domains)

SSO is optional. When unset, local bootstrap auth remains available.

| Variable | Type | Description |
|----------|------|-------------|
| `IDCS_DOMAIN_URL` | URL | Identity Domain base URL (e.g., `https://idcs-<id>.identity.oraclecloud.com`). <!-- VERIFY: identity domain URL is tenancy-specific and not discoverable from this repo --> |
| `IDCS_CLIENT_ID` | string | Confidential application client ID. |
| `IDCS_CLIENT_SECRET` | secret | Confidential application client secret. Prefer `IDCS_CLIENT_SECRET_FILE`. |
| `IDCS_REDIRECT_URI` | URL | OAuth redirect URI. Auto-derived from `DNS_DOMAIN`/`CRM_BASE_URL` when unset. |
| `IDCS_SCOPE` | string | OAuth scope. Default `openid profile email` (`shop/.env.example:94`). |
| `IDCS_POST_LOGOUT_REDIRECT` | URL | Post-logout landing URL. |
| `IDCS_VERIFY_JWT` | bool | Default `true`. Set `false` only in air-gapped dev environments where the JWKS endpoint is unreachable. |

The IAM Identity Domain must have a **Confidential Application** registered
with Authorization Code grant and scopes `openid`, `profile`, `email`.

---

## G. Public DNS, TLS, and Image Tags

### DNS

| Variable | Type | Description |
|----------|------|-------------|
| `DNS_DOMAIN` | string | Base public domain. Shop is served at `shop.${DNS_DOMAIN}` and CRM at `crm.${DNS_DOMAIN}`. When unset locally, services bind on `localhost:8080`. |
| `SHOP_PUBLIC_URL` | URL | Explicit override for the Shop public URL. Derived from `DNS_DOMAIN` when unset. |
| `CORS_ALLOWED_ORIGINS` | CSV | Comma-separated list of allowed origins. Derived from `DNS_DOMAIN` when unset. |

### TLS

The Helm chart **does not** create TLS secrets. Reference a pre-created secret
via `ingress.tls.secretName` (default `octo-apm-demo-tls`) or disable TLS by
setting `ingress.tls.enabled=false`. <!-- VERIFY: TLS certificate provisioning depends on the cluster's cert-manager or hand-rolled issuance flow -->

### Image tags

| Variable | Default | Image |
|----------|---------|-------|
| `SHOP_IMAGE_TAG` | `latest` | `octo-drone-shop` |
| `CRM_IMAGE_TAG` | `latest` | `enterprise-crm-portal` |
| `JAVA_APM_IMAGE_TAG` | `latest` | `octo-apm-java-demo` |
| `WORKFLOW_GATEWAY_IMAGE_TAG` | `latest` | `octo-workflow-gateway` |

Production deployments should pin immutable tags (e.g., `2026.05.16-1`)
rather than `latest`.

---

## H. Container Registry (OCIR)

The Compute deployment requires pull credentials. Helm uses an
`imagePullSecrets` reference (`ocir-pull-secret` by default).

| Variable | Description |
|----------|-------------|
| `OCIR_REGION` | OCIR region (e.g., `eu-frankfurt-1`). Default declared at `deploy/vm/.env.template:5` and `deploy/helm/octo-apm-demo/values.yaml:29`. |
| `OCIR_TENANCY` | OCIR namespace (tenancy object storage namespace). Required for Helm: `global.image.tenancy`. |
| `OCIR_REGISTRY` | Fully-qualified registry host (e.g., `<OCIR_REGION>.ocir.io`). Used by `deploy/compute/install.sh` for `podman login`. |
| `OCIR_USERNAME` | OCIR username — typically `<TENANCY_NAMESPACE>/<user-email>`. |
| `OCIR_AUTH_TOKEN` | OCIR auth token. Generated in OCI Console → Identity → Users → Auth Tokens. |

Image paths follow the pattern:

```text
<OCIR_REGION>.ocir.io/<OCIR_TENANCY>/octo-drone-shop:<tag>
<OCIR_REGION>.ocir.io/<OCIR_TENANCY>/enterprise-crm-portal:<tag>
<OCIR_REGION>.ocir.io/<OCIR_TENANCY>/octo-apm-java-demo:<tag>
<OCIR_REGION>.ocir.io/<OCIR_TENANCY>/octo-workflow-gateway:<tag>
```

---

## I. Helm Values Override Reference

Top-level keys in `deploy/helm/octo-apm-demo/values.yaml`:

| Key | Purpose |
|-----|---------|
| `global.dnsDomain` | Public base domain (default `example.com` — override). |
| `global.ociRegion` | OCI region for resources (default `eu-frankfurt-1`). |
| `global.serviceNamespace` | OTel namespace tag (default `octo`). |
| `global.stackName` | Stack identity (default `octo-apm-demo`). |
| `global.monitoringNamespace` | OCI Monitoring custom namespace (default `octo_apm_demo`). |
| `global.okeClusterName` | Cluster name tag (default `octo-apm-demo-oke`). |
| `global.environment` | Environment label (default `production`). |
| `global.image.region` / `.tenancy` / `.tag` / `.pullPolicy` / `.pullSecretName` | OCIR coordinates. `tenancy` is **required**. |
| `global.ociAuthMode` | One of `instance_principal` or `workload_identity`. |
| `secrets.create` | When `true`, the chart renders secrets from `secrets.data`. Default `false` (chart only references pre-created secrets). |
| `secrets.atpWallet` / `secrets.atpWalletB64` | ATP wallet zip provided via `--set-file`. |

### Per-service Helm sections

Each of `shop`, `crm`, `javaGateway`, `workflowGateway` exposes:

| Key | Default (shop / crm shown) |
|-----|----------------------------|
| `enabled` | `true` |
| `namespace` | `octo-drone-shop` / `enterprise-crm` |
| `subdomain` | `shop` / `crm` |
| `replicas` | `2` |
| `image.repository` | `octo-drone-shop` / `enterprise-crm-portal` |
| `image.region` / `.tenancy` / `.tag` | Inherits from `global.image.*` when empty |
| `resources.requests.cpu` | `250m` |
| `resources.requests.memory` | `512Mi` |
| `resources.limits.cpu` | `"2"` |
| `resources.limits.memory` | `2Gi` |
| `autoscaling.enabled` | `true` |
| `autoscaling.minReplicas` / `maxReplicas` | `2` / `6` |
| `autoscaling.cpuTargetUtilization` | `70` |
| `autoscaling.memoryTargetUtilization` | `75` |
| `pdb.enabled` / `pdb.minAvailable` | `true` / `1` |
| `service.type` / `service.port` | `ClusterIP` / `8080` |
| `env.extra` | Map of additional env vars merged into the deployment |

The `javaGateway` and `workflowGateway` sections use smaller defaults
(`100m`/`128Mi`–`384Mi`) appropriate for sidecar workloads. `workflowGateway`
additionally exposes `pollSeconds` (`90`) and `selectaiTimeoutSeconds` (`30`).

### Ingress and namespaces

| Key | Default | Notes |
|-----|---------|-------|
| `ingress.enabled` | `true` | Set `false` if exposing via LoadBalancer Services only. |
| `ingress.className` | `nginx` | Override for `oci-native-ingress-controller`. |
| `ingress.annotations` | nginx SSL redirect | Replace wholesale for non-nginx controllers. |
| `ingress.tls.enabled` | `true` | Chart does **not** create the secret. |
| `ingress.tls.secretName` | `octo-apm-demo-tls` | Pre-create in each target namespace. |
| `namespaces.create` | `true` | Set `false` when namespaces are managed by GitOps. |
| `tetragon.enabled` | `true` | Deploys Cilium Tetragon as a privileged DaemonSet emitting eBPF telemetry to `/var/log/tetragon`. |

### Kubernetes secret names

When `secrets.create=true`, the chart renders the following Opaque secrets
into every enabled namespace (`shop.namespace`, `crm.namespace`):

| Secret | Keys |
|--------|------|
| `octo-atp` | `dsn`, `username`, `password`, `wallet-password` |
| `octo-auth` | `token-secret`, `internal-service-key`, `app-secret-key`, `bootstrap-admin-password` |
| `octo-apm` | `endpoint`, `private-key`, `public-key`, `rum-endpoint`, `rum-web-application-ocid` |
| `octo-logging` | `log-group-id`, `log-id`, `log-chaos-audit-id`, `log-security-id` |
| `octo-oci-config` | `compartment-id`, `genai-endpoint`, `genai-model-id`, `selectai-profile-name` |
| `octo-llmetry` | `langfuse-enabled`, `langfuse-host`, `langfuse-public-key`, `langfuse-secret-key`, `langfuse-otel-export-enabled` |
| `octo-sso` | `idcs-domain-url`, `idcs-client-id`, `idcs-client-secret` |
| `octo-atp-wallet` | binary `wallet.zip` (base64-encoded) |

When `secrets.create=false` (the default), these secret names must already
exist in each target namespace before `helm install`.

---

## J. Synthetic Demo Data

A scheduled job creates synthetic corporate users and orders so dashboards have
non-empty data. The default email domain is `apex.example.test`, a reserved
test domain that does not resolve.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SYNTHETIC_USERS_ENABLED` | bool | `true` | Master switch. Disable to keep the database empty. |
| `SYNTHETIC_USER_EMAIL_DOMAIN` | string | `apex.example.test` | Email domain for generated users. Override only via ignored env files when impersonation is required. |
| `SYNTHETIC_USER_COUNT` | int | `12` | Number of users created per run. |
| `SYNTHETIC_USER_ORDER_COUNT` | int | `6` | Orders per generated user. |
| `SYNTHETIC_USER_DELETE_AFTER_DAYS` | int (days) | `7` | TTL for generated records. |
| `SYNTHETIC_USER_JOB_TIMEOUT_SECONDS` | int (seconds) | `30` | Per-run timeout. |

The CRM also seeds page-view metadata for the dashboards via these per-service
settings (`shop/.env.example:23-24`):

| Variable | Default |
|----------|---------|
| `SEED_USER_EMAIL_DOMAIN` | `example.invalid` |
| `SEED_PAGEVIEW_IP_PREFIX` | `198.18.0.` |

> `198.18.0.0/15` is the IANA-reserved benchmarking range — using it ensures
> seed data never collides with real client IPs.

---

## K. Chaos and Simulation Toggles (CRM)

Declared at `crm/.env.example:128-134`. Runtime-toggleable from the CRM
operations console:

| Variable | Default | Effect |
|----------|---------|--------|
| `SIMULATE_DB_LATENCY` | `false` | Inject artificial DB latency on reads. |
| `SIMULATE_DB_DISCONNECT` | `false` | Force periodic pool resets. |
| `SIMULATE_MEMORY_LEAK` | `false` | Slowly grow a per-process buffer. |
| `SIMULATE_CPU_SPIKE` | `false` | Burn CPU on a background coroutine. |
| `SIMULATE_SLOW_QUERIES` | `false` | Emit deliberately inefficient SQL for APM dashboards. |

---

## L. Security Controls (CRM)

| Variable | Default | Description |
|----------|---------|-------------|
| `SECURITY_LOG_ENABLED` | `true` | Emit audit events to the OCI security log (`OCI_LOG_SECURITY_ID`). |
| `SESSION_TIMEOUT_SECONDS` | `3600` | HTTP session TTL. |
| `MAX_LOGIN_ATTEMPTS` | `5` | Account lockout threshold. |

---

## M. OCI Console Drilldown Links

Optional URLs surfaced in the in-app "Integrations" page. All are tenancy-
specific and have no defaults.

| Variable | Description |
|----------|-------------|
| `APM_CONSOLE_URL` | APM domain console URL. |
| `OPSI_CONSOLE_URL` | Operations Insights console URL. |
| `DB_MANAGEMENT_CONSOLE_URL` | Database Management console URL. |
| `LOG_ANALYTICS_CONSOLE_URL` | Log Analytics console URL. |
| `CONTROL_PLANE_URL` | Optional CRM Integrations control-plane URL. |
| `PLATFORM_BACKEND_URL` | Optional CRM Integrations backend URL. |

<!-- VERIFY: console URLs are tenancy-specific and built from the OCI Console region + service paths -->

---

## N. Splunk HEC (optional)

Both services can mirror logs to Splunk via HTTP Event Collector when present:

| Variable | Description |
|----------|-------------|
| `SPLUNK_HEC_URL` | Splunk HEC endpoint URL. |
| `SPLUNK_HEC_TOKEN` | HEC token. Prefer `SPLUNK_HEC_TOKEN_FILE` for mounted secrets. |

---

## O. Load Balancer Subnet (Tenancy-portable)

| Variable | Description |
|----------|-------------|
| `OCI_LB_SUBNET_OCID` | Tenancy-specific subnet OCID consumed by `deploy/k8s/deployment.yaml` when provisioning a LoadBalancer Service. <!-- VERIFY: subnet OCID is tenancy-specific and must reference a public regional subnet --> |

---

## Configuration Quickstart

### Minimum env vars for a local stack

For a laptop run via `docker-compose` (`deploy/local-stack/`), the following
variables are sufficient:

```bash
# Identity
ENVIRONMENT=dev
DNS_DOMAIN=                  # leave empty for localhost
INTERNAL_SERVICE_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
AUTH_TOKEN_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
APP_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
BOOTSTRAP_ADMIN_PASSWORD=    # set a local-only password

# Database (skip ATP — use local PostgreSQL for CRM)
CRM_DB_PASSWORD=             # local-only

# Disable optional integrations
OCI_AUTH_MODE=config_file
PAYMENT_PROVIDER=simulated
LLMETRY_ENABLED=true
LANGFUSE_ENABLED=false
SYNTHETIC_USERS_ENABLED=true
```

### Minimum env vars for a production OCI deployment

For OKE via Helm, populate the seven referenced secrets (see Section I) and
the following Helm values:

```yaml
global:
  dnsDomain: ${DNS_DOMAIN}
  ociRegion: <OCI_REGION>
  image:
    region: <OCIR_REGION>
    tenancy: <OCIR_TENANCY>
    tag: 2026.05.16-1          # pin an immutable tag
  ociAuthMode: instance_principal
```

Required secret keys before `helm install`:

* `octo-atp`: `dsn`, `username`, `password`, `wallet-password`
* `octo-auth`: `token-secret`, `internal-service-key`, `app-secret-key`, `bootstrap-admin-password`
* `octo-apm`: `endpoint`, `private-key`, `public-key`, `rum-endpoint`, `rum-web-application-ocid`
* `octo-logging`: `log-group-id`, `log-id`, `log-chaos-audit-id`, `log-security-id`
* `octo-oci-config`: `compartment-id`, `genai-endpoint`, `genai-model-id`, `selectai-profile-name`
* `octo-atp-wallet`: binary `wallet.zip`

SSO (`octo-sso`) and Langfuse (`octo-llmetry`) secrets are optional and can be
left empty when those integrations are disabled.

---

## File-to-Variable Index

| Source file | Section(s) covered |
|-------------|--------------------|
| `deploy/vm/.env.template` | All — single-host reference template |
| `deploy/compute/runtime.env.template` | All — two-instance Compute template |
| `shop/.env.example` | Application, APM/RUM, OCI Monitoring, Logging, SSO |
| `crm/.env.example` | Application, APM, Database pool, Chaos toggles, SSO |
| `deploy/helm/octo-apm-demo/values.yaml` | Helm overrides (Section I) |
| `deploy/helm/octo-apm-demo/templates/secrets.yaml` | Secret name and key inventory |
| `shop/server/observability/oci_monitoring.py` | `OCI_MONITORING_INTERVAL_SECONDS` read |
| `crm/server/observability/oci_monitoring.py` | `OCI_MONITORING_INTERVAL_SECONDS` read |
