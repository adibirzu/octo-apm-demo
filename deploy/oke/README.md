# OKE deployment — octo-apm-demo

Production path: two FastAPI services on an OKE cluster behind OCI
Load Balancers with WAF, sharing an Autonomous Database, fully wired
into APM + RUM + OCI Logging → Log Analytics + Stack Monitoring.

## Names used by this path

| Concern | Value |
|---|---|
| Shop namespace | `octo-drone-shop` |
| CRM namespace | `enterprise-crm` |
| Shop Deployment | `octo-drone-shop` |
| CRM Deployment | `enterprise-crm-portal` |
| Shop in-cluster URL | `http://octo-drone-shop.octo-drone-shop.svc.cluster.local:8080` |
| CRM in-cluster URL | `http://enterprise-crm-portal.enterprise-crm.svc.cluster.local:8080` |
| Shop public hostname | `shop.${DNS_DOMAIN}` (for `DEFAULT` / `oci4cca`, use `shop.cyber-sec.ro`) |
| CRM public hostname | `crm.${DNS_DOMAIN}` (for `DEFAULT` / `oci4cca`, use `crm.cyber-sec.ro`) |

Deliberately different from the unified-VM names so both deployments
can co-exist on the same tenancy (different compartments / clusters)
without collisions.

## One-shot apply

```bash
DNS_DOMAIN=cyber-sec.ro \
OCIR_REGION=eu-frankfurt-1 \
OCIR_TENANCY=<namespace> \
OCI_LB_SUBNET_OCID=ocid1.subnet.oc1..xxx \
WAF_POLICY_SHOP_OCID=ocid1.webappfirewallpolicy.oc1..xxx \
WAF_POLICY_CRM_OCID=ocid1.webappfirewallpolicy.oc1..xxx \
IMAGE_TAG=latest \
./deploy/oke/deploy-oke.sh
```

The script:

1. Applies namespaces + labels.
2. Checks that each namespace has the expected bootstrap Secrets
   (`octo-auth`, `octo-atp`, `octo-atp-wallet`, `octo-oci-config`) —
   warns, does not error, so you can create them with
   `deploy/init-tenancy.sh` or a SecretProviderClass.
3. If the OCI Secrets Store CSI driver CRD is installed, applies a
   per-namespace `SecretProviderClass` that pulls every secret from
   OCI Vault. Otherwise continues with plain Kubernetes Secrets.
4. envsubsts + applies the Deployment/Service/LB/HPA/PDB for each
   service.
5. Applies the NetworkPolicies last so pod→pod traffic across
   namespaces works immediately.
6. Waits for rollouts, prints the LB public IPs for DNS setup.

## What it publishes

Each service gets two Kubernetes Services:

| Service | Type | Purpose |
|---|---|---|
| `octo-drone-shop` | ClusterIP | in-cluster callbacks (used by CRM) |
| `octo-drone-shop-lb` | LoadBalancer | public shop traffic (shop.${DNS_DOMAIN}) |
| `enterprise-crm-portal` | ClusterIP | in-cluster callbacks (used by Shop) |
| `enterprise-crm-portal-lb` | LoadBalancer | public CRM traffic (crm.${DNS_DOMAIN}) |

The public LBs are annotated with:

- `service.beta.kubernetes.io/oci-load-balancer-shape: flexible` +
  `shape-flex-min: 10` + `shape-flex-max: 100` (auto-scales bandwidth).
- `oci-load-balancer-subnet1` — uses the subnet you pass in.
- `oci.oraclecloud.com/waf-policy-ocid` — attaches the WAF policy
  created by `deploy/terraform/modules/waf/` (shop + crm get
  different policies so admin-path allowlisting applies only on CRM).

## Scaling

Both Deployments have HPA from **2 to 6 replicas** driven by 70% CPU
and 75% memory averages. Adjust `minReplicas` / `maxReplicas` for
production load. PodDisruptionBudget pins `minAvailable: 1` so node
drains during upgrades never kill every pod at once.

## Observability wiring (same as VM path — just different Secrets)

Every observability env var is read from a named Kubernetes Secret so
the OKE Deployment can be rolled independently of secret rotation:

| Env var | Secret:key |
|---|---|
| `OCI_APM_ENDPOINT` | `octo-apm:endpoint` |
| `OCI_APM_PRIVATE_DATAKEY` | `octo-apm:private-key` |
| `OCI_APM_PUBLIC_DATAKEY` | `octo-apm:public-key` |
| `OCI_APM_RUM_ENDPOINT` | `octo-apm:rum-endpoint` |
| `OCI_APM_WEB_APPLICATION` | `octo-apm:web-application` |
| `OCI_LOG_ID` | `octo-logging:log-id` |
| `OCI_LOG_GROUP_ID` | `octo-logging:log-group-id` |
| `OCI_COMPARTMENT_ID` | `octo-oci-config:compartment-id` |
| `OCI_GENAI_ENDPOINT` | `octo-oci-config:genai-endpoint` |
| `IDCS_CLIENT_SECRET` | `octo-sso:idcs-client-secret` |

`oracleApmTraceId` correlation is automatic: the app's OTel exporter
stamps the active trace id onto every OCI Logging record it emits
(via the `oci.loggingingestion` SDK), and the `octo-shop-app-json` Log
Analytics parser extracts it as a searchable field.

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

The root-level `deploy/deploy-shop.sh` and `deploy/deploy-crm.sh`
handle build + push + rollout. Point them at the OKE namespaces:

```bash
OCIR_REGION=${OCIR_REGION} \
OCIR_TENANCY=${OCIR_TENANCY} \
DNS_DOMAIN=${DNS_DOMAIN} \
./deploy/deploy.sh
```

Both scripts build on a remote x86_64 host (ARM laptops cannot cross-
build with QEMU reliably), push to OCIR, and `kubectl set image` the
appropriate Deployment.

## Rollback

```bash
kubectl rollout undo deployment/octo-drone-shop       -n octo-drone-shop
kubectl rollout undo deployment/enterprise-crm-portal -n enterprise-crm
```

## DNS + TLS

The LBs come up with public IPs; point DNS:

```
shop.${DNS_DOMAIN}    A    <shop LB IP>
crm.${DNS_DOMAIN}     A    <crm LB IP>
```

TLS options:

- **OCI Certificates service** (recommended) — create a certificate
  per hostname, reference on the LB via Terraform or the Console.
- **cert-manager + LetsEncrypt** — install cert-manager in the cluster,
  add an HTTP01 ClusterIssuer, deploy Ingress objects per hostname.

The manifests ship LB services with HTTP + HTTPS ports so the LB can
terminate TLS once certificates are attached.
