# octo-load-control

Named workload-profile orchestrator. Operators hit one REST endpoint
(`POST /runs`) with a profile name; load-control does the rest —
dispatches to the traffic-generator / chaos admin / browser-runner /
stress job, stamps every downstream signal with the run_id, emits OCI
Events on lifecycle transitions, and keeps an append-only audit trail.

## Why this exists

- The demo previously had 5+ ad-hoc buttons (traffic burst, chaos
  apply, chaos clear, simulation toggles...). Each used a different
  mechanism. Operators had to remember which was which.
- After a run, an SRE asking "what caused this APM spike?" had no
  single source of truth. Load-control's ledger is that source.
- Named profiles (see `profiles.py`) are **data**, not code — adding a
  new profile is a PR that doesn't touch the control plane logic.

## Profiles (12)

| Name | Target | Executor | Expected signal |
|---|---|---|---|
| `db-read-burst` | ATP | traffic-generator | APM DB span count ↑ |
| `db-write-burst` | ATP | traffic-generator | APM DB writes ↑, OPSI top SQL ↑ |
| `web-checkout-surge` | shop + CRM | traffic-generator | APM checkout p95 ↑ |
| `crm-backoffice-surge` | CRM admin | traffic-generator | CRM admin latency ↑ |
| `browser-journey` | browser | browser-runner (phase 4) | RUM sessions ↑ |
| `app-exception-storm` | shop | traffic-generator | 5xx alarm FIRING |
| `cache-miss-storm` | octo-cache | traffic-generator | cache hit ratio ↓ |
| `stream-lag-burst` | octo-event-stream | k8s-stress (phase 5) | consumer lag ↑ |
| `container-cpu-pressure` | OKE pod | k8s-stress (phase 8) | HPA scales ↑ |
| `container-memory-pressure` | OKE pod | k8s-stress (phase 8) | OOMKilled > 0 |
| `vm-cpu-io-pressure` | Compute VM | vm-stress (phase 8) | host CPU ↑ |
| `edge-auth-failure-burst` | API Gateway | edge-fuzz (phase 3) | WAF detected ↑ |

Executors marked "phase N" return `{status: not-yet-implemented}` today;
the control-plane contract is stable so downstream workers can land
independently.

## REST API

```
GET    /profiles                list all 12
GET    /profiles/{name}         profile detail
POST   /runs                    launch — body: {profile, duration_seconds, operator}
GET    /runs                    recent runs, newest first
GET    /runs/{run_id}           run detail
DELETE /runs/{run_id}           cancel (best effort — ignored if already terminal)
GET    /health                  liveness + ledger check
```

Launch response includes the `run_id` — use it to pivot across APM,
Log Analytics, RUM, and Monitoring as per the
[correlation contract](../../site/architecture/correlation-contract.md).

## Run ledger

Append-only. Default: `LocalJsonLedger` writing JSONL to
`~/.octo-load-control/runs.jsonl` (or `$LOAD_CONTROL_LEDGER_PATH`).
OKE deploy mounts a PVC at `/data` for persistence across pod
restarts. Production tenancies can swap in the OCI Object Storage
ledger (see [KG-024](../../site/observability/enhancement-plan.md))
for cross-region durability.

## OCI Events emission

On every state transition:

```json
{
  "eventType": "com.octodemo.load-control.run.started",
  "source": "octo-load-control",
  "eventTime": "2026-04-22T20:14:03.123Z",
  "data": {
    "run_id": "abc-...",
    "profile_name": "web-checkout-surge",
    "operator": "alice",
    "duration_seconds": 300,
    "state": "running"
  }
}
```

Consumers include the Coordinator (for auto-remediation hooks) and the
CRM Simulation Lab (for operator-facing dashboards).

## Deploy

### OKE

```bash
docker build --platform linux/amd64 \
    -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-load-control:latest \
    services/load-control/
docker push ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-load-control:latest

DNS_DOMAIN=octodemo.cloud OCIR_REGION=… OCIR_TENANCY=… IMAGE_TAG=latest \
envsubst < services/load-control/k8s/deployment.yaml | kubectl apply -f -
```

### Docker-compose (VM)

Add to `deploy/vm/docker-compose-unified.yml`:

```yaml
  load-control:
    image: ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-load-control:${TAG:-latest}
    restart: unless-stopped
    networks: [octo]
    environment:
      LOAD_CONTROL_LEDGER_PATH: /data/runs.jsonl
      TRAFFIC_GENERATOR_URL: http://traffic-generator:8080
      CRM_CHAOS_ADMIN_URL: http://crm:8080
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-gateway:4318
      OCI_EVENTS_TOPIC_URL: "${OCI_EVENTS_TOPIC_URL}"
    volumes:
      - load-control-data:/data
    ports:
      - "8081:8080"
```

## Usage

```bash
# List profiles
curl -s http://load-control.octo-load-control.svc.cluster.local:8080/profiles | jq '.[].name'

# Launch a profile
curl -sS -X POST \
    http://load-control.octo-load-control.svc.cluster.local:8080/runs \
    -H 'Content-Type: application/json' \
    -d '{"profile":"web-checkout-surge","duration_seconds":300,"operator":"alice"}'

# Tail recent runs
curl -s http://load-control.octo-load-control.svc.cluster.local:8080/runs | jq
```

## Tests

```bash
cd services/load-control
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
# 36 passed
```

Split across:
- `test_profiles.py` — registry invariants (exactly 12, all fields
  present, string-lookup works, expected signals populated for
  operator-facing executors).
- `test_runs.py` — Run model JSON round-trip + ledger contract
  (InMemory + LocalJson flavors).
- `test_api.py` — FastAPI routes + validation + cancel race.

## Next

- KG-024: OCI Object Storage ledger backend.
- Phase 4 (browser-runner): wires into `ExecutorKind.BROWSER_RUNNER`.
- Phase 8 (container-lab, vm-lab): wires into `K8S_STRESS` + `VM_STRESS`.
- Phase 3 (edge-gateway): wires into `EDGE_FUZZ`.
