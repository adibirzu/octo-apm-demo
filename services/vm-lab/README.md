# octo-vm-lab

A dedicated OCI Compute VM whose only job is to absorb stress so
operators learn to read host-level telemetry (CPU, memory, IO, process
state, syslog) via the OCI Management Agent → Stack Monitoring path.

Pairs with `services/container-lab/` (same idea, K8s flavour).

## What it ships

| File | Purpose |
|---|---|
| `cloud-init.yaml` | One-shot OCI Compute bootstrap: installs Management Agent, stress-ng, and clones this repo to `/opt/octo`. |
| `scripts/apply-stress.sh` | Launches a stress profile (`cpu` / `io` / `mem`) as a systemd-run transient unit named `octo-stress-<run_id>.service` so every run has a predictable journalctl trail. |
| `scripts/clear-stress.sh` | Stops one unit (by `RUN_ID`) or all `octo-stress-*` units. |

## Deploy the VM

Create an OCI Compute instance in a compartment you control (e.g. a
dedicated `octo-vm-lab` compartment). Shape: `VM.Standard.E5.Flex` with
2 OCPU / 8 GB is sufficient — stress-ng will saturate 2 OCPU happily.

Paste `cloud-init.yaml` into the Console **Cloud-init script** field at
create time. When the instance comes up, ssh in and verify:

```bash
systemctl status oracle.mgmt_agent || true
stress-ng --version
ls /opt/octo/services/vm-lab
```

## Apply a stress profile

```bash
sudo RUN_ID=$(uuidgen) KIND=cpu DURATION_SECONDS=300 \
    /opt/octo/services/vm-lab/scripts/apply-stress.sh

# Watch via journalctl
journalctl -u "octo-stress-${RUN_ID}.service" -f
```

## Observe

| Signal | Where |
|---|---|
| Host CPU utilisation | Stack Monitoring → Monitored Resource for this VM |
| Process state (D, R, S) | `top` locally; OCI Logging `syslog` + `management-agent` logs |
| Disk latency | Stack Monitoring → Performance Hub |
| stress-ng audit trail | `journalctl -u octo-stress-*.service --no-pager` |

The `run_id` appears in the unit name AND in the `OCTO_RUN_ID` env
stamped on every emitted signal — join with APM traces or load-control
runs to produce the cross-signal evidence the correlation contract
promises.

## Clear everything

```bash
# One profile
RUN_ID=<uuid> ./scripts/clear-stress.sh

# Every active stress run on this host
./scripts/clear-stress.sh
```

## Wire into octo-load-control

The `vm-cpu-io-pressure` profile (already declared in load-control)
has `ExecutorKind.VM_STRESS`. The load-control executor for that kind
will SSH to the lab VM and invoke `apply-stress.sh` with the active
run_id — tracked as KG-032.

## Safety

`systemd-run` wraps each launch with:

- `RuntimeMaxSec` — hard cap from `DURATION_SECONDS`.
- `TimeoutStopSec` — 10 s graceful shutdown before SIGKILL.

So a forgotten stress run cannot run past its declared duration; worst
case it's ignored for `DURATION_SECONDS` seconds and then cleaned up.

Do NOT run `apply-stress.sh` on a shared VM or on any host you don't
own — the whole point is to make the host miserable.
