# OCTO APM Demo — Unified Platform

Unified repository for the OCTO Drone Shop + Enterprise CRM Portal
platform: one `deploy/` tree, one Bill of Materials, one Resource
Manager stack, one unified-VM path. The two services live side-by-side
as independent containers under `shop/` and `crm/` so they keep the
cross-service contract hardened in the upstream repos.

**Docs site**: https://adibirzu.github.io/octo-apm-demo
**Target hostnames (`DEFAULT` / `<OCI_PROFILE>`)**: `shop.example.test` (Shop) · `crm.example.test` (CRM)
**Status (April 25, 2026)**: the tracked `DEFAULT` deployment is currently degraded. Public DNS for `shop.example.test` and `crm.example.test` returns no `A` record, the shared ingress load balancer still exists but the ingress controller is `0/2` because the managed node pool is `NotReady`, both app deployments are `0/2`, and ATP `octo-apm-demo-atp` is `STOPPED`. Use `deploy/bootstrap.sh` for fresh tenancies, and check [`site/operations/current-status.md`](site/operations/current-status.md) before treating the shared `DEFAULT` environment as E2E-ready.

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/adibirzu/octo-apm-demo/releases/download/resource-manager-stack/octo-stack.zip)

## Repository layout

```
octo-apm-demo/
├── README.md · ARCHITECTURE.md · LICENSE
├── shop/              # octo-drone-shop (imported via git subtree, full history preserved)
│   └── server/ · Dockerfile · tests/ · k6/ · ...
├── crm/               # enterprise-crm-portal (imported via git subtree, full history preserved)
│   └── server/ · Dockerfile · tests/ · ...
├── deploy/            # unified deployment surface
│   ├── BOM.md                        # Bill of Materials (authoritative)
│   ├── pre-flight-check.sh           # env + tooling validator
│   ├── init-tenancy.sh               # idempotent new-tenancy bootstrap
│   ├── deploy.sh                     # unified shop + crm build/push/rollout wrapper
│   ├── deploy-shop.sh                # build + push + rollout for Shop
│   ├── deploy-crm.sh                 # build + push + rollout for CRM
│   ├── resource-manager/             # OCI Resource Manager stack (one-click)
│   ├── vm/                           # Unified single-VM compose + cloud-init
│   ├── k8s/                          # OKE manifests (envsubst-templated)
│   │   ├── shop/
│   │   └── crm/
│   ├── helm/octo-apm-demo/           # Helm chart — drop-in onto an existing OKE cluster
│   ├── bootstrap.sh                  # End-to-end tenancy lifecycle (ATP + secrets + build + ingress + DNS + TLS)
│   ├── destroy.sh                    # Targeted teardown — never touches the OKE cluster itself
│   ├── terraform/modules/            # apm_domain, waf, log_pipeline, iam, api_gateway,
│   │                                 # atp, vault, object_storage, logging, stack_monitoring
│   ├── local-stack/                  # hermetic docker-compose for regression (postgres + redis)
│   ├── OBSERVABILITY-BOOTSTRAP.md    # end-to-end recipe: tf → init-tenancy → deploy → verify
│   └── oci/                          # ensure_apm.sh, ensure_stack_monitoring.sh, ...
├── services/          # supporting pods (otel-gateway, async-worker, cache, remediator,
│                      # load-control, browser-runner, edge-gateway, object-pipeline, vm-lab)
├── site/              # MkDocs (deployed to github.io)
│   └── architecture/diagrams/        # .drawio sources (platform-overview, observability-flow, deploy-topology)
└── mkdocs.yml
```

## Four deployment paths — same container images

| Path | Entry point | When to use |
|---|---|---|
| **OKE** | `deploy/k8s/oke/{shop,crm}/*.yaml` + `deploy/deploy-{shop,crm}.sh` | Production, HA, rolling updates. First-time rollout auto-runs `envsubst` on manifests. |
| **OKE (Helm, existing cluster)** | `deploy/helm/octo-apm-demo/` | Drop-in for operators who already have OKE + secrets. `helm upgrade --install`, `helm rollback`, one release owns both apps. See [`deploy/helm/octo-apm-demo/README.md`](deploy/helm/octo-apm-demo/README.md). |
| **Bootstrap (unified)** | `deploy/bootstrap.sh` + `deploy/destroy.sh` | End-to-end lifecycle: compartment picker → OCIR → kubeconfig → ATP terraform → seed secrets → build+push → apply manifests → ingress + DNS + TLS + smoke test. See [`deploy/BOOTSTRAP-README.md`](deploy/BOOTSTRAP-README.md). |
| **OCI Resource Manager stack** | `deploy/resource-manager/` | Console one-click bootstrap of APM + RUM + LA + WAF. Use the Deploy to Oracle Cloud button above. |
| **Unified single VM** | `deploy/vm/docker-compose-unified.yml` | Demos, workshops, air-gapped — both services on one Compute instance |
| **local-stack** | `deploy/local-stack/docker-compose.test.yml` | Hermetic regression — Playwright + k6 + CI without OCI credentials. NOT for prod. |

Full matrix: [site/getting-started/deployment-options.md](site/getting-started/deployment-options.md). Observability wiring for a fresh tenancy: [deploy/OBSERVABILITY-BOOTSTRAP.md](deploy/OBSERVABILITY-BOOTSTRAP.md).

## Cross-service integration contract

Both services publish the same contract at `GET /api/integrations/schema`.

| Concern | Value |
|---|---|
| Canonical shop URL env | `SERVICE_SHOP_URL` (legacy aliases: `OCTO_DRONE_SHOP_URL`, `MUSHOP_CLOUDNATIVE_URL`) |
| Canonical CRM URL env | `SERVICE_CRM_URL` (legacy alias: `ENTERPRISE_CRM_URL`) |
| Shared auth header | `X-Internal-Service-Key: $INTERNAL_SERVICE_KEY` |
| Idempotency fields on order POST | `source_system`, `source_order_id`, `idempotency_token` (UUID5) |

## Deployment Bill of Materials

Full list of required resources, secrets, CLIs, and images in
**[deploy/BOM.md](deploy/BOM.md)**. `pre-flight-check.sh`,
`init-tenancy.sh`, and the Resource Manager schema all validate against
it.

## Quick start — single VM (fastest path)

```bash
# 1. SSH onto a fresh OCI Compute VM (Oracle Linux 9 / Ubuntu 24.04)
sudo dnf install -y git curl unzip                  # or apt-get

# 2. Clone + configure
git clone https://github.com/adibirzu/octo-apm-demo.git /opt/octo
cd /opt/octo/deploy/vm
cp .env.template .env
${EDITOR:-vi} .env                                   # set DNS_DOMAIN=example.tld, OCIR, ATP, keys

# 3. Unzip the ATP wallet
unzip /path/to/Wallet_<DB>.zip -d wallet

# 4. TLS certs (bundled domains: shop.$DNS + crm.$DNS)
sudo certbot certonly --standalone \
  -d shop.${DNS_DOMAIN} -d crm.${DNS_DOMAIN}
sudo cp /etc/letsencrypt/live/shop.${DNS_DOMAIN}/*.pem   nginx/tls/shop/
sudo cp /etc/letsencrypt/live/crm.${DNS_DOMAIN}/*.pem nginx/tls/crm/

# 5. Launch
sudo ./install.sh
```

Validate:

```bash
curl -s https://shop.${DNS_DOMAIN}/ready   | jq
curl -s https://crm.${DNS_DOMAIN}/ready | jq
curl -s https://shop.${DNS_DOMAIN}/api/integrations/schema   | jq .info.title
curl -s https://crm.${DNS_DOMAIN}/api/integrations/schema | jq .info.title
```

Both `/ready` must show `database.reachable=true`; both `/api/integrations/schema`
must return an OpenAPI doc with `InternalServiceKey` in
`components.securitySchemes`.

## Subtree sources

| Path | Source repo | Subtree command |
|---|---|---|
| `shop/` | `github.com/adibirzu/octo-drone-shop` | `git subtree pull --prefix=shop https://github.com/adibirzu/octo-drone-shop.git main` |
| `crm/`  | `github.com/adibirzu/enterprise-crm-portal` | `git subtree pull --prefix=crm  https://github.com/adibirzu/enterprise-crm-portal.git main` |

Either subtree can be pulled to grab upstream fixes without disturbing
the other service. The upstream repos remain the per-service source of
truth for app-layer changes; this repo owns the unified deploy + docs
surface.

## License

MIT — see [LICENSE](LICENSE).
