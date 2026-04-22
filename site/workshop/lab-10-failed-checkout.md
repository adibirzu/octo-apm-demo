# Lab 10 — End-to-end debug a failed checkout

## Objective

Reproduce the operator workflow when a customer reports "I tried to
buy a drone and it didn't work". Use only the observability stack —
no app source code reading allowed — and produce a single-page
postmortem.

## Time budget

60 minutes.

## Prerequisites

- All prior labs complete.

## Steps

### 1. The customer report

> *"At 14:47 today I tried to buy the OCTO Surveyor 6 drone. The page
> spun for a long time, then said 'sorry, something went wrong'. My
> session ID was on a sticker that said `S-91A2`."*

### 2. Find the RUM session

Console → APM → Real User Monitoring → Sessions Explorer.

Filter:
- Time range: 14:30-15:00.
- Properties → `session.id` = `S-91A2` (or whatever your synthetic
  session id was).

Open the session. You should see:

1. Page load `/` → `/shop` → `/product/octo-surveyor-6`.
2. Click `add_to_cart` (custom event).
3. Click `checkout_start` (custom event).
4. POST to `/api/orders` → **HTTP 500**.
5. `console.error` event with the message the customer saw.

### 3. Pivot to the backend trace

In the failed POST entry, click "View server-side trace". APM Trace
Explorer opens with the matching `trace_id`.

The flame chart shows:

- POST `/api/orders` (root)
  - `validate_payload` (12 ms — fine)
  - `lookup_customer` (8 ms — fine)
  - `lookup_products` (15 ms — fine)
  - `crm.sync_order` (4250 ms — **timeout**)
    - `httpx.POST https://backend.octodemo.cloud/api/orders` —
      circuit breaker `OPEN`
  - SQL `INSERT INTO orders` (succeeded)
  - response status = 500

So the order was actually written to the DB, but the cross-service
sync to CRM failed and the shop returned 500 to the user.

### 4. Investigate the CRM side

The trace's `crm.sync_order` span has `peer.service=enterprise-crm-portal`
but no child spans on the CRM side — typical of a network failure that
never reached the peer. Check:

```bash
kubectl get pods -n octo-backend-prod
```

Notice one of two CRM pods is `CrashLoopBackOff`.

```bash
kubectl logs -n octo-backend-prod <bad-pod> --previous | tail -30
```

The trailing log shows an `OperationalError: ATP wallet expired` —
the wallet rotated and one pod didn't pick up the new mount until it
restarted.

### 5. Cross-check with Log Analytics

```
'Log Source' = 'octo-shop-app-json'
  and route = '/api/orders'
  and http_status = 500
  and Time > dateTime('2026-04-22T14:45:00Z')
  and Time < dateTime('2026-04-22T15:00:00Z')
  | stats count() by error
```

You should see a single `error=crm_sync_timeout count=N` row,
confirming the failure was systemic to the time window — not a
one-off.

### 6. Resolve

```bash
# Force the bad pod to restart with the fresh wallet mount
kubectl delete pod -n octo-backend-prod <bad-pod>
```

It comes back healthy within 60 s. Re-test:

```bash
curl -sS https://backend.octodemo.cloud/ready | jq
# database.reachable=true, healthy
```

### 7. Communicate the resolution

The customer's order made it to the shop's DB despite the 500. The
shop's existing reconciliation job (`server/order_sync.py`) will pick
it up on the next run and push it to CRM. You can either:

- Manually trigger the reconciliation right now:
  ```bash
  curl -sS -X POST -H "X-Internal-Service-Key: $KEY" \
      https://drone.octodemo.cloud/api/integrations/crm/sync-order \
      -d '{"order_id": <from trace>}'
  ```
- Or wait for the 5-min cycle.

### 8. Write the postmortem

Use this template:

```markdown
# Postmortem — failed checkout S-91A2 — 2026-04-22

**Severity**: P3 (single user, no data loss).
**Duration**: ~12 min.
**Customer impact**: 1 user saw a 500; order did succeed in DB.

## Timeline
- 14:43 — ATP wallet rotation pushed.
- 14:45 — CRM pod B failed to mount new wallet, started CrashLoopBackOff.
- 14:47 — User S-91A2 hit checkout. crm.sync_order routed to pod B,
  timed out at 4250ms. Shop returned 500 (after writing the order).
- 14:55 — Operator restarted pod B, traffic recovered.
- 14:56 — Order reconciliation completed.

## Root cause
The CSI Secrets Store driver's reconciler fired but the existing pod
didn't restart on rotation; the only signal was a CrashLoopBackOff
that was masked by the second healthy pod.

## Fix
- Short-term: documented in runbook (this postmortem).
- Mid-term: switch from `optional: true` Secret references to
  `mountPropagation: HostToContainer` so rotations are picked up
  in-place without restart.
- Long-term: deploy reflector or annotation-driven pod restart on
  Vault rotation events.

## How we caught it
RUM session → APM trace → CRM logs → kubectl. ~7 minutes, mostly the
RUM session search.

## Detection gap
The CRM `/ready` probe returned 200 from the healthy pod, so a
naive "is CRM up?" check would have lied. Adding a per-pod synthetic
ping that asserts every replica responds within 5s would have caught
this in 60s.
```

## Verify

```bash
./tools/workshop/verify-10.sh
```

Expected:

```
✓ found at least one POST /api/orders trace with status 500 in the last 24h
✓ that trace contains a crm.sync_order span with status_code = ERROR
✓ at least one CRM pod restart in the same window
PASS — Lab 10 complete
GRADUATION — all 10 labs passed.
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Can't find session `S-91A2` | The example is illustrative; replace with a real RUM session ID from your tenancy | Generate one: open the shop in browser, do a checkout, note your session ID from dev tools |
| No 500s in traces | Healthy environment; chaos drill (Lab 09) should produce them | Re-run Lab 09 to inject failures |

## Read more

- [Architecture → Correlation Contract](../architecture/correlation-contract.md)
- [Operations → Alarms & Health](../operations/alarms.md)

---

[← Lab 09](lab-09-chaos-drill.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Workshop Home](index.md)

🎓 **Done!** Run `./tools/workshop/certify.sh` for your completion
passport.
