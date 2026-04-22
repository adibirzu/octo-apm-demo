# Chaos admin operations

See the shared [chaos playbook](../observability-v2/chaos-playbook.md).
This page captures CRM-specific operational guidance.

## Access

Users must hold the `chaos-operator` IDCS role. Assign via the IDCS
admin console; no code change required.

## TTL hygiene

- Hard upper bound: `CHAOS_MAX_TTL_SECONDS` (default 3600).
- The Coordinator `chaos-cleanup` playbook (tier `low`) auto-clears
  scenarios whose `expires_at` is in the past.

## Audit

The CRM admin router emits:

```
chaos.apply | scenario_id=... | target=shop|crm|both | ttl_seconds=...
chaos.clear | applied_by=<hashed-user>
```

Routed by the `octo-chaos-audit` Log Analytics parser into the Security
Posture dashboard and the `stale-chaos-scenario` correlation rule.
