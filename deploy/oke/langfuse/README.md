# Langfuse Test Stack on OKE

This is the low-resource OKE path for a dedicated OCTO-DEMO Langfuse test
environment such as `https://langfuse.octodemo.cloud`.

The script is intentionally separate from the production Shop/CRM OKE deploy:
it deploys Langfuse web, worker, Postgres, ClickHouse, Redis, and MinIO in
`octo-langfuse` with one replica each and small resource requests. It also
refuses to use an OKE cluster outside the target OCTO project VCN unless the
operator explicitly sets `ALLOW_DIFFERENT_VCN=true`.

## Preflight

```bash
./deploy/oke/deploy-langfuse.sh --check
```

For emdemo, defaults are read from `credentials/emdemo/outputs.json`:

- `COMPARTMENT_ID`
- `TARGET_VCN_ID`
- `OCI_LB_SUBNET_OCID`

If the OKE cluster already exists in that VCN, the script creates a temporary
kubeconfig, verifies Kubernetes permissions, checks the storage class, and
prints the node summary.

## Apply

```bash
LANGFUSE_HOSTNAME=langfuse.octodemo.cloud \
LANGFUSE_PUBLIC_URL=https://langfuse.octodemo.cloud \
./deploy/oke/deploy-langfuse.sh
```

Secrets are generated at deploy time unless provided through environment
variables. Do not commit generated secrets or Langfuse project ingestion keys.

## Optional App Exporter Secret

After creating a project in the new Langfuse instance, wire OKE Shop telemetry
to it by passing project ingestion keys:

```bash
APP_LANGFUSE_PUBLIC_KEY=pk-lf-... \
APP_LANGFUSE_SECRET_KEY=sk-lf-... \
LANGFUSE_PROJECT_NAME=drones.octodemo.cloud \
./deploy/oke/deploy-langfuse.sh
```

The script updates `octo-llmetry` in the Shop namespace. The Shop deployment
then exports the same assistant spans to OCI APM and Langfuse OTLP with
`assistant.project.name`, `llmetry.project.name`, and `langfuse.project.name`
set to the project name.

## Low-Usage Defaults

These defaults are intentionally below Langfuse's production sizing guidance.
Use this stack as a test/visibility endpoint for OCTO-DEMO projects, not as a
high-throughput production Langfuse service.

| Component | Replicas | Request |
|---|---:|---:|
| Langfuse web | 1 | `250m` CPU, `512Mi` memory |
| Langfuse worker | 1 | `250m` CPU, `512Mi` memory |
| Postgres | 1 | `100m` CPU, `256Mi` memory |
| ClickHouse | 1 | `250m` CPU, `1Gi` memory |
| Redis | 1 | `50m` CPU, `128Mi` memory |
| MinIO | 1 | `100m` CPU, `256Mi` memory |

The OCI Load Balancer uses flexible shape `10-10` Mbps by default. Increase
only when test traffic requires it.
