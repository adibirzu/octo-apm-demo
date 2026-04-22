#!/usr/bin/env bash
# Stop any active stress run.
#
# Usage:
#   RUN_ID=<uuid> ./clear-stress.sh   # stop a specific run
#   ./clear-stress.sh                 # stop ALL octo-stress-* units

set -uo pipefail

if [[ -n "${RUN_ID:-}" ]]; then
    sudo systemctl stop "octo-stress-${RUN_ID}.service" 2>/dev/null || true
    echo "stopped octo-stress-${RUN_ID}"
else
    for unit in $(systemctl list-units --plain --no-legend 'octo-stress-*.service' | awk '{print $1}'); do
        sudo systemctl stop "${unit}" 2>/dev/null || true
        echo "stopped ${unit}"
    done
fi
