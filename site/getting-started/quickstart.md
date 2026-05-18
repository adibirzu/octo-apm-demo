---
title: Quickstart
description: Deploy the OCTO APM Demo platform into any OCI tenancy in 5-10 minutes.
---

# Quickstart — Deploy in any OCI tenancy

This guide gets the OCTO APM Demo running in **your** OCI tenancy. Three
deployment paths, all starting from `make doctor`:

- **Path A: One-click** (Resource Manager stack zip) — fastest, no local
  tooling needed
- **Path B: Make** (recommended for evaluators) — `make tenancy-init &&
  make deploy && make smoke`
- **Path C: Local stack** (no OCI) — `make local-up`, browse to
  `http://localhost:18080`

---

## Prerequisites — common to all paths

| Requirement | How to check | Notes |
|---|---|---|
| OCI tenancy | `oci iam region list` | Free Tier works |
| Access to a target compartment | `oci iam compartment list` | A clean compartment is recommended |
| OCI policy: APM, Logging, Log Analytics, Monitoring, ATP read+write | `oci iam policy list` | Sample policy in `deploy/oci/policies/` |
| `oci` CLI 3.40+ | `oci --version` | `pip install oci-cli` |
| `jq`, `curl`, `bash` 5+ | `which jq curl bash` | Standard tooling |

For Paths B/C you also need:

- `docker` or `colima` (for `make local-up` and building images)
- `kubectl` (for OKE deploys)
- `helm` (optional, for `make deploy-helm`)
- `terraform` 1.5+ (for IaC paths)

Quick environment check:

```bash
make doctor
```

---

## Path A — One-click (Resource Manager stack)

Best for evaluators who want to see the platform running in 5 minutes
without local tooling.

1. Click the **Deploy to Oracle Cloud** badge:

   [![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/adibirzu/octo-apm-demo/releases/download/compute-resource-manager-stack-20260517/octo-compute-stack.zip)
2. OCI Console opens at **Resource Manager → Create stack**, with the
   zip URL pre-filled.
3. Fill the stack variables:
   - **Compartment** — target compartment
   - **DNS domain** — your public DNS zone (e.g. `demo.acme.io`)
   - **Resource prefix** — short prefix for all resources (default `octo`)
4. Click **Plan → Apply**. Provisioning takes 25-40 minutes.
5. Once apply completes, point your DNS A records:
   ```
   drones.<your-dns>     A    <LB-IP from stack output>
   admin.<your-dns>      A    <LB-IP from stack output>
   ```
6. Wait for DNS propagation (~5 min), then validate:
   ```bash
   DNS_DOMAIN=<your-dns> ./deploy/validate-deployment.sh
   ```

The stack provisions: VCN, OKE cluster, ATP, OCI APM domain, RUM Web
Application, Log Analytics, Monitoring, Stack Monitoring, WAF policies,
Load Balancers, OCIR repositories.

---

## Path B — Make (recommended for hands-on operators)

Best for engineers who want to inspect and customize the deployment.

### 1. Configure your environment

Create `.env` in the repo root (or export the variables):

```bash
cat > .env <<EOF
OCI_PROFILE=DEFAULT
OCI_COMPARTMENT_ID=<COMPARTMENT_OCID>
OCIR_REGION=<OCIR_REGION>
OCIR_TENANCY=<OCIR_TENANCY>
DNS_DOMAIN=<your-dns-zone>
EOF
```

### 2. Run preflight

```bash
make doctor
```

Should report ✓ on `oci`, `kubectl`, `docker`, `jq`, and a successful OCI
profile auth. Fix anything ✗ before continuing.

### 3. Bootstrap the tenancy

```bash
make tenancy-init
```

This creates: OCIR repositories, Kubernetes namespaces, bootstrap secrets
(internal-service-key, apm-tokens placeholder, logging-config
placeholder). Idempotent — re-runs are safe.

### 4. Deploy

```bash
make deploy
```

Builds shop + crm + Java sidecar images (~5 min on a remote x86_64
builder, longer with local QEMU), pushes them to OCIR, applies the
Kubernetes manifests, waits for rollout, prints the public LB IPs.

For per-service deploys:

```bash
make deploy-shop
make deploy-crm
make deploy-java-apm
```

For the Helm chart instead of raw manifests:

```bash
make deploy-helm
```

### 5. Point DNS

The deploy output prints the LB IPs. Create A records:

```
drones.${DNS_DOMAIN}    A    <shop LB IP>
admin.${DNS_DOMAIN}     A    <crm LB IP>
```

### 6. Smoke-check

```bash
make smoke
```

Probes every observable surface (storefront HTML, `/ready` JSON fields
for APM/RUM/Logging/Workflow Gateway/Select AI/GenAI/Java sidecar,
admin reachability). All checks should print green ✓ within 60 seconds
of DNS propagation.

### 7. Open the storefront

```
https://drones.${DNS_DOMAIN}
https://admin.${DNS_DOMAIN}
```

You're done. Continue with the [workshop labs](../workshop/index.md)
to learn what each observability surface captures.

---

## Path C — Local stack (no OCI)

Best for first-time evaluators and developers extending the codebase.

```bash
make local-up
```

The docker-compose stack brings up shop, crm, Java sidecar, redis,
postgres. After ~30 seconds:

```
http://localhost:18080   # shop
http://localhost:18090   # crm
http://localhost:18091   # java sidecar /actuator
```

Local stack uses postgres (not ATP) and emits OTel telemetry to a
console exporter (not OCI APM). Most workshop labs are **OCI-dependent**
and won't work locally — but the storefront UX, code paths, and
contract tests all run.

Tear down:

```bash
make local-down
```

---

## Troubleshooting

??? warning "make doctor reports OCI auth failure"
    Check that your OCI config has the named profile and that the API
    signing key is uploaded to that user. The standard fix:

    ```bash
    oci setup config
    oci iam region list   # should print regions
    ```

??? warning "make deploy hangs at image build"
    Image builds happen on a remote x86_64 builder by default (set
    `BUILD_HOST=<ssh-target>` to use yours). Without a builder, Docker
    falls back to QEMU on ARM Macs which is slow but works. Set
    `BUILD_LOCALLY=1` if you have x86_64 Docker locally.

??? warning "smoke reports APM/RUM/Logging 'false'"
    The shop pods are running but missing OCI env vars. Check the
    secrets:

    ```bash
    kubectl get secret octo-apm -n octo-drone-shop -o yaml
    kubectl get secret octo-logging -n octo-drone-shop -o yaml
    ```

    See `docs/CONFIGURATION.md` in the repo for the full env var list for the full env var list.

??? warning "Load Balancer IP not visible in 'make deploy' output"
    OCI LB provisioning takes ~3-5 minutes. Poll:

    ```bash
    kubectl get svc -n octo-drone-shop -w
    ```

    Look for the EXTERNAL-IP column to populate.

---

## After deployment — recommended next steps

1. **Run the workshop** — start at [Workshop / Lab 01](../workshop/lab-01-first-trace.md).
2. **Apply Log Analytics saved searches** — `bash tools/la-saved-searches/apply.sh`
3. **Enable the traffic generator** — `kubectl apply -f tools/traffic-generator/k8s/` so APM and RUM have continuous signal.
4. **Review the architecture map** — [ARCHITECTURE.md](../architecture/platform-overview.md) explains every service and observability surface in detail.
5. **Tear down when done** — `make destroy` (asks for confirmation).
