# Deploy Readiness

This page explains what the repo can verify automatically before a
rollout. It is **not** the live status page for the shared `DEFAULT`
tenancy.

## Repo-level verification

Run the canonical verifier from the repo root:

```bash
bash deploy/verify.sh
```

`deploy/verify.sh` currently checks:

- shell syntax for every `deploy/*.sh`
- plain YAML parsing for non-Helm manifests
- Helm chart render and `helm lint` for `deploy/helm/octo-apm-demo`
- JSON manifest validity
- Terraform format drift plus root-stack `terraform validate`
- `docker compose config` for the unified VM stack
- pre-flight required-variable enforcement
- `mkdocs build --strict`
- root deploy tests, provisioning-wizard tests, and shop/crm/tool pytest suites
- lightweight template-render smoke for both apps

Latest local release gate, May 14, 2026:

```text
VERIFY PASSED — 0 warning(s)
```

That run included full Shop and CRM pytest groups, strict MkDocs, Helm
render/lint, Terraform validation, Docker compose config, Kubernetes client
dry-run for rendered Helm, and template smoke checks.

The latest shared private rollout validated by this gate is immutable image
tag `obs-20260514203801`. Post-rollout smoke checks covered the public
round-robin load-balanced Shop/Admin routes, direct VM checkout, OKE checkout,
APM trace lookup, Log Analytics trace/order/payment-gateway correlation, and
OCI Monitoring custom metrics for the VM and OKE service names.

Supplementary targeted checks:

```bash
python3 -m pytest -q tests/test_unified_deploy_surface.py
bash deploy/compute/validate.sh
python3 -m pytest -q services/load-control/tests/test_profiles.py \
  services/load-control/tests/test_api.py \
  services/load-control/tests/test_runs.py
```

## Non-destructive rollout checks

Run these before touching a shared demo route. They validate the same
deployment contract used by the VM and OKE paths without changing the
public Load Balancer routing policy.

```bash
bash deploy/verify.sh
bash deploy/compute/validate.sh

DNS_DOMAIN=<domain> \
OCIR_REGION=<region> \
OCIR_TENANCY=<namespace> \
IMAGE_TAG=<immutable-tag> \
OKE_CLUSTER_NAME=octo-apm-demo-oke \
SERVER_DRY_RUN=true \
APPLY=false \
bash deploy/oke/deploy-oke.sh

APPLY=false bash deploy/oke/install-oci-kubernetes-monitoring.sh
```

Live promotion stays separate from validation:

- `deploy/oke/wire-existing-lb-backends.sh --round-robin-active --apply`
  only after VM and OKE direct smoke tests pass.
- `deploy/oke/wire-existing-lb-backends.sh --rollback-active-vm` returns
  the active backend sets to VM-only if the OKE path regresses.
- Playwright E2E should cover login, cart, checkout, payment rail, order
  view, and admin order visibility against both public routes during the
  round-robin period.
- APM Trace Explorer must show the browser/user action, Shop, Java payment
  gateway, Admin/CRM, and database spans for a successful purchase.
- Log Analytics saved searches must return matching records for the same
  trace ID, workflow ID, order ID, payment gateway request ID, and service
  names before the deployment is promoted.
- Deployment parity checks must show the same capability contract across
  OKE raw manifests, Helm, two-instance Compute, unified VM, and local
  containers: service namespace/instance IDs, Java payment gateway,
  Workflow Gateway/Select AI where Oracle ATP is available, LLMetry/Langfuse
  flags, payment simulation flags, and Log Analytics `SOC Application Logs`
  annotations.

## Manual steps still outside Terraform

Two OCI integrations still require operator follow-through:

| Step | Why manual | Current helper |
|---|---|---|
| RUM web application registration | `oci_apm_config_config` still rejects `config_type = "WEB_APPLICATION"` | Console after `terraform apply` |
| Log Analytics source registration | LA source binding is outside the current Service Connector schema | `python3 tools/create_la_source.py ...` or Console |

## What repo verification does not prove

| Concern | Why it is separate |
|---|---|
| Live ATP state | Requires real tenancy state; the shared `DEFAULT` ATP can still be `STOPPED` |
| Ingress/controller health | Depends on current OKE node readiness |
| Public DNS correctness | Depends on live OCI DNS records and delegation |
| OCIR pull behavior on the current node class | Requires a real pod pull on the target cluster |
| Playwright E2E | Requires a deployed, reachable tenancy plus optional SSO/test credentials |

## Fresh-tenancy gate before E2E

Do not hand a tenancy to Playwright until all of these pass:

1. `kubectl get deploy -n octo-drone-shop octo-drone-shop` shows `2/2`.
2. `kubectl get deploy -n enterprise-crm enterprise-crm-portal` shows `2/2`.
3. `kubectl -n ingress-nginx get endpoints` shows non-empty controller endpoints.
4. `oci db autonomous-database get ...` shows `AVAILABLE` for `octo-apm-demo-atp`.
5. Public DNS resolves `shop.<domain>` and `crm.<domain>`, or you have a temporary host override.
6. `INTERNAL_SERVICE_KEY` exists for cross-service smoke.
7. `octo-sso` plus an OCI IAM Identity Domain test user exist before the SSO spec.

## Failure triage

| Symptom | First place to look |
|---|---|
| `VERIFY FAILED` in the Helm section | Run `helm template` / `helm lint` manually with the same flags |
| Public hostnames do not resolve | `dig +noall +answer shop.<domain> @1.1.1.1` |
| Ingress `0/2` with no endpoints | `kubectl -n ingress-nginx get deploy,pods,endpoints -o wide` |
| Pods stuck in `ContainerCreateFailed` | `kubectl describe pod ...` plus OCIR pull-secret refresh |
| `/ready` still fails after rollout | Check ATP state and wallet/auth secrets first |
