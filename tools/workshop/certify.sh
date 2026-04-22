#!/usr/bin/env bash
# Workshop certification — re-runs every per-lab verifier and prints a
# completion passport.
#
# Each verifier may need lab-specific args (trace_id, run_id) — this
# script reads them from CERT_TRACE_ID, CERT_TRACE_ID_03, CERT_RUN_ID
# env vars to keep the contract explicit.
#
# Exit code 0 = all 10 labs pass. Anything else = at least one lab
# incomplete.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

red()    { printf "\033[31m%s\033[0m" "$*"; }
green()  { printf "\033[32m%s\033[0m" "$*"; }
yellow() { printf "\033[33m%s\033[0m" "$*"; }

results=()
passed=0
failed=0
warned=0

run_lab() {
    local n="$1"; shift
    printf "──── Lab %s ────\n" "${n}"
    if "${SCRIPT_DIR}/verify-${n}.sh" "$@"; then
        results+=("${n}:PASS")
        passed=$((passed + 1))
    else
        results+=("${n}:FAIL")
        failed=$((failed + 1))
    fi
    echo
}

# Defaults: each lab can be skipped if its required arg is unset
[[ -n "${CERT_TRACE_ID:-}" ]]    && run_lab 01 "${CERT_TRACE_ID}"    || { results+=("01:SKIP"); warned=$((warned + 1)); echo "── Lab 01 skipped (set CERT_TRACE_ID) ──"; echo; }
[[ -n "${CERT_TRACE_ID:-}" ]]    && run_lab 02 "${CERT_TRACE_ID}"    || { results+=("02:SKIP"); warned=$((warned + 1)); echo "── Lab 02 skipped (set CERT_TRACE_ID) ──"; echo; }
[[ -n "${CERT_TRACE_ID_03:-}" ]] && run_lab 03 "${CERT_TRACE_ID_03}" || { results+=("03:SKIP"); warned=$((warned + 1)); echo "── Lab 03 skipped (set CERT_TRACE_ID_03 — must be a slow-SQL trace) ──"; echo; }
run_lab 04
run_lab 05
run_lab 06
run_lab 07
run_lab 08
[[ -n "${CERT_RUN_ID:-}" ]]      && run_lab 09 "${CERT_RUN_ID}"      || { results+=("09:SKIP"); warned=$((warned + 1)); echo "── Lab 09 skipped (set CERT_RUN_ID) ──"; echo; }
run_lab 10

echo
echo "════════════════════════════════════════════"
echo "  Workshop Passport — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "════════════════════════════════════════════"
for r in "${results[@]}"; do
    n=${r%:*}
    s=${r##*:}
    case "${s}" in
        PASS) printf "  %s  Lab %s\n" "$(green '✓')" "${n}" ;;
        FAIL) printf "  %s  Lab %s\n" "$(red '✗')" "${n}" ;;
        SKIP) printf "  %s  Lab %s (skipped)\n" "$(yellow '·')" "${n}" ;;
    esac
done
echo "────────────────────────────────────────────"
printf "  Passed:  %d\n" "${passed}"
printf "  Failed:  %d\n" "${failed}"
printf "  Skipped: %d\n" "${warned}"
echo "════════════════════════════════════════════"

if [[ "${failed}" -gt 0 ]]; then
    exit 1
fi
if [[ "${passed}" -eq 10 ]]; then
    green "🎓 GRADUATED"; printf " — every lab passed.\n"
    exit 0
fi
yellow "INCOMPLETE"; printf " — pass all 10 to graduate.\n"
exit 0
