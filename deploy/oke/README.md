# OKE deployment — octo-apm-demo

Production path: Drone Shop + Admin/CRM FastAPI services, the Java
payment-gateway/app-server simulator, and the Workflow Gateway on an OKE
cluster behind OCI Load Balancers with WAF, sharing an Autonomous Database, fully wired into
APM + RUM + OCI Logging → Log Analytics + Stack Monitoring.

Dedicated Langfuse test path: use
[`deploy-langfuse.sh`](deploy-langfuse.sh) to deploy a low-resource
`octo-langfuse` stack for `langfuse.octodemo.cloud`. The script validates
OCI/Kubernetes rights, enforces the target VCN by default, creates platform
secrets at deploy time, and can optionally update the Shop `octo-llmetry`
secret after a Langfuse project is created.

Read-only OCTO DEMO capacity check: use
[`check-small-cluster.sh`](check-small-cluster.sh) before creating any OKE
resources in `emdemo`. It verifies the target VCN/subnets from the Compute
outputs, lists existing clusters, checks OKE cluster quota, E4/E5 Flex OCPU
availability, block-volume headroom, and Service Connector Hub availability.
It does not create, update, or delete resources.

Current `emdemo` result on May 11, 2026:

- Quota/capacity is sufficient for a small two-node test cluster in the OCTO
  project compartment: `cluster-count available=3`, E4/E5 Flex OCPUs
  available in `Njav:PHX-AD-1`, and enough Block Volume capacity.
- No ACTIVE OKE cluster currently lives in the OCTO project VCN. Existing
  clusters (`cluster2-basic`, `cluster-n`, `cluster3`) are ACTIVE but belong
  to the older quickstart VCN, so `deploy-langfuse.sh --check` intentionally
  refuses to use them.
- Service Connector Hub quota is exhausted (`available=0`, `used=7`), so a new
  OCI Logging -> Log Analytics route for OKE app logs is blocked until quota is
  increased or an approved OCTO-owned connector is consolidated.

## Names used by this path

| Concern | Value |
|---|---|
| Shop namespace | `octo-drone-shop` |
| CRM namespace | `enterprise-crm` |
| Shop Deployment | `octo-drone-shop` |
| CRM Deployment | `enterprise-crm-portal` |
| Java payment gateway Deployment | `octo-apm-java-demo` |
| Workflow Gateway Deployment | `octo-workflow-gateway` |
| Shop in-cluster URL | `http://octo-drone-shop.octo-drone-shop.svc.cluster.local:8080` |
| CRM in-cluster URL | `http://enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080` |
| Java payment gateway in-cluster URL | `http://octo-apm-java-demo.octo-drone-shop.svc.cluster.local` |
| Workflow Gateway in-cluster URL | `http://octo-workflow-gateway.octo-drone-shop.svc.cluster.local:8090` |
| Shop public hostname | `drones.${DNS_DOMAIN}` |
| CRM public hostname | `admin.${DNS_DOMAIN}` |

Deliberately different from the unified-VM names so both deployments
can co-exist on the same tenancy (different compartments / clusters)
without collisions.

## One-shot apply

```bash
./deploy/oke/check-small-cluster.sh

DNS_DOMAIN=example.test \
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
IMAGE_TAG=<immutable-image-tag> \
./deploy/oke/deploy-oke.sh
```

The script:

1. Applies namespaces + labels.
2. Checks that each namespace has the required bootstrap Secrets
   (`octo-auth`, `octo-atp`, `octo-atp-wallet`, `octo-oci-config`,
   `octo-apm`, `octo-logging`, and `ocir-pull-secret`) and fails fast
   when any are missing. Recreate them with
   `deploy/oke/bootstrap-emdemo-secrets.sh`.
3. If the OCI Secrets Store CSI driver CRD is installed, applies a
   per-namespace `SecretProviderClass` that pulls every secret from
   OCI Vault. Otherwise continues with plain Kubernetes Secrets.
4. envsubsts + applies the Java payment-gateway and Workflow Gateway
   Deployments/Services in the Shop namespace.
5. envsubsts + applies the Deployment/Service/NodePort/HPA/PDB for Shop and
   CRM. The Shop container points `JAVA_APM_SERVICE_URL` at the Java
   service, points `WORKFLOW_API_BASE_URL` at the Workflow Gateway, and
   enables the simulated payment gateway.
6. Applies the NetworkPolicies last so pod-to-pod traffic across
   namespaces works immediately.
7. Waits for rollouts and prints the NodePort services used by the
   existing OCI Load Balancer backend sets.

`OCI_REGION` is the Monitoring/APM region used for OCI SDK calls from pods.
It defaults from `OCI_CLI_REGION`, then `OCI_REGION_ID`, then `us-phoenix-1`.
Keep it explicit when OCIR images are pulled from a different region than the
APM domain.

## emdemo small OKE cluster path

The emdemo OKE path is deliberately staged beside the live Compute/VM
deployment. It reuses the existing VCN, ATP database, APM domain, OCI
Logging resources, and public OCI Load Balancer, but it does not change
host routing until an explicit cutover.

Capacity target:

- Cluster: `octo-apm-demo-oke`
- Workers: `2 x VM.Standard.E5.Flex`
- Per worker: `2 OCPU / 16 GiB`
- Total requested worker capacity: `4 OCPU / 32 GiB`
- Worker subnet: dedicated private subnet `<OKE_WORKER_SUBNET_CIDR>`
- Public app names after cutover: `drones.<DNS_DOMAIN>` and
  `admin.<DNS_DOMAIN>`

Provision and deploy:

```bash
./deploy/oke/ensure-emdemo-worker-subnet.sh

OKE_WORKER_SUBNET_ID=<worker-subnet-ocid> \
OKE_NODE_POOL_NAME=octo-apm-demo-oke-pool-private \
./deploy/oke/create-emdemo-small-cluster.sh

./deploy/oke/bootstrap-emdemo-secrets.sh

OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<OCIR_NAMESPACE> \
IMAGE_TAG=<image-tag> \
DNS_DOMAIN=<DNS_DOMAIN> \
OKE_CLUSTER_NAME=octo-apm-demo-oke \
./deploy/oke/deploy-oke.sh

./deploy/oke/wire-existing-lb-backends.sh --apply
./deploy/oke/install-oci-kubernetes-monitoring.sh
```

Current emdemo validation, May 13, 2026:

- OKE cluster `octo-apm-demo-oke` is active with two private workers in
  the dedicated OKE worker subnet.
- Worker capacity is `4 OCPU / 32 GiB` total. `kubectl top nodes`
  after validation showed roughly 6% CPU and 18-25% memory per node.
- Deployed image tag: `oke-20260513122023-shop-downstream` for Shop,
  `oke-20260513103616-aecfbae` for Admin/CRM,
  `oke-20260513112855-java-json` for the Java payment gateway, and the
  matching immutable `octo-workflow-gateway` image for Select AI/workflow
  proxy traffic. Structured stdout events are parsed by `SOC Application Logs`.
- OKE APM service names are `octo-drone-shop-oke`,
  `enterprise-crm-portal-oke`, `octo-java-app-server-oke`, and
  `octo-workflow-gateway-oke`, all exporting to the existing
  `octo-apm-demo` APM domain.
- The Shop container sets `JAVA_APM_SERVICE_NAME=octo-java-app-server-oke`
  and emits `java_apm.service.name` / `payment.processor.name` in OCI
  Logging records. The Log Analytics checkout and trace saved searches map
  these to the existing `Downstream Component` field.
- Shop, Admin/CRM, and Java are running with 2 replicas, HPA minimum 2,
  PDB `minAvailable: 1`, and container UID `10001`; Workflow Gateway runs
  as UID `10001` with one low-resource replica because it is a scoped
  admin/Select AI proxy.
- The existing public OCI LB has green staged OKE backend sets:
  `oke_shop_nodeport` and `oke_admin_nodeport`, each with two healthy
  node backends. The active host-routing policy still points to backend
  sets `shop` and `crm`; those active backend sets now round-robin across
  the original VM backend plus both OKE NodePort backends.
- Focused Playwright payment-gateway validation passed through OKE
  port-forwards for Google Pay, Apple Pay, and declined Visa card flows.
- OCI Kubernetes Monitoring is deployed in namespace `oci-onm`; Log
  Analytics collectors, tcpconnect collectors, discovery, and the
  Management Agent are running. The installer uses ephemeral
  Management Agent state by default for this low-resource demo cluster.
  The live ONM release is revision 4.
- The OCI Kubernetes Monitoring installer is pinned to
  `oci-onm-4.2.1` with SHA256 verification and supports `APPLY=false`
  for a no-write render/server-side preflight before live changes.
  `OCI_ONM_ENABLE_SERVICE_LOGS=false` is the default so the discovery
  CronJob does not invoke Resource Manager to create optional service
  logs on this small demo cluster.
- The ONM config sends container and tcpconnect logs directly to Log
  Analytics through the OCI Log Analytics Fluentd plugin. It does not
  require a Service Connector Hub connector. The emdemo Service Connector
  Hub quota is still exhausted (`used=7`, `available=0`), so new OCI
  Logging -> Log Analytics connectors still require quota cleanup or reuse
  of an existing approved connector.
- The ONM metrics config writes to compartment-scoped OCI Monitoring under
  `mgmtagent_kubernetes_metrics` with cluster name `octo-apm-demo-oke`.
  Existing Log Analytics entity name `octo-apm-demo-oke_nullZ` is reused by
  cloud resource ID because OCI Log Analytics does not support entity rename;
  new ONM log metadata and metric dimensions use the clean cluster name.
- `octo-llmetry` is populated for both namespaces; Shop readiness reports
  `langfuse_configured=true`.
- Log Analytics receives OKE container rows with Kubernetes namespace,
  pod, and container dimensions for `octo-drone-shop`, `enterprise-crm`,
  the Java payment gateway, and Workflow Gateway.
- Repo-owned OKE ONM health searches scope on
  `Kubernetes Cluster Name = octo-apm-demo-oke`. Do not reintroduce a broad
  namespace-only fallback for `oci-onm`, because older clusters in the same
  Log Analytics namespace can use that namespace too.

`wire-existing-lb-backends.sh --apply` only creates or updates the
dedicated OKE backend sets (`oke_shop_nodeport` and
`oke_admin_nodeport`). `wire-existing-lb-backends.sh --round-robin-active
--apply` updates the active `shop` and `crm` backend sets to include the
VM and OKE NodePort backends without changing the listener, certificate,
or host-routing policy. Use `--rollback-active-vm` to restore the active
backend sets to VM-only. Use `--cutover` only during the approved migration
window; use `--rollback-vm` to point routing back to the VM backend sets.

## What it publishes

Each service gets two Kubernetes Services:

| Service | Type | Purpose |
|---|---|---|
| `octo-drone-shop` | ClusterIP | in-cluster callbacks (used by CRM) |
| `octo-apm-java-demo` | ClusterIP | Java payment gateway, antifraud, and app-server spans used by Shop checkout |
| `octo-workflow-gateway` | ClusterIP | Select AI/workflow proxy used by same-origin Shop/Admin routes |
| `octo-drone-shop-lb` | NodePort `30080` | staged shop traffic from the existing OCI LB |
| `enterprise-crm-portal` | ClusterIP | in-cluster callbacks (used by Shop) |
| `enterprise-crm-portal-lb` | NodePort `30081` | staged admin traffic from the existing OCI LB |

The public OCI Load Balancer remains managed outside Kubernetes. This is
intentional for the transition period: the Compute/VM and OKE backends
can co-exist, and host routing can move independently after OKE health
checks are green.

## Scaling

Both FastAPI Deployments have HPA from **2 to 4 replicas** driven by 70%
CPU and 75% memory averages. Adjust `minReplicas` / `maxReplicas` for
production load. PodDisruptionBudget pins `minAvailable: 1` so node
drains during upgrades never kill every pod at once.

## Production guardrails

- `deploy-oke.sh` requires an immutable `IMAGE_TAG` and refuses `latest`
  unless `ALLOW_LATEST_IMAGE_TAG=true` is explicitly set.
- `deploy-oke.sh` verifies the active kubectl context matches
  `OKE_CLUSTER_NAME` before applying manifests.
- Server-side Kubernetes dry-run is enabled by default before every
  rendered manifest apply (`SERVER_DRY_RUN=true`).
- Set `APPLY=false` to run the same preflight and server-side manifest
  validation without changing the cluster.
- `install-oci-kubernetes-monitoring.sh` also supports `APPLY=false`
  and renders the Helm manifest first. It fails if the rendered
  discovery CronJob would re-enable Resource Manager service-log
  automation while `OCI_ONM_ENABLE_SERVICE_LOGS=false`.
- NetworkPolicies allow the existing LB/NodePort path only from
  `OKE_EXTERNAL_INGRESS_CIDR`, defaulting to the emdemo VCN range
  `10.42.0.0/16`.
- Pods disable service-account token automount, run as UID/GID `10001`
  where the image supports it, use the runtime-default seccomp profile,
  drop Linux capabilities, and disallow privilege escalation.

## Observability wiring (same as VM path — just different Secrets)

Every observability env var is read from a named Kubernetes Secret so
the OKE Deployment can be rolled independently of secret rotation:

| Env var | Secret:key |
|---|---|
| `OCI_APM_ENDPOINT` | `octo-apm:endpoint` |
| `OCI_APM_PRIVATE_DATAKEY` | `octo-apm:private-key` |
| `OCI_APM_PUBLIC_DATAKEY` | `octo-apm:public-key` |
| `OCI_APM_RUM_ENDPOINT` | `octo-apm:rum-endpoint` |
| `OCI_APM_WEB_APPLICATION` | `octo-apm:rum-web-application-ocid` |
| `OCI_LOG_ID` | `octo-logging:log-id` |
| `OCI_LOG_GROUP_ID` | `octo-logging:log-group-id` |
| `OCI_COMPARTMENT_ID` | `octo-oci-config:compartment-id` |
| `OCI_REGION` | rendered from `OCI_REGION` / `OCI_CLI_REGION` / `OCI_REGION_ID` |
| `OCI_MONITORING_NAMESPACE` | manifest default `octo_apm_demo` |
| `OCI_GENAI_ENDPOINT` | `octo-oci-config:genai-endpoint` |
| `OCI_GENAI_MODEL_ID` | `octo-oci-config:genai-model-id` |
| `SELECTAI_PROFILE_NAME` | `octo-oci-config:selectai-profile-name` |
| `IDCS_CLIENT_SECRET` | `octo-sso:idcs-client-secret` |

Every workload also sets `SERVICE_NAMESPACE=octo`, `DEMO_STACK_NAME=octo-apm-demo`,
`SERVICE_INSTANCE_ID=$(POD_NAME)`, `OCI_MONITORING_NAMESPACE=octo_apm_demo`,
and `OTEL_RESOURCE_ATTRIBUTES` with the pod and namespace identifiers. Shop
checkout logs and spans carry `workflow.id=checkout`, `workflow.step=payment`,
`orders.order_id`, `payment.gateway.request_id`, `payment.gateway.step`,
`payment.network.transaction_id`, `oracleApmTraceId`, and `oracleApmSpanId`
so Log Analytics can pivot directly to APM traces and payment-gateway spans.

`oracleApmTraceId` correlation is automatic: the app's OTel exporter
stamps the active trace id onto every OCI Logging record it emits
(via the `oci.loggingingestion` SDK). OKE stdout rows annotated for ONM use
the `SOC Application Logs` parser/source contract; connector-fed OCI Logging
rows appear as `OCI Unified Schema Logs` and are covered by
`connector-live-log-coverage.sql`.

The Shop and Admin pods also publish OCI Monitoring custom metrics under
`octo_apm_demo`. These metrics are deliberately low-cardinality and safe for
alarms and dashboard widgets: app health, uptime, request/error interval
counts, checkout/order counts, auth success/failure counts, security events,
dashboard loads, DB latency, CRM sync age, and low-stock inventory. High-cardinality
journey details stay in APM traces and Log Analytics fields instead of metric
dimensions.

For a single pre-demo signal check, call each app's
`/api/observability/melts` endpoint and run
`deploy/oci/log_analytics/searches/melts-collection-completeness.sql` in Log
Analytics. The saved search validates structured app logs, connector-fed OCI
Unified Schema logs, and OKE Kubernetes container logs in one result set.

## Runtime containers

| Container | Image | Default resources | Role |
|---|---|---|---|
| Shop | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${IMAGE_TAG}` | 2 replicas, `250m/512Mi` request, `1 CPU/1536Mi` limit | Storefront, checkout, OCI APM/RUM, OCI Logging SDK, Log Analytics correlation fields |
| Admin/CRM | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal:${IMAGE_TAG}` | 2 replicas, `250m/512Mi` request, `1 CPU/1536Mi` limit | Admin site, orders, OCI Coordinator scope, CRM/order linkage |
| Java payment gateway | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-apm-java-demo:${IMAGE_TAG}` | 2 replicas, `100m/384Mi` request, `500m/768Mi` limit | Simulated Apple Pay, Google Pay, Visa, Mastercard, antifraud, processor, and network authorization spans |
| Workflow Gateway | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-workflow-gateway:${IMAGE_TAG}` | 1 replica, `100m/128Mi` request, `500m/512Mi` limit | Admin-scoped Select AI/workflow proxy, ATP SQL spans, and workflow logs |
| Load control | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-load-control:${IMAGE_TAG}` | 2 replicas, `100m/128Mi` request, `500m/512Mi` limit | Workload profile launcher with FastAPI/HTTPX OTEL spans |
| Async worker | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-async-worker:${IMAGE_TAG}` | 2 replicas, `100m/128Mi` request, `500m/256Mi` limit | Redis stream consumer with script, Redis, and HTTPX OTEL spans |
| Remediator | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-remediator:${IMAGE_TAG}` | 2 replicas, `100m/128Mi` request, `500m/256Mi` limit | Alarm remediation API with FastAPI OTEL spans |
| Object pipeline | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-object-pipeline:${IMAGE_TAG}` | 2 replicas, `100m/128Mi` request, `500m/256Mi` limit | OCI Object Storage event API with FastAPI OTEL spans |
| Traffic generator | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-traffic-generator:${IMAGE_TAG}` | 1 replica, `100m/128Mi` request, `500m/256Mi` limit | Synthetic buyer sessions with root `traffic.session` spans |

## Cross-service contract on OKE

- Shop calls CRM at `http://enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080`
- CRM calls Shop at `http://octo-drone-shop.octo-drone-shop.svc.cluster.local:8080`
- Both send `X-Internal-Service-Key: $INTERNAL_SERVICE_KEY` — the
  shared value is pulled from `octo-auth:internal-service-key` on both
  sides.
- Idempotency: shop emits `idempotency_token` (UUID5 from stable
  namespace + `(order_id, source)`); CRM side honours it via the
  composite `(source_system, source_order_id, idempotency_token)`
  pattern documented in [the cross-service contract](../../site/crm/integrations/cross-service-contract.md).

## Image build + push

Build and push the OKE images to the authenticated OCIR registry that the
worker nodes can pull from:

```bash
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<OCIR_NAMESPACE> \
IMAGE_TAG=oke-$(date -u +%Y%m%d%H%M%S) \
./deploy/oke/build-push-images.sh
```

`build-push-images.sh` no longer pushes `:latest` by default. Set
`PUSH_LATEST=true` only when you intentionally want to refresh that
convenience tag for manual testing.
The script also refuses `IMAGE_TAG=latest` by default and runs each
pushed image with `--entrypoint id -u`; the build fails unless every
runtime image reports UID `10001`, matching the OKE pod securityContext.

The root `.dockerignore` excludes local credentials and keeps BuildKit
contexts small while still allowing the three Dockerfiles to copy their
service sources and shared client packages.

## Rollback

```bash
kubectl rollout undo deployment/octo-drone-shop       -n octo-drone-shop
kubectl rollout undo deployment/enterprise-crm-portal -n enterprise-crm
```

## DNS + TLS

During the staged migration, DNS remains pointed at the existing public
OCI Load Balancer:

```
drones.${DNS_DOMAIN}    A    <PUBLIC_LB_IP>
admin.${DNS_DOMAIN}     A    <PUBLIC_LB_IP>
```

TLS options:

- **OCI Certificates service** (recommended) — create a certificate
  per hostname, reference on the LB via Terraform or the Console.
- **cert-manager + LetsEncrypt** — install cert-manager in the cluster,
  add an HTTP01 ClusterIssuer, deploy Ingress objects per hostname.

The OKE manifests ship NodePort services. TLS termination stays on the
existing OCI Load Balancer until the approved cutover.

## Known residual issue

The current OKE demo workloads do not require Kubernetes persistent
volumes. The first OCI Kubernetes Monitoring install exposed missing node
topology labels for the OCI CSI node plugin; the nodes were patched with
their OCI availability-domain and fault-domain metadata, and
`csi-oci-node` is now running with `blockvolume`, `fss`, and `lustre`
drivers registered on both workers. Keep the Management Agent on
`MGMT_AGENT_STATE_STORAGE=emptyDir` for this low-resource test cluster
unless the demo explicitly needs PVC-backed agent state.
