# octo-remediator

Alarm-driven recovery service. Receives OCI alarm notifications, matches
them against a **playbook catalog**, and executes — automatically for
tier-low actions (cache flush), approval-gated for tier-high actions
(rollout restart). Complete audit trail + correlation-contract
compliance.

Spec: OCI 360 Phase 5 — `octo-remediator`.

## Playbook catalog (3 shipped, easy to extend)

| Name | Tier | Matches | What it does |
|---|---|---|---|
| `cache-flush` | LOW | `cache.hit_ratio` metric / "cache stale" alarm | SCAN + DEL namespace keys in `octo-cache`. Permissive — DB fallback catches misses. |
| `scale-hpa` | MEDIUM | CPU-pressure alarms | Patch target HPA `minReplicas += 1`. Auto-applies when `OCTO_REMEDIATOR_AUTO_MEDIUM=true`; otherwise proposes. |
| `restart-deployment` | HIGH | "deployment unhealthy" / "pod crashloop" | Patch `kubectl.kubernetes.io/restartedAt` annotation. **Always proposes, never auto-applies** — drops in-flight connections. |

Add a playbook: drop a file in `src/octo_remediator/playbooks/`,
extend `Playbook`, register in `playbooks/__init__.py:CATALOG`. Wire
tests in `tests/test_playbooks.py`.

## Tier semantics

| Tier | Behavior |
|---|---|
| `LOW` | Auto-applied on match. Reversible + scoped. |
| `MEDIUM` | Auto-applied only when `OCTO_REMEDIATOR_AUTO_MEDIUM=true`. Otherwise proposes for approval. |
| `HIGH` | Always proposes. Requires `POST /runs/{id}/approve`. |

## API

```
POST  /events/alarm              Alarm webhook (OCI Notifications target)
GET   /playbooks                 Catalog
GET   /runs                      Recent proposals + executions
GET   /runs/{run_id}             Detail — state, actions, audit trail
POST  /runs/{run_id}/approve     Operator approves a PROPOSED run
POST  /runs/{run_id}/reject      Operator rejects
GET   /health
```

### Sample alarm webhook body

OCI Notifications delivers this shape to `/events/alarm`:

```json
{
  "id": "ocid1.alarm.oc1..xxx",
  "title": "octo-shop CPU > 80%",
  "body": "CPU pressure sustained for 5m on octo-drone-shop",
  "severity": "CRITICAL",
  "metric_name": "container_cpu_utilisation",
  "dimensions": {"deployment": "octo-drone-shop", "namespace": "octo-shop-prod"},
  "annotations": {
    "target_namespace": "octo-shop-prod",
    "target_deployment": "octo-drone-shop",
    "min_replicas_increment": "2"
  }
}
```

## Deploy (OKE)

The Deployment's ServiceAccount has a narrow ClusterRole: only
`deployments` + `horizontalpodautoscalers` can be `get/list/patch`ed.
No wildcard permissions. The playbooks fail closed if the RBAC
doesn't allow the action they want.

```bash
docker build -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-remediator:latest .
docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-remediator:latest

OCIR_REGION=… OCIR_TENANCY=… IMAGE_TAG=latest \
envsubst < k8s/deployment.yaml | kubectl apply -f -
```

## Wire OCI Notifications to the webhook

1. Console → Notifications → create a Topic `octo-alarms`.
2. Add Subscription: Protocol `HTTPS (Custom URL)`, Endpoint
   `https://backend.octodemo.cloud/remediator/events/alarm` (routed
   through the edge gateway).
3. Create an Alarm → Destinations → select `octo-alarms` topic.

When the alarm fires, Notifications POSTs to the webhook; the
remediator parses, matches, and either executes or proposes.

## Audit

Every run state transition lands in:

- `octo_remediator_runs` Redis stream (KG-036 — currently in-memory;
  the API is stable, the storage backend is pluggable).
- OCI Event `com.octodemo.remediator.run.<state>` (emission scaffolded
  in the api; enable by setting `OCI_EVENTS_TOPIC_URL`).

The workshop's Lab 09 (chaos drill) uses this pathway: launch a
`db-latency` profile via load-control, trigger the CPU alarm from the
workshop Lab 05, and watch the remediator propose a `scale-hpa` run
that the student approves or rejects.

## Tests

```bash
cd services/remediator
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
# 14 passed
```

Coverage:
- Catalog has at least one of each tier (LOW/MEDIUM/HIGH).
- Each playbook's `matches()` predicate accepts + rejects expected
  shapes.
- `extract_params` honours `annotations`.
- `cache-flush` dry-run returns a well-formed action record.
- API: health, list playbooks, cache-alarm auto-flush, crashloop-alarm
  proposes-only, approve → succeeded, reject locks, approve-unknown
  → 404.

## Follow-ups

- **KG-036**: swap in-memory `_RunStore` for an append-only Redis
  stream so runs survive restarts and multi-replica deployments.
- **KG-037**: auto-revert for `scale-hpa` — scheduled background job
  that undoes the bump after 10 min if CPU dropped below threshold.
- **KG-038**: Slack interactive approval — `/runs/{id}/approve` hit
  from a Slack action button instead of the dashboard.
- **KG-039**: metric publishing for `remediator.run.succeeded` count,
  `time_to_propose`, `time_to_approve` so SRE can SLO against the
  auto-rem pipeline.
