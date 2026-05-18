# Stack Monitoring — Autonomous Database

Current note for May 2026: OCI Stack Monitoring is still useful for this
lab, but Oracle has announced service deprecation. Treat this integration
as an private demo visibility enhancement, keep DB Management and Operations
Insights as the durable ATP investigation path, and avoid making new demo
content depend only on Stack Monitoring.

OCI Stack Monitoring complements APM traces with a unified topology +
health view of the underlying Autonomous Database. Once the ATP is
registered as a `MonitoredResource`, health, performance, and capacity
metrics become visible in the Stack Monitoring console alongside the OKE
workloads.

## Private Demo status

For the May 6, 2026 private demo Compute deployment, DB Management and
Operations Insights were enabled for the dedicated ATP, and Management
Agent resources were created for the private Compute hosts. Explicit
Stack Monitoring HOST auto-promote/plugin updates and ATP
`MonitoredResource` registration remain disabled because the tenancy
returned authorization/tagging errors for those operations. Use APM,
DB Management, and Operations Insights as the live drilldown path until
Stack Monitoring authorization is granted.

## Discover the app hosts

The app-server hosts must be discovered before Stack Monitoring can show host
CPU, memory, process, filesystem, and availability context next to the APM
trace and Log Analytics evidence. Use placeholders in tracked docs and enter
real hostnames only in the OCI Console or ignored private runbooks.

Console path:

```text
OCI Console -> Observability & Management -> Stack Monitoring -> Resource Discovery
```

For the shop host:

1. Click **Discover New Resource**.
2. Set **Resource Type** to **Host**.
3. Set **Resource Name** to `<shop-host-fqdn>`.
4. Set **Management Agent** to the agent installed on the shop host.
5. Under **Discover in**, select **Stack Monitoring and Log Analytics
   (recommended)**.
6. Under **License**, select **Enterprise Edition** unless the deployment
   explicitly requires Standard Edition.
7. Expand **Show advanced options** only when you need tags or custom
   properties.
8. Click **Discover New Resource**.
9. Wait for the discovery job status to become **Succeeded**.
10. Click the discovered host and verify host metrics, related logs, and
    resource topology.

Repeat the same flow for `<admin-host-fqdn>` with the management agent that
monitors the admin host.

When the UI is unavailable or you need a repeatable check, use the CLI discovery
payload shape with placeholders:

```json
{
  "discoveryType": "ADD",
  "discoveryClient": "host-discovery",
  "compartmentId": "<compartment-ocid>",
  "discoveryDetails": {
    "agentId": "<management-agent-ocid>",
    "resourceType": "HOST",
    "resourceName": "<host-fqdn>",
    "properties": {
      "propertiesMap": {}
    }
  }
}
```

```bash
oci stack-monitoring discovery-job create \
  --compartment-id "<compartment-ocid>" \
  --from-json file://host-discovery.json
```

The host discovery job is separate from APM Java agent instrumentation. APM App
Servers explains Java heap, CPU, request, and JVM behavior for the sidecar;
Stack Monitoring host discovery explains the underlying VM and makes the same
host easier to join with Log Analytics.

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
COMPARTMENT_ID=<COMPARTMENT_OCID> \
AUTONOMOUS_DATABASE_ID=<AUTONOMOUS_DATABASE_OCID> \
SM_RESOURCE_NAME=octo-atp \
./deploy/oci/ensure_stack_monitoring.sh          # dry run (default)

DRY_RUN=false \
COMPARTMENT_ID=<COMPARTMENT_OCID> \
AUTONOMOUS_DATABASE_ID=<AUTONOMOUS_DATABASE_OCID> \
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

## Official references

- Stack Monitoring overview:
  <https://docs.oracle.com/en-us/iaas/stack-monitoring/home.htm>
- Resource discovery and promotion:
  <https://docs.oracle.com/en-us/iaas/stack-monitoring/doc/promotion-and-discovery.html>
- CLI discovery jobs:
  <https://docs.oracle.com/en-us/iaas/stack-monitoring/doc/discovering-resource-using-command-line-interface-cli.html>
