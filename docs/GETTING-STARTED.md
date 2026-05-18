---
title: Getting Started
---

# Getting Started with octo-apm-demo

This guide walks a new evaluator from a freshly cloned repository to a running stack that emits real OCI Observability telemetry. Each step explains the **why** before the **how**, so you can deviate when your tenancy looks different.

If you only want to skim the moving parts of the system, start with [ARCHITECTURE.md](ARCHITECTURE.md). If you just need a list of knobs, jump to [CONFIGURATION.md](CONFIGURATION.md). Otherwise, work through this guide top-to-bottom.

---

## A. What you'll have after this guide

By the end of section G you will have a working demo platform that produces every signal the workshop labs depend on:

- **Drone Shop** (FastAPI storefront) and **Enterprise CRM Portal** (FastAPI admin/support console) running and reachable.
- **Java payment-gateway simulator** participating in checkout spans so Apple Pay / Google Pay / Visa / Mastercard rails are visible in APM.
- **OCI APM traces** for every HTTP request, with W3C-compatible trace context propagated between shop, CRM, and the Java service.
- **Real User Monitoring (RUM)** on the shop's browser surface, with trace IDs propagated so a click in the browser links to a backend span.
- **OCI Logging → Log Analytics** custom logs for application SDK logs, container stdout, and host telemetry.
- **Custom business metrics** (orders, payments, fraud signals) posted to OCI Monitoring under your namespace.
- **Attack-lab and chaos simulation** endpoints wired so you can drive the workshop labs end-to-end.

You do not need everything from day one. Section E (local stack) gets you a working app loop without touching OCI. Sections F–G add real observability.

---

## B. Prerequisites

### OCI tenancy

You need an OCI tenancy with the following services enabled and a compartment you can create resources in. For the local stack (section E) you can skip this entirely.

| Service | Why it matters |
|---|---|
| **APM Domain** | Endpoint + private/public keys for OTLP/Zipkin trace export, plus a RUM web application record. |
| **Log Analytics namespace** | Destination for parsed log entries via Service Connector Hub. |
| **Monitoring** | Custom metric posting target (`postMetricData`). |
| **Logging service** | Custom log groups + logs that hold application SDK output, container stdout, and audit streams. |
| **Autonomous Database (ATP)** | Primary data store. Wallet-based mTLS connectivity. |
| **OCI Registry (OCIR)** | Container images for shop, crm, java-apm-demo, workflow-gateway. |
| **Resource Manager** *(optional)* | If you take the Compute path in section F, the Resource Manager stack provisions everything end-to-end. |

### Permissions / policies

You need either **instance principals** (recommended for any VM/OKE deploy) or a config-file user with rights to:

- `manage apm-domains`, `manage apm-traces`, `read apm-traces` in the target compartment
- `manage log-analytics-resources-family` (or read-only if you use Service Connector for ingest)
- `manage logging-family`
- `use metrics`, `read metrics` for the custom metric namespace
- `manage autonomous-database-family` (only at provision time; runtime needs just `read`)
- `read repos`, `manage repos` on OCIR
- `manage stack-monitoring-resources-family` if you want Stack Monitoring host registration

Encode these as a dynamic group + matching policies for instance principals, or as a single user-level policy bundle for config-file auth.

### Local tools

| Tool | Used by |
|---|---|
| **Python 3.11+** | Running shop/crm tests, generating images, executing helper scripts. |
| **Docker or Podman** | All deployment substrates; `docker compose` is used by the local stack. |
| **kubectl** | OKE deployments (sections F option 3). |
| **Helm 3** | Optional, for the chart-based OKE install. |
| **Terraform** | Compute / Resource Manager IaC path. |
| **Java 17 (JDK)** | Only required if you build the Java payment-gateway sidecar locally; otherwise pull from OCIR. |
| **Node 20 + npm** | Frontend assets, Playwright tests. |
| **GitHub account** | To fork or clone the repository, and to author pull requests. |

---

## C. Clone and explore

```bash
git clone https://github.com/<github-username>/octo-apm-demo.git
cd octo-apm-demo
```

A quick walk through what lives where:

| Path | What it holds |
|---|---|
| `shop/` | FastAPI storefront, Playwright + k6 suites, Alembic migrations. |
| `crm/` | FastAPI CRM portal, admin coordinator, observability dashboards. |
| `services/` | Sidecar services: `apm-java-demo`, `async-worker`, `auto-remediator`, `otel-gateway`, `remediator`, attack-lab containers. |
| `deploy/` | Every deployment substrate (`local-stack/`, `vm/`, `oke/`, `k8s/`, `helm/`, `compute/`, `terraform/`, `resource-manager/`). |
| `site/` | The MkDocs documentation site, including the 10-lab workshop under `site/workshop/`. |
| `tests/` | Cross-service integration tests. |
| `tools/` | One-off operational scripts (image builds, OCI bootstrap, doc generation). |

Open `site/index.md` to preview the docs locally:

```bash
pip install -r requirements-docs.txt
mkdocs serve
# open http://127.0.0.1:8000
```

---

## D. Pick a deployment substrate

The project ships five paths. Pick one based on what you want to evaluate and how much OCI surface you want to manage.

| Substrate | When to use | Path |
|---|---|---|
| **Local stack** (docker-compose, Postgres stand-in) | Quick eval, regression testing, no OCI tenancy needed | `deploy/local-stack/` |
| **VM** (single host, Podman/Docker behind nginx) | Single-host OCI demo, air-gapped reproducer, workshops | `deploy/vm/` |
| **OKE — raw manifests** | Production-shaped Kubernetes with full control over YAML | `deploy/k8s/oke/` |
| **OKE — Helm chart** | Same as above, with values-file overrides and lifecycle commands | `deploy/helm/octo-apm-demo/` |
| **Compute via Resource Manager** | OCI-native IaC, multi-instance with private LB + WAF + Stack Monitoring | `deploy/compute/` |

If you have never run the project before, do section E first to confirm the apps work, then come back to F.

---

## E. Quickstart — local stack (no OCI needed)

The local stack runs shop + crm + the Java payment simulator + Redis + Postgres in a hermetic docker-compose. It exists so you can prove the application logic works before involving OCI.

### 1. Start

```bash
cd deploy/local-stack
docker compose -f docker-compose.test.yml up --build
```

First build is 2–3 minutes. Subsequent runs reuse cached layers.

### 2. Verify

| Component | URL |
|---|---|
| Drone Shop | http://localhost:18080 |
| CRM Portal | http://localhost:18090 |
| Java payment gateway | http://localhost:18091 |
| Redis | `localhost:16379` |
| Postgres | `localhost:15432` (user `octo`, db `octo`) |

Browse to the shop, register a user, add a drone to the cart, complete checkout. The Java payment gateway should respond and the CRM should show the order when an admin signs in.

### 3. What works locally vs not

**Works:** functional flows (signup → browse → cart → checkout → admin views order), Playwright + k6 regression, the simulated payment rails, the local trace/log correlation seen in container stdout.

**Does not work:** real OCI APM trace export, RUM ingest, Log Analytics, Monitoring custom metrics, IDCS SSO, Select AI / Workflow Gateway (it requires an ATP wallet). The local stack uses Postgres rather than ATP, so any PL/SQL or JSON Relational Duality View paths are stubbed or skipped.

### 4. Teardown

```bash
docker compose -f docker-compose.test.yml down -v
```

Drop the `-v` flag to preserve the pg-data volume between runs.

---

## F. First OCI deployment — minimum viable

The fastest OCI path is the **VM substrate** in `deploy/vm/`. It runs the full stack on one Compute instance, talks to a real ATP, and exports real telemetry to APM + Logging + Monitoring. From there you can graduate to OKE or the multi-instance Compute path without re-learning the env contract.

### 1. Provision the OCI primitives

You need (in your target compartment):

- A Compute VM. `VM.Standard.E5.Flex` with 2 OCPU / 16 GB is enough.
- An Autonomous Database (ATP) — download its wallet zip from **OCI Console → Autonomous Database → DB Connection → Download Wallet**.
- An APM Domain — note its data upload endpoint, public key, and private key.
- A RUM Web Application — note its OCID.
- A Log Group + Custom Logs for `app-sdk`, `chaos-audit`, and `security`.
- An OCIR repository populated with images for `shop`, `crm`, `octo-apm-java-demo`, and `octo-workflow-gateway` (build locally with `tools/build-and-push.sh` or pull pre-built tags if your tenancy mirrors them).

If you would rather have all of this provisioned in one click, use the Resource Manager stack under `deploy/compute/` — it creates the VM, ATP, Load Balancer, WAF, APM domain, log groups, and Service Connector pipelines in a single apply. See `site/getting-started/compute-deployment.md` for the walkthrough.

### 2. Configure environment

Read [CONFIGURATION.md](CONFIGURATION.md) for the full env var contract. The short version, copied onto the VM:

```bash
sudo dnf install -y git curl unzip   # or apt-get install ...
git clone https://github.com/<github-username>/octo-apm-demo.git /opt/octo
cd /opt/octo/deploy/vm

cp .env.template .env
${EDITOR:-vi} .env
```

The fields that **must** be filled before launch:

- `OCIR_REGION`, `OCIR_TENANCY`, and image tags — so Podman knows where to pull from.
- `DNS_DOMAIN` and `SHOP_PUBLIC_URL` — so cookies, CORS, and absolute URLs work.
- `INTERNAL_SERVICE_KEY`, `AUTH_TOKEN_SECRET`, `APP_SECRET_KEY`, `BOOTSTRAP_ADMIN_PASSWORD` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` and **reuse the same values on shop and crm sides**.
- `ORACLE_DSN`, `ORACLE_USER`, `ORACLE_PASSWORD`, plus the wallet zip unpacked into `deploy/vm/wallet/`.
- APM keys + endpoint, RUM OCID, log OCIDs, and `OCI_COMPARTMENT_ID`.

### 3. Place TLS certs and the wallet

```bash
# Wallet
unzip /path/to/Wallet_<DB>.zip -d wallet

# TLS for shop.${DNS_DOMAIN} and crm.${DNS_DOMAIN}
sudo certbot certonly --standalone \
    -d shop.${DNS_DOMAIN} -d crm.${DNS_DOMAIN}
sudo cp /etc/letsencrypt/live/shop.${DNS_DOMAIN}/*.pem nginx/tls/shop/
sudo cp /etc/letsencrypt/live/crm.${DNS_DOMAIN}/*.pem  nginx/tls/crm/
```

### 4. Launch

```bash
sudo ./install.sh
```

The script logs into OCIR, pulls the four images, renders the compose file with your env values, and starts everything behind nginx.

### 5. Verify health

```bash
curl -s https://shop.${DNS_DOMAIN}/ready | jq
curl -s https://crm.${DNS_DOMAIN}/ready  | jq
```

Both should report `status: ready` with `db: ok` and `cache: ok`. If `apm: ok` is false, your APM keys or endpoint are wrong — re-check `.env` and restart the affected container.

### Alternative: OKE

If you already have an OKE cluster and OCIR images, the equivalent one-shot is:

```bash
DNS_DOMAIN=example.test \
OCIR_REGION=<OCIR_REGION> \
OCIR_TENANCY=<OCIR_TENANCY> \
IMAGE_TAG=<immutable-image-tag> \
./deploy/oke/deploy-oke.sh
```

That script applies namespaces, validates bootstrap Secrets exist, optionally wires the OCI Secrets Store CSI driver, applies Java payment-gateway + Workflow Gateway + Shop + CRM Deployments, applies NetworkPolicies, and waits for rollouts. The Helm chart equivalent lives under `deploy/helm/octo-apm-demo/` — see its README for the full values reference.

---

## G. Your first trace

The point of the demo is the observability story. Let's produce one trace and follow it from browser to database.

### 1. Drive traffic

In an incognito window:

1. Open `https://shop.${DNS_DOMAIN}`.
2. Register a new shopper.
3. Add at least one drone to the cart.
4. Complete checkout with the simulated card form.

This sequence exercises shop → java-apm-demo → ATP, and emits one RUM session plus several backend spans.

### 2. Find the trace in APM

In the OCI Console: **Observability & Management → Application Performance Monitoring → Trace Explorer**.

- Set the APM domain to the one you provisioned.
- Filter by **Service Name** = `octo-drone-shop`.
- Set the time window to the last 15 minutes.

You should see a trace with at least these spans:

- `POST /api/checkout` (root span, on `octo-drone-shop`)
- a child span on `octo-apm-java-demo` for the simulated payment
- one or more SQL spans on the ATP connection

### 3. Pivot from span to log

Pick the root span and copy its `traceId`. Then in **Observability & Management → Logging Analytics → Log Explorer**:

```
* | where 'oracleApmTraceId' = '<paste-trace-id>'
```

You should see correlated entries from the shop application log, the Java service log, and the audit log if checkout triggered an admin notification. This is the bidirectional link that powers the workshop's trace–log correlation lab.

### 4. Confirm RUM

In **Application Performance Monitoring → Real User Monitoring → Sessions**, find the session matching the time of your checkout. Open it — the session timeline should show the page view, the checkout XHR, and a `Show Trace` action that opens the matching APM trace in a new tab.

If any of these three signals is missing, the most common causes are: wrong APM data-upload endpoint, the RUM injection snippet pointing at a different web-application OCID, or the Service Connector to Log Analytics being paused.

---

## H. Where to go next

You now have a working baseline. From here the project is meant to be explored in three directions:

1. **Workshop labs** — `site/workshop/` contains 10 labs that build on each other:
    1. First trace (you just did this)
    2. Trace ↔ log correlation
    3. Slow SQL drill-down
    4. RUM outage detection
    5. Custom metric + alarm
    6. WAF event investigation
    7. Saved searches in Log Analytics
    8. Stack Monitoring for ATP
    9. Chaos drill (the failure injection lab)
    10. Failed checkout post-mortem

2. **Observability v2 docs** — `site/observability-v2/` contains the golden workflows: which dashboards to open, which queries to run, which alarms to wire, organized by persona (SRE, security operator, business analyst).

3. **Detection rules walkthrough** — `site/observability/` plus the attack-lab containers under `services/` cover the security-observability story: WAF rules, OCI Vault audit pivots, the automated remediator's decision graph, and the Genrative AI–assisted incident summarization that closes the loop into the CRM portal.

For environment variable reference, see [CONFIGURATION.md](CONFIGURATION.md). For the system map and component interactions, see [ARCHITECTURE.md](ARCHITECTURE.md). For deeper deployment guides per substrate, see `site/getting-started/` (rendered as `mkdocs serve`, or browse the markdown directly).

If something is missing or wrong, open an issue on GitHub against `https://github.com/<github-username>/octo-apm-demo` with the deployment substrate, the step that failed, and the relevant `/ready` output.
