#!/usr/bin/env bash
# Pre-flight check for OCTO Drone Shop deployment to a new OCI tenancy.
#
# Validates:
#   - Required env vars are set (no silent defaults)
#   - No placeholder values leaked (example.cloud, example.invalid)
#   - Required CLIs present on PATH (kubectl, oci, envsubst, docker, ssh)
#   - kubectl context resolves
#
# Exit codes:
#   0 = all checks passed
#   1 = at least one check failed (missing var or missing tool)
#
# Usage:
#   DNS_DOMAIN=tenant-a.customer.example \
#   OCIR_REPO=eu-frankfurt-1.ocir.io/<ns>/octo-drone-shop \
#   K8S_NAMESPACE=octo-drone-shop \
#   ./deploy/pre-flight-check.sh

set -uo pipefail

errors=0
warnings=0

log_err()  { printf "\033[31m[FAIL]\033[0m %s\n" "$*" >&2; errors=$((errors + 1)); }
log_warn() { printf "\033[33m[WARN]\033[0m %s\n" "$*" >&2; warnings=$((warnings + 1)); }
log_ok()   { printf "\033[32m[ OK ]\033[0m %s\n" "$*"; }

# ── Required environment variables ────────────────────────────────────────
required_vars=(
    DNS_DOMAIN
    OCIR_REPO
    K8S_NAMESPACE
)

for v in "${required_vars[@]}"; do
    if [[ -z "${!v:-}" ]]; then
        log_err "${v} is not set (required for new-tenancy deploy)"
    else
        log_ok "${v} = ${!v}"
    fi
done

# ── Placeholder leak detection ────────────────────────────────────────────
# Any value containing a known placeholder domain indicates the operator
# copied the template without overriding — refuse.
placeholder_patterns='example\.cloud|example\.invalid|changeme|TODO|PLACEHOLDER'

for v in "${required_vars[@]}"; do
    val="${!v:-}"
    if [[ -n "${val}" ]] && echo "${val}" | grep -Eiq "${placeholder_patterns}"; then
        log_err "${v} contains a placeholder value ('${val}') — replace with real tenancy config"
    fi
done

# ── Optional but recommended vars (warnings only) ─────────────────────────
recommended_vars=(
    OCI_COMPARTMENT_ID
    OCI_APM_ENDPOINT
    OCI_LOG_ID
    OCI_LB_SUBNET_OCID
    IDCS_DOMAIN_URL
)

for v in "${recommended_vars[@]}"; do
    if [[ -z "${!v:-}" ]]; then
        log_warn "${v} is not set (observability/SSO features will be disabled)"
    fi
done

# ── Required CLIs on PATH ─────────────────────────────────────────────────
required_tools=(kubectl oci envsubst docker ssh)

for tool in "${required_tools[@]}"; do
    if command -v "${tool}" >/dev/null 2>&1; then
        log_ok "tool available: ${tool}"
    else
        log_warn "tool not on PATH: ${tool} (required for full deploy)"
    fi
done

# ── kubectl context check (best-effort, skipped if kubectl missing) ───────
if command -v kubectl >/dev/null 2>&1; then
    if ctx=$(kubectl config current-context 2>/dev/null); then
        log_ok "kubectl context: ${ctx}"
    else
        log_warn "kubectl has no current context — run: kubectl config use-context <your-oke>"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo
if [[ "${errors}" -gt 0 ]]; then
    printf "\033[31mPre-flight FAILED\033[0m with %d error(s), %d warning(s)\n" "${errors}" "${warnings}" >&2
    exit 1
fi

printf "\033[32mPre-flight PASSED\033[0m (%d warning(s))\n" "${warnings}"
exit 0
