#!/usr/bin/env bash
# Validate the gateway's collector config without spinning up the
# full agent. Uses the otelcol-contrib `validate` subcommand if
# the binary is available; falls back to YAML-only sanity if not.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${SCRIPT_DIR}/../config/otel-collector.yaml"

red()   { printf "\033[31m%s\033[0m" "$*"; }
green() { printf "\033[32m%s\033[0m" "$*"; }

if ! python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "${CONFIG}" 2>/dev/null; then
    red "FAIL"; printf " %s does not parse as YAML\n" "${CONFIG}"
    exit 1
fi
green "OK"; printf " YAML parses\n"

# Required pipelines must exist
required_keys='["receivers", "processors", "exporters", "service"]'
if python3 - "${CONFIG}" <<'PY'
import json, sys, yaml
required = json.loads('["receivers", "processors", "exporters", "service"]')
data = yaml.safe_load(open(sys.argv[1]))
missing = [k for k in required if k not in data]
if missing:
    print(f"missing top-level keys: {missing}", file=sys.stderr)
    sys.exit(1)
pipelines = data["service"].get("pipelines", {})
for need in ("traces", "metrics", "logs"):
    if need not in pipelines:
        print(f"missing pipeline: {need}", file=sys.stderr)
        sys.exit(1)
PY
then
    green "OK"; printf " all top-level + pipeline keys present\n"
else
    red "FAIL"; printf " collector config is missing required keys\n"
    exit 1
fi

# Optional: real validation if otelcol-contrib is on PATH
if command -v otelcol-contrib >/dev/null 2>&1; then
    if otelcol-contrib validate --config "${CONFIG}" >/dev/null 2>&1; then
        green "OK"; printf " otelcol-contrib validate\n"
    else
        red "FAIL"; printf " otelcol-contrib validate\n"
        otelcol-contrib validate --config "${CONFIG}" 2>&1 | head -10
        exit 1
    fi
else
    printf " (skipped: otelcol-contrib not on PATH — install for full validation)\n"
fi

green "ALL CHECKS PASSED"; printf "\n"
