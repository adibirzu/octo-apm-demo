# bootstrap.sh + destroy.sh — end-to-end lifecycle

Two scripts that own the full provisioning + teardown flow so an
operator does not have to memorise the individual `deploy/deploy-*.sh`,
`oci ce cluster create-kubeconfig`, `terraform apply`, `kubectl apply`
sequence. Safe to rerun; safe on shared compartments.

## Bootstrap

```bash
# Fully non-interactive (every env pre-set):
OCI_PROFILE=DEFAULT \
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx \
DNS_BASE_DOMAIN=cyber-sec.ro \
REMOTE_BUILD_HOST=control-plane-oci \
./deploy/bootstrap.sh

# Interactive — pick compartment from a menu:
OCI_PROFILE=DEFAULT ./deploy/bootstrap.sh
```

The first run caches the choice in `deploy/.last-tenancy.env` (gitignored).
Subsequent runs reuse it unless you delete the cache.

### What it does, in order

| Step | What | Idempotent? | Opt-out |
|---|---|---|---|
| 0 | Validate OCI profile via Python SDK | yes | — |
| 1 | Compartment picker (TTY prompt if `OCI_COMPARTMENT_ID` unset) | yes | `OCI_COMPARTMENT_ID=…` |
| 2 | Detect OCIR namespace, create 3 tagged OCIR repos | yes (409 = skip) | — |
| 3 | Fetch kubeconfig, create `octo-<compartment>` context, create 2 namespaces | yes | `OKE_CLUSTER_ID=…` to override |
| 4 | `terraform apply -target=module.atp` (passwords auto-generated) | yes | omit — but then you must `ORACLE_DSN` manually |
| 5 | Extract wallet zip, seed 6 K8s secrets per namespace | yes (applied with `--dry-run=client` diff) | — |
| 6 | `deploy-{shop,crm}.sh --build-only` on remote builder | yes | `REMOTE_BUILD_HOST` |
| 7 | Apply shop + crm manifests via `envsubst` | yes | — |
| 8 | Detect virtual-node-only cluster (KB-459) — install nginx-ingress or exit with guidance | yes | `INSTALL_NGINX_INGRESS=false` |
| 9 | Create Ingress objects | yes | — |
| 10 | Wait for nginx LB IP, PATCH `<DNS_BASE_DOMAIN>` zone with A records | yes | — |
| 11 | Smoke-test `/` + `/ready` via Host: header | yes | — |

### Environment variables

| Var | Default | Purpose |
|---|---|---|
| `OCI_PROFILE` | `DEFAULT` | OCI CLI profile under `~/.oci/config`. |
| `OCI_COMPARTMENT_ID` | *(prompt)* | Target compartment. Interactive picker if unset + TTY. |
| `DNS_BASE_DOMAIN` | `cyber-sec.ro` | Zone under which `shop` + `crm` subdomains are created. Must already exist as a DNS zone OCI can PATCH. |
| `SHOP_SUBDOMAIN` / `CRM_SUBDOMAIN` | `shop` / `crm` | Subdomain leaves. |
| `K8S_NAMESPACE_SHOP` / `K8S_NAMESPACE_CRM` | `octo-drone-shop` / `enterprise-crm` | K8s namespaces. |
| `REMOTE_BUILD_HOST` | `control-plane-oci` | SSH host for x86_64 Docker builds. |
| `OKE_CLUSTER_ID` | *(first ACTIVE cluster in compartment)* | Skip cluster auto-detection. |
| `INSTALL_NGINX_INGRESS` | `true` | Opt-out of helm install. |
| `SKIP_APM_JAVA_DEMO` | `true` | Reserved. |
| `ATP_ADMIN_PW` / `ATP_WALLET_PW` | *(generated)* | Override if you want specific creds. |

### Known gotchas covered

- **Starlette signature** (KB-448): pre-flight template smoke test in `verify.sh`.
- **`packaging` transitive** (KB-449): Dockerfile uses `--ignore-installed`.
- **`.env.example` vs rsync glob** (KB-450): COPY dropped from Dockerfile.
- **Container name per service** (KB-451): `deploy-crm.sh` defaults `crm`, shop defaults `app`.
- **CRM `BOOTSTRAP_ADMIN_PASSWORD`** (KB-452): seeded in step 5 under `octo-auth`.
- **OKE disk pressure** (KB-453): OKE module defaults to 93 GiB boot volume.
- **`deploy-shop.sh` unbound var** (KB-454): fixed in the script.
- **LB `<pending>` behind ingress** (KB-455): Service is `ClusterIP`, ingress fronts.
- **OCI Monitoring write endpoint** (KB-456): app code uses `telemetry-ingestion.*`.
- **ATP DSN is a tns alias** (KB-457): script uses `${DB_NAME,,}_low`, not the full service_name.
- **Wallet zip must be extracted** (KB-458): script unzips then `--from-file`s every file.
- **OKE virtual-nodes + LoadBalancer** (KB-459): script detects, exits with guidance; nginx-ingress install is skipped.

## Destroy

```bash
./deploy/destroy.sh                      # interactive, prompts per step
./deploy/destroy.sh --yes                # no prompts
./deploy/destroy.sh --keep-atp           # leave the ATP alive
./deploy/destroy.sh --keep-images        # leave OCIR images in place
./deploy/destroy.sh --keep-atp --keep-images   # workloads only
```

### What it removes

1. K8s namespaces `${K8S_NAMESPACE_SHOP}` + `${K8S_NAMESPACE_CRM}` (deployments, services, ingresses, secrets, PDBs, HPAs).
2. nginx-ingress Helm release (only if installed by bootstrap).
3. DNS A records `shop.<DNS_BASE_DOMAIN>`, `crm.<DNS_BASE_DOMAIN>`.
4. ATP via `terraform destroy -target=module.atp`.
5. OCIR repos `octo-drone-shop`, `enterprise-crm-portal`, `octo-apm-java-demo`.
6. Local kubectl context + tenancy cache.

### What it NEVER touches

- The OKE cluster itself (pre-existing infrastructure).
- Any APM domain, Vault, Log Analytics namespace that predated bootstrap.
- Other namespaces / deployments in the cluster (coredns, anything unrelated).
- Network — VCN, subnets, security lists, route tables.
- OCIR repos in the compartment that weren't created by bootstrap.

### Safety tests run

Verified against oci4cca / Adrian_Birzu compartment:

| Test | Outcome |
|---|---|
| Dry-run (all `n` prompts) | All steps skipped, nothing removed |
| Workloads-only (`--keep-atp --keep-images`) | Shop+crm ns deleted, DNS records removed, ATP + OCIR + cluster + other apps untouched |
| Full destroy (`--yes`) | All the above + ATP terraform destroy + OCIR repos + local kubectl context |

Post-destroy `kubectl get ns` showed only: `default`, `kube-node-lease`, `kube-public`, `kube-system`. Post-destroy `kubectl get deploy -A` showed only `coredns` and `kube-dns-autoscaler`. Zero collateral damage.
