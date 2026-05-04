# octo-apm-demo Helm chart

Installs the Drone Shop + Enterprise CRM Portal demo onto an **existing
OKE cluster**. It is the Helm equivalent of the manifests under
`deploy/k8s/oke/`, intended for operators who already have:

- an OKE cluster with a working ingress controller
- an Autonomous DB (ATP) with wallet and credentials
- OCIR repos populated with shop + crm images

If you have none of that, run `deploy/bootstrap.sh` instead — it
provisions ATP, OCIR, DNS, ingress, and the TLS material for you.

## Install

```bash
helm upgrade --install octo-apm-demo deploy/helm/octo-apm-demo \
  --namespace octo-drone-shop --create-namespace \
  --set global.dnsDomain=mydomain.example \
  --set global.image.tenancy=<OCIR_NAMESPACE> \
  --set global.image.tag=2026-04-24 \
  --set ingress.className=nginx \
  --set ingress.tls.secretName=my-tls-secret
```

The chart creates both `octo-drone-shop` and `enterprise-crm` namespaces
by default (`namespaces.create=true`), so a single release owns both
components. Pass `--namespace <anything>` purely to satisfy Helm's
per-release bookkeeping.

## Bring-your-own-secrets (default, recommended)

The chart references these Secrets **in each app namespace**. They must
exist before the pods will start:

| Secret             | Keys                                                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `octo-atp`         | `dsn`, `username`, `password`, `wallet-password`                                                                          |
| `octo-atp-wallet`  | `wallet.zip` (binary ATP wallet)                                                                                          |
| `octo-auth`        | `token-secret`, `internal-service-key`, `app-secret-key`, `bootstrap-admin-password`                                      |
| `octo-oci-config`  | `compartment-id`, optional `genai-endpoint`, `genai-model-id`                                                             |
| `octo-apm`         | optional: `endpoint`, `private-key`, `public-key`, `rum-endpoint`, `rum-web-application-ocid`                             |
| `octo-logging`     | optional: `log-group-id`, `log-id`, `log-chaos-audit-id`, `log-security-id`                                               |
| `octo-sso`         | optional: `idcs-domain-url`, `idcs-client-id`, `idcs-client-secret`                                                       |

`deploy/bootstrap.sh` seeds all of these from terraform outputs. For a
pre-existing cluster that already ran bootstrap, this chart is a drop-in
replacement for the raw manifests.

## Chart-managed secrets (one-shot install)

Set `secrets.create=true` to render Secrets from values. Never check the
filled `values.yaml` into git. Typical install:

```bash
helm upgrade --install octo-apm-demo deploy/helm/octo-apm-demo \
  --namespace octo-demo --create-namespace \
  --set secrets.create=true \
  --set secrets.data.atp.dsn=octoatp_low \
  --set secrets.data.atp.username=ADMIN \
  --set secrets.data.ociConfig.compartmentId=ocid1.compartment... \
  --set-file secrets.atpWallet=./wallet.zip \
  --values my.secrets.yaml
```

Put the remaining required secret values in `my.secrets.yaml` and keep
that file out of git. Avoid passing real secret material through shell
history.

Required runtime fields are validated at render time. Optional integration
fields are skipped so `optional: true` env lookups stay optional.

## TLS

Chart expects a pre-created TLS secret — by default `octo-apm-demo-tls`
in each app namespace. bootstrap.sh loads this from OCI Certificates;
for a manual setup:

```bash
kubectl -n octo-drone-shop create secret tls octo-apm-demo-tls \
  --cert=fullchain.pem --key=privkey.pem
kubectl -n enterprise-crm create secret tls octo-apm-demo-tls \
  --cert=fullchain.pem --key=privkey.pem
```

Set `ingress.tls.secretName=""` to disable TLS on the Ingress resource.

## Uninstall

```bash
helm uninstall octo-apm-demo --namespace octo-drone-shop
# Namespaces are created by the chart, so helm uninstall will NOT remove
# them (Kubernetes preserves namespaces to protect data). Remove manually
# if desired:
kubectl delete ns octo-drone-shop enterprise-crm
```

Helm does NOT touch ATP, OCIR, or DNS. Use `deploy/destroy.sh` or OCI
console for those.

## Differences vs deploy/k8s/oke/*

| Concern                       | Raw manifests (`envsubst`) | Helm chart                                  |
| ----------------------------- | -------------------------- | ------------------------------------------- |
| Templating                    | env vars                   | values.yaml + Go templates                  |
| Atomic upgrade/rollback       | no                         | yes (`helm rollback`)                       |
| Ingress                       | separate `ingress.yaml`    | toggled via `ingress.enabled`               |
| Secret seeding                | bootstrap.sh               | references OR chart-managed via `secrets.*` |
| Namespace creation            | common/namespaces.yaml     | `namespaces.create`                         |
| LoadBalancer Service per app  | yes (skipped by bootstrap) | no (use Ingress)                            |
| WAF-policy annotations        | yes                        | add via `shop.env.extra` /                  |
|                               |                            | manual annotation patch if needed           |

The chart intentionally drops the per-app `Service type=LoadBalancer`
that the raw manifests carry, because that's only useful when there is
no ingress controller. If you need it, install with `ingress.enabled=false`
and add a LoadBalancer Service manually, or extend this chart.

## Compatibility with deploy/bootstrap.sh

The chart's secret names, env var names, and labels match what
bootstrap.sh produces exactly. A cluster provisioned by bootstrap.sh can
be upgraded to Helm with:

```bash
# bootstrap.sh already created the secrets + namespaces.
helm upgrade --install octo-apm-demo deploy/helm/octo-apm-demo \
  --namespace octo-drone-shop \
  --set namespaces.create=false \
  --set global.dnsDomain=cyber-sec.ro \
  --set global.image.tenancy=$OCIR_NAMESPACE \
  --set global.image.tag=$IMAGE_TAG
```
