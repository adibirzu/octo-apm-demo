# OKE deployment — octo-apm-demo

Production path: two FastAPI services on an OKE cluster behind OCI
Load Balancers with WAF, sharing an Autonomous Database, fully wired
into APM + RUM + OCI Logging → Log Analytics + Stack Monitoring.

## Namespaces + hostnames

| Service | Namespace | Deployment | In-cluster URL | Public hostname |
|---|---|---|---|---|
| Drone Shop | `octo-shop-prod` | `octo-drone-shop` | `http://octo-drone-shop.octo-shop-prod.svc.cluster.local:8080` | `drone.${DNS_DOMAIN}` |
| Enterprise CRM | `octo-backend-prod` | `enterprise-crm-portal` | `http://enterprise-crm-portal.octo-backend-prod.svc.cluster.local:8080` | `backend.${DNS_DOMAIN}` |

Names deliberately differ from the unified-VM path so both deployments
can co-exist on the same tenancy (different compartments or clusters)
without collisions.

## One-shot apply

```bash
DNS_DOMAIN=octodemo.cloud \
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
OCI_LB_SUBNET_OCID=ocid1.subnet.oc1..xxx \
WAF_POLICY_SHOP_OCID=ocid1.webappfirewallpolicy.oc1..xxx \
WAF_POLICY_CRM_OCID=ocid1.webappfirewallpolicy.oc1..xxx \
IMAGE_TAG=latest \
./deploy/oke/deploy-oke.sh
```

The script applies namespaces, Deployments, LoadBalancer Services with
WAF annotations, HPA (2→6 replicas, 70% CPU / 75% memory), PDB
(`minAvailable: 1`), NetworkPolicies, and optionally a
SecretProviderClass per namespace when the OCI Secrets Store CSI
driver is installed.

Full walkthrough: [deploy/oke/README.md](https://github.com/adibirzu/octo-apm-demo/blob/main/deploy/oke/README.md).

## Security posture

| Control | Where |
|---|---|
| WAF (DETECTION → BLOCK) | OCI LB annotation `oci.oraclecloud.com/waf-policy-ocid` |
| TLS | OCI Certificates service attached to the LB, or cert-manager + LetsEncrypt |
| Cross-service auth | `X-Internal-Service-Key: $INTERNAL_SERVICE_KEY` on every cross-service POST |
| Idempotent order sync | `idempotency_token` (UUID5, stable per `(order_id, source)`) |
| Network segmentation | Per-namespace `NetworkPolicy` allowing only inter-namespace traffic + LB ingress |
| Secret handling | `SecretProviderClass` from OCI Vault via the Secrets Store CSI driver (optional; falls back to K8s Secrets) |
| Pod safety | Resource requests + limits, liveness + readiness probes on `/ready`, PDB, rolling updates with `maxUnavailable: 0` |

## Full observability — same as VM path, different Secrets

| Signal | Env var | Secret reference | Destination |
|---|---|---|---|
| Traces | `OCI_APM_ENDPOINT`, `OCI_APM_PRIVATE_DATAKEY` | `octo-apm:endpoint` + `private-key` | OCI APM Domain |
| RUM | `OCI_APM_RUM_ENDPOINT`, `OCI_APM_PUBLIC_DATAKEY`, `OCI_APM_WEB_APPLICATION` | `octo-apm:rum-endpoint` + `public-key` + `web-application` | OCI APM RUM |
| Logs | `OCI_LOG_ID`, `OCI_LOG_GROUP_ID` | `octo-logging:log-id` + `log-group-id` | OCI Logging → Service Connector → Log Analytics (source `octo-shop-app-json`) |
| Metrics | `OCI_COMPARTMENT_ID`, `OCI_MONITORING_NAMESPACE` | `octo-oci-config:compartment-id` | OCI Monitoring custom metrics + alarms |

**Correlation**: `oracleApmTraceId` is stamped onto every Logging record
the app emits via `oci.loggingingestion`. The Log Analytics parser
promotes it to a searchable column, so trace-to-log pivots work in
both directions: APM → Log Analytics search, Log Analytics → APM
trace explorer URL.

## Image build + push

The root-level `deploy/deploy-shop.sh` and `deploy/deploy-crm.sh` handle
build + push + rollout. Point them at the OKE namespaces:

```bash
# Drone Shop
OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-drone-shop \
K8S_NAMESPACE=octo-shop-prod \
K8S_DEPLOYMENT=octo-drone-shop \
./deploy/deploy-shop.sh

# Enterprise CRM
OCIR_REPO=${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/enterprise-crm-portal \
K8S_NAMESPACE=octo-backend-prod \
K8S_DEPLOYMENT=enterprise-crm-portal \
./deploy/deploy-crm.sh
```

Both scripts build on a remote x86_64 host (ARM laptops cannot cross-
build with QEMU reliably), push to OCIR, and `kubectl set image` the
appropriate Deployment.

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
curl -s https://drone.${DNS_DOMAIN}/ready   | jq
curl -s https://backend.${DNS_DOMAIN}/ready | jq
curl -s https://drone.${DNS_DOMAIN}/api/integrations/schema   | jq .info.title
curl -s https://backend.${DNS_DOMAIN}/api/integrations/schema | jq .info.title
```

When both `/ready` return `database.reachable=true` and both schema
endpoints return an OpenAPI doc advertising `InternalServiceKey` in
`components.securitySchemes`, the OKE deploy is fully operational.

## Rollback

```bash
kubectl rollout undo deployment/octo-drone-shop       -n octo-shop-prod
kubectl rollout undo deployment/enterprise-crm-portal -n octo-backend-prod
```

## Legacy

The previous OKE walkthrough (single-Deployment shop-only install) is
preserved in the commit history; its content is superseded by this
page and by `deploy/oke/README.md`.
