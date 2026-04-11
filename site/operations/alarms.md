# Alarms & Health

## OCI Monitoring Alarms

| Alarm | MQL Query | Severity |
|---|---|---|
| High error rate | `app.errors.rate[1m].rate() > 5` | CRITICAL |
| DB latency | `app.db.latency_ms[1m].percentile(0.95) > 2000` | WARNING |
| Health down | `app.health[1m].min() < 1` | CRITICAL |
| CRM sync stale | `app.crm.sync_age_s[5m].max() > 600` | WARNING |
| Low stock | `app.inventory.low_stock_products[5m].max() > 3` | WARNING |

All alarms deliver via OCI Notifications to configured email/webhook.

## Health Endpoints

### Liveness (`/health`)
```json
{"status": "ok", "service": "octo-drone-shop"}
```
Always returns 200. K8s restarts the pod if this fails.

### Readiness (`/ready`)
```json
{
  "ready": true,
  "database": "connected",
  "db_type": "oracle_atp",
  "apm_configured": true,
  "rum_configured": true,
  "runtime": { "host.name": "...", "process.pid": 1 }
}
```
Checks DB connectivity. K8s removes the pod from the service if this fails.

## OCI Health Checks

HTTP monitor on `/ready` endpoint every 30 seconds. Configured via `deploy/oci/ensure_monitoring.sh`.

## Provisioning

```bash
COMPARTMENT_ID="<compartment-ocid>" \
SHOP_PUBLIC_URL="https://shop.yourcompany.cloud" \
ALARM_EMAIL="ops@yourcompany.cloud" \
./deploy/oci/ensure_monitoring.sh
```
