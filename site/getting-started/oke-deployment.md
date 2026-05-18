# OKE deployment — octo-apm-demo

Production path: Drone Shop + Admin/CRM FastAPI services, the Java
payment-gateway/app-server simulator, and the Workflow Gateway on an OKE
cluster behind OCI Load Balancers with WAF, sharing an Autonomous Database, fully wired into
APM + RUM + OCI Logging → Log Analytics + Stack Monitoring.

## Namespaces + hostnames

| Service | Namespace | Deployment | In-cluster URL | Public hostname |
|---|---|---|---|---|
| Drone Shop | `octo-drone-shop` | `octo-drone-shop` | `http://octo-drone-shop.octo-drone-shop.svc.cluster.local:8080` | `drones.${DNS_DOMAIN}` |
| Enterprise CRM | `enterprise-crm` | `enterprise-crm-portal` | `http://enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080` | `admin.${DNS_DOMAIN}` |
| Java payment gateway | `octo-drone-shop` | `octo-apm-java-demo` | `http://octo-apm-java-demo.octo-drone-shop.svc.cluster.local` | internal only |
| Workflow Gateway | `octo-drone-shop` | `octo-workflow-gateway` | `http://octo-workflow-gateway.octo-drone-shop.svc.cluster.local:8090` | internal only |

Names deliberately differ from the unified-VM path so both deployments
can co-exist on the same tenancy (different compartments or clusters)
without collisions.

## One-shot apply

```bash
DNS_DOMAIN=example.tld \
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
IMAGE_TAG=<immutable-image-tag> \
./deploy/oke/deploy-oke.sh
```

The script applies namespaces, the Java payment-gateway Deployment, the
Workflow Gateway Deployment, the Shop/CRM Deployments, staged NodePort Services, HPA
(2→4 replicas, 70% CPU / 75% memory), PDB (`minAvailable: 1`),
NetworkPolicies, and optionally a SecretProviderClass per namespace when
the OCI Secrets Store CSI driver and Vault OCID variables are available.
It fails fast when required Kubernetes Secrets are missing, rejects
mutable `latest` image tags by default, and server-side dry-runs rendered
manifests before applying them. Set `APPLY=false` to run preflight and
server-side validation without changing the cluster. The Shop container is
pre-wired with `JAVA_APM_SERVICE_URL`, `WORKFLOW_API_BASE_URL`,
`PAYMENT_PROVIDER=simulated`, and `PAYMENT_GATEWAY_SIMULATION_ENABLED=true`
so checkout emits the full Apple Pay, Google Pay, Visa, and Mastercard
simulation workflow while admin-scoped workflow/Select AI calls stay inside
the private cluster service.

## <OCI_PROFILE> staged cluster

The <OCI_PROFILE> cluster is a small private-worker OKE deployment that lives
beside the existing Compute/VM runtime until the approved traffic cutover.
It reuses the existing VCN, ATP database, APM domain, OCI Logging/Log
Analytics resources, and public OCI Load Balancer.

Current target:

- `octo-apm-demo-oke`
- `2 x VM.Standard.E5.Flex`
- `2 OCPU / 16 GiB` per worker, `4 OCPU / 32 GiB` total requested worker capacity
- dedicated private worker subnet `<OKE_WORKER_SUBNET_CIDR>`
- NodePorts `30080` for Drone Shop and `30081` for Admin/CRM
- existing public names `drones.<DNS_DOMAIN>` and `admin.<DNS_DOMAIN>`

Validated <OCI_PROFILE> state on May 13, 2026:

- Image tag `oke-20260513122023-shop-downstream` is deployed for Drone Shop,
  `oke-20260513103616-aecfbae` for Admin/CRM, Java payment gateway uses
  `oke-20260513112855-java-json`, and Workflow Gateway uses the matching
  immutable `octo-workflow-gateway` tag for structured stdout events parsed
  by `SOC Application Logs`.
- Drone Shop emits `java_apm.service.name` and `payment.processor.name` in
  checkout log records; Log Analytics saved searches expose those through the
  existing `Downstream Component` field.
- APM service names are OKE-specific:
  `octo-drone-shop-oke`, `enterprise-crm-portal-oke`, and
  `octo-java-app-server-oke`; Workflow Gateway uses
  `octo-workflow-gateway-oke`.
- Drone Shop, Admin/CRM, and Java payment gateway run with 2 replicas,
  HPA minimum 2, PDB `minAvailable: 1`, and runtime UID `10001`; Workflow
  Gateway runs as UID `10001` with one low-resource replica.
- Existing LB backend sets `oke_shop_nodeport` and
  `oke_admin_nodeport` are healthy. Public host routing remains on
  backend sets `shop` and `crm`, and those active backend sets now
  round-robin across the original VM backend plus both OKE NodePort
  backends.
- OCI Kubernetes Monitoring is installed in `oci-onm`; Log Analytics
  collectors, tcpconnect collectors, discovery, and Management Agent pods
  are running. The live release is revision 4 with Resource Manager
  service-log automation disabled for the discovery CronJob.
- ONM sends Kubernetes container and tcpconnect logs directly to Log
  Analytics through its Fluentd Log Analytics output; it does not need a
  Service Connector Hub connector. The current Service Connector Hub quota
  remains full (`used=7`, `available=0`), which only blocks additional OCI
  Logging -> Log Analytics connectors.
- Repo-owned OKE ONM searches and the `OkeOnmLogSamples` scheduled rule
  now scope on `Kubernetes Cluster Name = octo-apm-demo-oke`. Do not use
  `Namespace = oci-onm` as a standalone filter in shared Log Analytics
  namespaces because retained clusters can emit records with the same
  namespace name.
- ONM metrics are configured for `mgmtagent_kubernetes_metrics` in the Octo
  compartment with cluster name `octo-apm-demo-oke`. The older Log
  Analytics entity name is reused by cloud-resource-id because Log Analytics
  entity names cannot be renamed, but new log metadata and metric dimensions
  use the clean cluster name.
- The OKE `octo-llmetry` secret is populated in both app namespaces, and
  Drone Shop readiness reports `langfuse_configured=true`.
- Google Pay, Apple Pay, and declined Visa checkout E2E tests passed against the OKE
  shop service, producing APM spans for browser/user action, checkout,
  payment gateway, Java antifraud/authorization, network routing, Workflow
  Gateway/Select AI when exercised, CRM order sync, and ATP writes.

Runbook:

```bash
./deploy/oke/ensure-<OCI_PROFILE>-worker-subnet.sh
./deploy/oke/create-<OCI_PROFILE>-small-cluster.sh
./deploy/oke/bootstrap-<OCI_PROFILE>-secrets.sh

OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<OCIR_NAMESPACE> \
IMAGE_TAG=<image-tag> \
DNS_DOMAIN=<DNS_DOMAIN> \
OKE_CLUSTER_NAME=octo-apm-demo-oke \
./deploy/oke/deploy-oke.sh

./deploy/oke/wire-existing-lb-backends.sh --apply
./deploy/oke/wire-existing-lb-backends.sh --round-robin-active --apply
./deploy/oke/install-oci-kubernetes-monitoring.sh
```

`wire-existing-lb-backends.sh --apply` creates or updates
`oke_shop_nodeport` and `oke_admin_nodeport`; it does not change live host
routing. `--round-robin-active --apply` keeps host routing unchanged but
adds the OKE NodePort backends to active `shop` and `crm`; use
`--rollback-active-vm` to return those active backend sets to VM-only.
Use `--cutover` only when the VM-to-OKE migration window starts.
Run `APPLY=false ./deploy/oke/install-oci-kubernetes-monitoring.sh`
before changing ONM in-place. The installer is pinned to `oci-onm-4.2.1`
with SHA256 validation, renders the Helm chart before upgrade, and fails
if optional Resource Manager service-log automation would be enabled while
`OCI_ONM_ENABLE_SERVICE_LOGS=false`.

Full walkthrough: [deploy/oke/README.md](%%GITHUB_REPO_URL%%/blob/main/deploy/oke/README.md).

## Security posture

| Control | Where |
|---|---|
| WAF (DETECTION → BLOCK) | OCI LB annotation `oci.oraclecloud.com/waf-policy-ocid` |
| TLS | OCI Certificates service attached to the LB, or cert-manager + LetsEncrypt |
| Cross-service auth | `X-Internal-Service-Key: $INTERNAL_SERVICE_KEY` on every cross-service POST |
| Idempotent order sync | `idempotency_token` (UUID5, stable per `(order_id, source)`) |
| Network segmentation | Per-namespace `NetworkPolicy` allowing only explicit inter-namespace traffic plus the configured LB/NodePort VCN ingress CIDR |
| Secret handling | `SecretProviderClass` from OCI Vault via the Secrets Store CSI driver (optional; falls back to K8s Secrets) |
| Pod safety | Non-root UID/GID, no service-account token automount, dropped Linux capabilities, no privilege escalation, runtime-default seccomp, resource requests + limits, liveness + readiness probes on `/ready`, PDB, rolling updates with `maxUnavailable: 0` |

## Full observability — same as VM path, different Secrets

| Signal | Env var | Secret reference | Destination |
|---|---|---|---|
| Traces | `OCI_APM_ENDPOINT`, `OCI_APM_PRIVATE_DATAKEY` | `octo-apm:endpoint` + `private-key` | OCI APM Domain |
| RUM | `OCI_APM_RUM_ENDPOINT`, `OCI_APM_PUBLIC_DATAKEY`, `OCI_APM_WEB_APPLICATION` | `octo-apm:rum-endpoint` + `public-key` + `rum-web-application-ocid` | OCI APM RUM |
| Logs | `OCI_LOG_ID`, `OCI_LOG_GROUP_ID` | `octo-logging:log-id` + `log-group-id` | OCI Logging custom log. Connector-fed rows land as `OCI Unified Schema Logs`; OKE stdout rows annotated for ONM land as `SOC Application Logs`. |
| Metrics | `OCI_COMPARTMENT_ID`, `OCI_MONITORING_NAMESPACE` | `octo-oci-config:compartment-id` | OCI Monitoring custom metrics + alarms |

All OKE containers set `SERVICE_NAMESPACE=octo`, `DEMO_STACK_NAME=octo-apm-demo`,
`SERVICE_INSTANCE_ID=$(POD_NAME)`, and `OTEL_RESOURCE_ATTRIBUTES` with pod
and namespace details. Checkout spans and logs include `workflow.id`,
`workflow.step`, `orders.order_id`, `payment.gateway.request_id`,
`payment.gateway.step`, `payment.network.transaction_id`, `oracleApmTraceId`,
and `oracleApmSpanId` for APM ↔ Log Analytics troubleshooting.

**Correlation**: `oracleApmTraceId` is stamped onto every Logging record
the app emits via `oci.loggingingestion`. The Log Analytics parser
promotes it to a searchable column, so trace-to-log pivots work in
both directions: APM → Log Analytics search, Log Analytics → APM
trace explorer URL.

Trace Explorer saved queries include both the existing VM service names
and the OKE `*-oke` names so operators can troubleshoot during the
parallel-run period.

## Runtime containers

| Container | Image | Default resources | Observability role |
|---|---|---|---|
| Shop | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop:${IMAGE_TAG}` | 2 replicas, `250m/512Mi` request, `1 CPU/1536Mi` limit | Storefront, checkout, RUM, OCI Logging SDK, Log Analytics fields |
| Admin/CRM | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal:${IMAGE_TAG}` | 2 replicas, `250m/512Mi` request, `1 CPU/1536Mi` limit | Admin operations, orders, CRM links, OCI Coordinator scope |
| Java payment gateway | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-apm-java-demo:${IMAGE_TAG}` | 2 replicas, `100m/384Mi` request, `500m/768Mi` limit | Java app-server, antifraud, processor, and network authorization spans |
| Workflow Gateway | `${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-workflow-gateway:${IMAGE_TAG}` | 1 replica, `100m/128Mi` request, `500m/512Mi` limit | Admin-scoped Select AI/workflow proxy, ATP SQL spans, and workflow logs |

## Image build + push

For <OCI_PROFILE>, publish OKE images to the authenticated Frankfurt OCIR
registry until Phoenix OCIR auth is corrected:

```bash
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<OCIR_NAMESPACE> \
IMAGE_TAG=oke-$(date -u +%Y%m%d%H%M%S) \
./deploy/oke/build-push-images.sh
```

The root `.dockerignore` excludes local credential material from Docker
contexts and keeps the OKE image build small enough for local BuildKit.
The build script does not push a mutable `:latest` tag unless
`PUSH_LATEST=true` is explicitly set, refuses `IMAGE_TAG=latest` by
default, and runs each pushed image with `--entrypoint id -u` so a tag
cannot be promoted unless it matches the OKE runtime UID `10001`.

## Provisioning the observability resources

Before the first deploy, run:

```bash
COMPARTMENT_ID=<compartment-ocid> ./deploy/oci/ensure_apm.sh --apply
COMPARTMENT_ID=<compartment-ocid> \
AUTONOMOUS_DATABASE_ID=<atp-ocid> \
DRY_RUN=false \
./deploy/oci/ensure_stack_monitoring.sh
python3 tools/create_la_source.py \
    --la-namespace <la-namespace> \
    --la-log-group-id <la-log-group-ocid> --apply
./deploy/oci/ensure_monitoring.sh
```

The outputs (`apm_data_upload_endpoint`, `apm_public_datakey`,
`apm_private_datakey`, `rum_web_application_id`) are what populate the
`octo-apm` Kubernetes secret.

## Validate

```bash
curl -s https://drones.${DNS_DOMAIN}/ready | jq
curl -s https://admin.${DNS_DOMAIN}/ready  | jq
curl -s https://drones.${DNS_DOMAIN}/api/integrations/schema | jq .info.title
curl -s https://admin.${DNS_DOMAIN}/api/integrations/schema  | jq .info.title
```

When both `/ready` return `database.reachable=true` and both schema
endpoints return an OpenAPI doc advertising `InternalServiceKey` in
`components.securitySchemes`, the OKE deploy is fully operational.

For <OCI_PROFILE> before cutover, validate OKE directly with `kubectl
port-forward` and verify the dedicated OCI LB backend sets separately.
The live public LB should continue to serve the VM backend sets until the
routing policy is explicitly changed.

## Rollback

```bash
kubectl rollout undo deployment/octo-drone-shop       -n octo-drone-shop
kubectl rollout undo deployment/enterprise-crm-portal -n enterprise-crm
```

## Legacy

The previous OKE walkthrough (single-Deployment shop-only install) is
preserved in the commit history; its content is superseded by this
page and by `deploy/oke/README.md`.
