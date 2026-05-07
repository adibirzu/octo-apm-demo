# Lab 08 — Stack Monitoring + ATP health

## Objective

See the Autonomous Database in OCI Stack Monitoring as a unified
"resource" alongside the application pods, and use it to investigate
a database health concern that started as an APM symptom.

## Time budget

40 minutes.

## Prerequisites

- Lab 03.
- ATP onboarded as a Stack Monitoring `MonitoredResource`
  (`./deploy/oci/ensure_stack_monitoring.sh DRY_RUN=false`).
- The shop and admin hosts have active Management Agents if you want to
  demonstrate host discovery and host metrics.

## Steps

### 1. Discover the app hosts

Console → Observability & Management → **Stack Monitoring → Resource
Discovery**.

For each app host:

1. Click **Discover New Resource**.
2. Select **Resource Type = Host**.
3. Enter the deployment host FQDN, using `<shop-host-fqdn>` for the shop host
   and `<admin-host-fqdn>` for the admin host in public docs.
4. Select the Management Agent installed on the same host.
5. Select **Stack Monitoring and Log Analytics (recommended)** so discovery
   feeds both resource monitoring and log context.
6. Select **Enterprise Edition** unless the lab is explicitly running Standard
   Edition.
7. Click **Discover New Resource** and wait for **Succeeded**.
8. Open the host detail page and confirm CPU, memory, filesystem, process, and
   availability charts are present.

Do not commit real live hostnames, OCIDs, private IPs, or tenancy names in this
lab. Use ignored private runbooks for live delivery values.

### 2. Find the ATP in Stack Monitoring

Console → Observability & Management → **Stack Monitoring → Monitored
Resources**.

Filter Type = `Oracle Autonomous Transaction Processing`. You should
see `octo-atp` listed. Click it.

The resource page shows:

- **Health** — overall green/yellow/red.
- **Capacity** — CPU, storage, sessions, transactions per second.
- **Alarms** — anything currently firing on this resource.
- **Topology** — the graph of related resources (pods, services).

### 3. Read the topology

The shop + CRM pods point at this ATP. Stack Monitoring infers the
relationship from the OCID references in the pod env, so the topology
graph **already shows** drone-shop and crm-portal as dependents — no
manual configuration.

This is the value: at incident time, click the ATP, see what depends
on it, and prioritize the broadcast accordingly.

### 4. Trigger a session-pressure event

Run a high-concurrency burst against the shop:

```bash
for i in $(seq 1 50); do
    (curl -sS https://shop.example.tld/api/products?heavy=true > /dev/null) &
done
wait
```

Within 60-90 s, the **Sessions** chart on the ATP resource page should
show a spike.

### 5. Drill from Stack Monitoring to OPSI

On the ATP page, click **Operations Insights → Open**. OPSI shows
the same session timeline but with longer history and richer SQL
breakdowns:

- Top sessions by elapsed time.
- Top SQL statements (correlate with Lab 03's `SQL_ID`).
- Wait class breakdown (`User I/O`, `CPU`, `Concurrency`, etc.).

### 6. Cross-reference with APM

The session pressure should also be visible in APM:

- Service Topology shows `octo-drone-shop → ATP` with a thicker edge
  than usual.
- Trace Explorer for the burst window shows many parallel traces, all
  spending most of their time in the SQL span.

### 7. (Optional) Configure an alarm

Stack Monitoring resources expose their own metric namespace
(`oracle_oci_database`). Create an alarm:

```bash
oci monitoring alarm create \
    --compartment-id "$OCI_COMPARTMENT_ID" \
    --display-name "octo-atp-sessions-high-lab08" \
    --metric-compartment-id "$OCI_COMPARTMENT_ID" \
    --namespace "oracle_oci_database" \
    --query-text "Sessions[5m].max() > 80" \
    --severity "WARNING" \
    --body "ATP session count climbing — check Stack Monitoring topology for which pods are pressuring the DB." \
    --destinations "[\"$NOTIFICATIONS_TOPIC_OCID\"]" \
    --is-enabled true
```

Now session bursts page on-call automatically.

## Verify

```bash
./tools/workshop/verify-08.sh
```

Expected:

```
✓ ATP MonitoredResource 'octo-atp' exists in Stack Monitoring
✓ Stack Monitoring health is reachable
✓ topology shows ≥ 1 dependent resource (shop or crm pod)
PASS — Lab 08 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `octo-atp` not in Monitored Resources | Onboarding script not run | `DRY_RUN=false ./deploy/oci/ensure_stack_monitoring.sh` |
| Topology graph empty | Pods don't expose ATP OCID in env | Pods need `OCI_ATP_OCID` env var; some operators leave it implicit and discovery doesn't fire |
| OPSI panel says "No data" | OPSI not enabled on the ATP | Console → ATP → Tools → Operations Insights → Enable |

## Read more

- [Observability v2 → Stack Monitoring (ATP)](../observability-v2/stack-monitoring.md)
- [Stack Monitoring docs](https://docs.oracle.com/en-us/iaas/stack-monitoring/)

---

[← Lab 07](lab-07-saved-search.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 09 → Chaos drill →](lab-09-chaos-drill.md)
