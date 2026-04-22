# Shared helpers for every workshop verifier.
# Each verifier sources this and uses ok / fail / require / pass / abort.

set -uo pipefail

red()    { printf "\033[31m%s\033[0m" "$*"; }
green()  { printf "\033[32m%s\033[0m" "$*"; }
yellow() { printf "\033[33m%s\033[0m" "$*"; }

errors=0

ok()   { printf "%s %s\n" "$(green '✓')" "$*"; }
fail() { printf "%s %s\n" "$(red   '✗')" "$*" >&2; errors=$((errors + 1)); }
warn() { printf "%s %s\n" "$(yellow '!')" "$*"; }

require_var() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        fail "env var ${name} is required for this verifier"
    fi
}

require_cmd() {
    local cmd="$1"
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        fail "command '${cmd}' not on PATH"
    fi
}

pass_or_fail() {
    local lab="$1"
    if [[ "${errors}" -gt 0 ]]; then
        red "FAIL"; printf " — Lab %s incomplete (%d check(s) failed)\n" "${lab}" "${errors}"
        exit 1
    fi
    green "PASS"; printf " — Lab %s complete\n" "${lab}"
    exit 0
}
