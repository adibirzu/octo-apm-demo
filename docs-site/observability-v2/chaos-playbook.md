# Chaos playbook

!!! warning "Shop has no chaos write endpoints"
    The Octo Drone Shop is a **reader** only. Chaos scenarios can be
    applied from either the Enterprise CRM admin page
    (`https://crm.octodemo.cloud/admin/chaos`) or from the Ops / cp
    portal. Any POST to `/api/admin/chaos/*` on the shop is a 404.

## Presets

| id | targets | faults | default TTL |
| --- | --- | --- | --- |
| `db-slow-checkout` | shop | `db.slow`, `workflow:checkout` | 300 s |
| `crm-sync-fail` | shop + crm | `http.502`, `path:/api/crm/sync` | 300 s |
| `payment-timeout` | shop | `http.timeout`, `path:/api/payments` | 300 s |
| `deadlock-cart` | shop | `db.deadlock`, `workflow:add-to-cart` | 300 s |
| `pool-exhaustion` | shop + crm | `db.pool_hold` | 600 s |
| `crm-admin-abuse` | crm | `http.burst`, `path:/api/admin` | 300 s |

## Apply (CRM operator only)

```bash
curl -sS https://crm.octodemo.cloud/api/admin/chaos/apply \
  -H 'Content-Type: application/json' \
  -b session.cookie \
  -d '{"scenario_id":"db-slow-checkout","target":"shop","ttl_seconds":300,"note":"demo"}'
```

## Clear

```bash
curl -sS -X POST https://crm.octodemo.cloud/api/admin/chaos/clear -b session.cookie
```

The `chaos-cleanup` Coordinator playbook also auto-clears stale scenarios
(tier `low`, no approval needed) when they exceed their TTL.

## Audit trail

Every apply/clear is written to the `chaos-audit` logger. The
`octo-chaos-audit` Log Analytics parser surfaces these rows in the
Security Posture dashboard.
