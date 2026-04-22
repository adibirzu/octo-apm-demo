#!/usr/bin/env bash
# Apply a VM stress profile with a bounded duration.
#
# Usage on the target VM:
#   sudo RUN_ID=$(uuidgen) KIND=cpu DURATION_SECONDS=300 \
#     ./services/vm-lab/scripts/apply-stress.sh
#
# Kinds:
#   cpu   — stress-ng --cpu $(nproc) --cpu-load 80
#   io    — stress-ng --io 4 --hdd 2 --hdd-bytes 500M
#   mem   — stress-ng --vm 1 --vm-bytes 1024M
#
# Every run is tagged with the run_id in the systemd unit name so
# `journalctl -u octo-stress@${RUN_ID}` produces the audit trail.

set -euo pipefail

: "${RUN_ID:?run_id required}"
: "${KIND:=cpu}"
: "${DURATION_SECONDS:=300}"

if ! command -v stress-ng >/dev/null 2>&1; then
    echo "Installing stress-ng..."
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y stress-ng
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update && sudo apt-get install -y stress-ng
    else
        echo "Unsupported OS — install stress-ng manually" >&2
        exit 2
    fi
fi

case "${KIND}" in
    cpu)
        args="--cpu $(nproc) --cpu-load 80"
        ;;
    io)
        args="--io 4 --hdd 2 --hdd-bytes 500M"
        ;;
    mem)
        args="--vm 1 --vm-bytes 1024M --vm-hang 1"
        ;;
    *)
        echo "unknown kind: ${KIND}" >&2; exit 2 ;;
esac

echo "Launching stress kind=${KIND} run_id=${RUN_ID} duration=${DURATION_SECONDS}s"

# Wrap in systemd-run so the run ends up in journalctl with a
# predictable unit name (octo-stress-<run_id>) and a hard TimeoutStop.
exec sudo systemd-run \
    --unit="octo-stress-${RUN_ID}" \
    --description="octo vm-lab stress kind=${KIND} run_id=${RUN_ID}" \
    --property=TimeoutStopSec=10s \
    --property=RuntimeMaxSec="${DURATION_SECONDS}s" \
    /usr/bin/stress-ng ${args} --metrics-brief --timeout "${DURATION_SECONDS}s"
