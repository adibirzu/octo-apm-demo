# Lab 05 — Custom metric + alarm

## Objective

Publish a custom metric to OCI Monitoring, attach an alarm with the
correlation contract annotations, and verify the alarm fires when
conditions are met.

## Time budget

40 minutes.

## Prerequisites

- Lab 01.
- `OCI_COMPARTMENT_ID` set in the shop pod env (already done by
  `deploy/init-tenancy.sh`).

## Steps

### 1. Confirm custom metrics are flowing

The shop publishes a handful of custom metrics on startup
(`shop/server/observability/oci_monitoring.py`). Confirm they're
arriving:

```bash
oci monitoring metric-data summarize-metrics-data \
    --compartment-id "$OCI_COMPARTMENT_ID" \
    --namespace octo_drone_shop \
    --query-text 'shop.checkout.count[1m].sum()' \
    --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
    --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    | jq '.data[].aggregated-datapoints[-3:]'
```

If the array is empty, no requests have been made — generate some:

```bash
for i in $(seq 1 20); do
    curl -sS https://shop.example.tld/api/products > /dev/null
done
```

Wait 60 s and re-query.

### 2. Create an alarm (Console)

Console → Monitoring → **Alarm Definitions → Create Alarm**.

| Field | Value |
|---|---|
| Alarm Name | `octo-shop-error-rate-lab05` |
| Alarm Severity | Warning |
| Compartment | (your demo compartment) |
| Metric Namespace | `octo_drone_shop` |
| Metric Name | `shop.http.errors_5xx` |
| Interval | 1 m |
| Statistic | sum |
| Trigger Operator | greater than |
| Trigger Value | 0 |
| Alarm Body | `Shop is emitting 5xx errors. Run-id: {annotation.run_id}. Trace exemplar: {annotation.trace_exemplar}.` |
| Notifications Topic | (any topic you control — or create a new one with email destination) |

Save.

### 3. Same alarm, via OCI CLI

```bash
oci monitoring alarm create \
    --compartment-id "$OCI_COMPARTMENT_ID" \
    --display-name "octo-shop-error-rate-lab05" \
    --metric-compartment-id "$OCI_COMPARTMENT_ID" \
    --namespace "octo_drone_shop" \
    --query-text "shop.http.errors_5xx[1m].sum() > 0" \
    --severity "WARNING" \
    --body "Shop is emitting 5xx errors. Run-id: {annotation.run_id}. Trace exemplar: {annotation.trace_exemplar}." \
    --destinations "[\"$NOTIFICATIONS_TOPIC_OCID\"]" \
    --is-enabled true
```

### 4. Trigger it

Force a 5xx by hitting a route that intentionally fails:

```bash
for i in $(seq 1 5); do
    curl -sS -o /dev/null -w "%{http_code}\n" \
        -X POST https://shop.example.tld/api/orders \
        -H "Content-Type: application/json" \
        -d '{"customer_id": 0, "items": []}'
done
```

5xx responses (or 4xx — the shop emits a custom counter for both)
should bump the metric within a minute.

### 5. Watch the alarm fire

Console → Monitoring → Alarm Definitions → click your alarm. The
state should flip from `OK` to `FIRING` within 60 s.

The notification destination receives a payload with the annotations
**baked into the body**. Check your email/Slack — the message should
quote `Run-id: none` (since we didn't set one) and a real
`Trace exemplar` from the offending request.

### 6. Resolve

Wait two minutes without sending more bad requests. The alarm
auto-resolves to `OK`.

## Verify

```bash
./tools/workshop/verify-05.sh
```

Expected:

```
✓ custom namespace octo_drone_shop has metrics in the last hour
✓ alarm 'octo-shop-error-rate-lab05' exists
✓ alarm body references annotation contract (run_id, trace_exemplar)
PASS — Lab 05 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Empty `metric-data summarize-metrics-data` | App not publishing | Check pod env `OCI_COMPARTMENT_ID`; restart pod |
| Alarm never fires | Wrong query operator | `> 0` is the trick; `> 1` would need 2+ errors per minute |
| Alarm body has literal `{annotation.run_id}` | Annotation not set on the metric | The annotation contract requires the publisher to send the value; for now, leave it as `none` until lab 09 (chaos drill) |

## Read more

- [Observability → Metrics](../observability/metrics.md)
- [Operations → Alarms & Health](../operations/alarms.md)
- [OCI Monitoring docs](https://docs.oracle.com/en-us/iaas/Content/Monitoring/home.htm)

---

[← Lab 04](lab-04-rum-outage-detection.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 06 → WAF event investigation →](lab-06-waf-event-investigation.md)
