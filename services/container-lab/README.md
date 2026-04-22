# octo-container-lab

K8s Jobs that generate **pod-level stress** so HPA, throttling counters,
OOMKilled events, disk-saturation alarms, and Stack Monitoring health
dashboards all fire during demos.

## Jobs

| Manifest | Drives |
|---|---|
| `cpu-stress.yaml` | stress-ng `--cpu 2 --cpu-load 80` co-located with a shop pod via podAffinity. Trips HPA + container throttling metrics. |
| `memory-stress.yaml` | stress-ng `--vm 1 --vm-bytes 1024M` — allocates + touches memory. Can push the node into reclaim; on smaller nodes it will OOMKill the job itself first (which is the point — the kill event is what operators are learning to investigate). |
| `disk-stress.yaml` | stress-ng `--hdd 2 --hdd-bytes 500M` writing into emptyDir. Shows up as node disk-latency spikes in Stack Monitoring. |

Each Job has `ttlSecondsAfterFinished: 3600` so pods stick around for
inspection, and `activeDeadlineSeconds` as a hard stop in case an
operator forgets.

## Launch (manual)

```bash
RUN_ID=$(uuidgen) \
TARGET_NAMESPACE=octo-shop-prod \
CPU_LOAD_PERCENT=80 \
DURATION_SECONDS=300 \
envsubst < services/container-lab/k8s/cpu-stress.yaml | kubectl apply -f -
```

## Launch (via octo-load-control)

The `container-cpu-pressure` + `container-memory-pressure` profiles
(declared in `services/load-control/src/octo_load_control/profiles.py`)
target `ExecutorKind.K8S_STRESS`. When load-control's K8S_STRESS
executor lands (tracked as KG-031), launching is a single
`POST /runs` call.

## Observe

| Signal | Where |
|---|---|
| Container CPU utilization | Stack Monitoring → Monitored Resource `octo-drone-shop` |
| HPA scaling | `kubectl describe hpa -n octo-shop-prod octo-drone-shop` |
| CPU throttling | `kubectl top pod -n octo-shop-prod` + OCI Monitoring metric `container.cpu_throttling_nanoseconds` |
| OOMKilled | `kubectl get pods -n octo-shop-prod -o wide`; OCI Logging `eventLog` search for `OOMKilled` |
| Node disk latency | Stack Monitoring → node Monitored Resource → Performance chart |

Every stress Job tags its spans + logs with `run_id=${RUN_ID}` so the
workshop's Lab 09 (chaos drill) pattern works identically here.

## Safety

- `backoffLimit: 0` — a killed stress Job does not retry.
- `activeDeadlineSeconds` — hard cap on runtime.
- `resources.limits` — stress doesn't break out of the configured
  budget.
- `ttlSecondsAfterFinished` — pod retained 1h then garbage-collected.

Do NOT run these manifests in namespaces you don't own. They are
intentionally disruptive.
