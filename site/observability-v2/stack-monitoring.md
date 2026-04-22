# Stack Monitoring — Autonomous Database

OCI Stack Monitoring complements APM traces with a unified topology +
health view of the underlying Autonomous Database. Once the ATP is
registered as a `MonitoredResource`, health, performance, and capacity
metrics become visible in the Stack Monitoring console alongside the OKE
workloads.

## Why it matters

- APM gives per-request DB spans (`DbOracleSqlId`, statement text) but
  no database-wide health view.
- DB Management + Operations Insights surface SQL tuning advice but sit
  in a separate console.
- Stack Monitoring bridges the two: a single topology where the ATP node
  is wired to the shop/CRM pods and alarms inherit the trace context.

## Onboarding the ATP

Use the helper script:

```bash
COMPARTMENT_ID=ocid1.compartment.oc1..xxx \
AUTONOMOUS_DATABASE_ID=ocid1.autonomousdatabase.oc1..xxx \
SM_RESOURCE_NAME=octo-atp \
./deploy/oci/ensure_stack_monitoring.sh          # dry run (default)

DRY_RUN=false \
COMPARTMENT_ID=ocid1.compartment.oc1..xxx \
AUTONOMOUS_DATABASE_ID=ocid1.autonomousdatabase.oc1..xxx \
./deploy/oci/ensure_stack_monitoring.sh          # actually register
```

The script is idempotent — re-runs short-circuit when a MonitoredResource
with the same name already exists in the compartment.

## Verification

1. OCI Console → Observability & Management → Stack Monitoring → Monitored Resources
2. Filter by resource type `Oracle Autonomous Transaction Processing`
3. Look for `octo-atp` — click through to view health, capacity, and
   resource topology.

## Alarms

Default Stack Monitoring alarms cover ATP CPU utilization, storage
pressure, and connection count. If additional alarms are required, add
them to `deploy/oci/ensure_monitoring.sh` so they are re-created on new
tenancy bootstraps.

## Why shell instead of Terraform

As of this writing, `oci_stack_monitoring_monitored_resource` is still
listed as preview for several resource types (the Autonomous Database
resource type in particular). The shell wrapper is predictable today and
can migrate to Terraform later — the module boundary in
`deploy/oci/ensure_stack_monitoring.sh` keeps the migration path clear.
