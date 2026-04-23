# Lab 09 — Chaos drill

## Objective

Run a controlled chaos exercise: inject a database-latency fault,
detect it from APM + Monitoring + Log Analytics, then resolve it
without losing the audit trail.

## Time budget

50 minutes.

## Prerequisites

- Labs 01-05 complete (you understand traces, logs, and alarms).
- CRM Chaos Admin enabled
  (see [chaos-admin docs](../crm/operations/chaos-admin.md)).
- Authority to call the CRM `chaos-operator` role (typically scoped
  to a workshop user).

## Steps

### 1. Create the run_id

The CRM Chaos Admin emits a `run_id` for every chaos profile launch.
Note: this is the field every signal will carry per the
[correlation contract](../architecture/correlation-contract.md).

```bash
RUN_ID=$(uuidgen)
echo "RUN_ID=$RUN_ID"
```

### 2. Apply the chaos profile

```bash
curl -sS -X POST https://crm.example.tld/api/admin/chaos/apply \
    -H "Content-Type: application/json" \
    -H "X-Internal-Service-Key: $INTERNAL_SERVICE_KEY" \
    -H "X-Run-Id: $RUN_ID" \
    -d '{
        "profile": "db-latency",
        "duration_seconds": 600,
        "intensity": "moderate"
    }' | jq
```

Response includes the `chaos_id` and the `run_id` echoed back.

### 3. Watch the symptoms

#### APM
Open APM Trace Explorer, filter:

```
attributes."chaos.run_id" = '<RUN_ID>'
```

You should see traces with the SQL span suddenly taking 200-500 ms
instead of 5-20 ms.

#### Monitoring
The `shop.checkout.latency_p95` metric should climb above its baseline
within 90 s. The alarm you authored in Lab 05 fires.

#### Log Analytics
```
'Log Source' = 'octo-shop-app-json' and run_id = '<RUN_ID>' | head limit = 50
```
Every shop request that ran during the chaos window is here. Note the
`Duration` column — uniformly elevated.

### 4. Triage

The chaos run pretends to be a real incident. The on-call playbook is:

1. **Identify scope**: which routes/users/regions are affected?
   ```
   'Log Source' = 'octo-shop-app-json' and run_id = '<RUN_ID>' | stats count() by route
   ```
2. **Identify root cause**: is the DB itself slow, or the app's DB
   client?
   ```
   'Log Source' = 'octo-shop-app-json' and run_id = '<RUN_ID>' and "db.statement" != null | stats avg(Duration), count() by route
   ```
3. **Decide blast radius**: is this customer-impacting? (Latency p95 > 1s
   = page; > 500ms = warn; < 200ms = note.)

### 5. Resolve

```bash
curl -sS -X POST https://crm.example.tld/api/admin/chaos/clear \
    -H "Content-Type: application/json" \
    -H "X-Internal-Service-Key: $INTERNAL_SERVICE_KEY" \
    -H "X-Run-Id: $RUN_ID" \
    -d '{"chaos_id":"<from step 2>"}' | jq
```

Within 30 s, alarm clears, latency returns to baseline.

### 6. Postmortem

Pull the audit trail:

```bash
oci log-analytics query \
    --namespace-name "$LA_NAMESPACE" \
    --query-string "'Log Source' = 'octo-chaos-audit' | where run_id = '$RUN_ID'" \
    | jq '.data.results[] | {Time, action, profile, intensity, operator}'
```

You should see two rows: `apply` and `clear`, each tagged with the
operator who ran them. This is what you'd attach to the incident
ticket.

## Verify

```bash
./tools/workshop/verify-09.sh "$RUN_ID"
```

Expected:

```
✓ chaos profile 'db-latency' was applied (audit log row exists)
✓ APM has ≥ 5 traces tagged with run_id during the window
✓ Monitoring alarm transitioned OK→FIRING→OK during the window
✓ chaos clear emitted within 600 s of apply
PASS — Lab 09 complete
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `chaos/apply` returns 401 | Missing or wrong `X-Internal-Service-Key` | Check shared secret matches the CRM Pod env |
| Symptoms invisible | Chaos profile not actually applied | Check the chaos_state table: `kubectl exec -n octo-backend-prod <pod> -- python -c "from server.database import ..."` |
| APM trace filter returns nothing | The shop didn't receive any requests during the window | Hit `/api/products` with the `X-Run-Id` header in step 3 |

## Read more

- [Observability v2 → Chaos playbook](../observability-v2/chaos-playbook.md)
- [Operations → Chaos Engineering](../operations/chaos.md)

---

[← Lab 08](lab-08-stack-monitoring-atp.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Next: Lab 10 → End-to-end debug a failed checkout →](lab-10-failed-checkout.md)
