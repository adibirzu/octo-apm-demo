#!/usr/bin/env bash
# Dry-run every deploy script in sequence and report what would happen.
# Catches bit-rot in the deploy tree before an operator hits it on a
# real tenancy.
#
# Categories:
#   syntax    — bash -n on every shell script
#   help      — every script accepts --help / -h or echoes usage
#   pre-flight — required env vars surface as clear errors
#   yaml      — every plain YAML manifest parses cleanly
#   helm      — Helm charts lint and render into valid YAML
#   terraform — `terraform fmt -check` + root stack validate
#   compose   — docker-compose config validates without container pulls
#   docs      — mkdocs build --strict
#
# Exit codes:
#   0 = every category passed
#   1 = at least one category failed (full report still printed)
#
# Usage:
#   ./deploy/verify.sh

set -uo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

case "${1:-}" in
    -h|--help)
        show_usage
        exit 0
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

red()    { printf "\033[31m%s\033[0m" "$*"; }
green()  { printf "\033[32m%s\033[0m" "$*"; }
yellow() { printf "\033[33m%s\033[0m" "$*"; }

errors=0
warnings=0

section() {
    echo
    printf "── %s ──────────────────────────────────────────────\n" "$1"
}

ok()   { green "  PASS  "; echo " $*"; }
warn() { yellow "  WARN  "; echo " $*"; warnings=$((warnings + 1)); }
fail() { red   "  FAIL  "; echo " $*"; errors=$((errors + 1)); }

# ── Shell syntax ──────────────────────────────────────────────────────
section "Shell syntax (bash -n)"
while IFS= read -r script; do
    if bash -n "${script}" 2>/dev/null; then
        ok "${script#${REPO_ROOT}/}"
    else
        fail "${script#${REPO_ROOT}/}"
        bash -n "${script}" 2>&1 | sed 's/^/         /'
    fi
done < <(find "${REPO_ROOT}/deploy" -type f -name "*.sh")

# ── Help surfaces ──────────────────────────────────────────────────────
section "Script help"
help_report="$(mktemp)"
python3 - "${REPO_ROOT}" >"${help_report}" <<'PY'
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
failed = False
for script in sorted((root / "deploy").rglob("*.sh")):
    rel = script.relative_to(root)
    try:
        result = subprocess.run(
            ["bash", str(script), "--help"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"FAIL\t{rel}\ttimed out after 5s")
        failed = True
        continue

    if result.returncode == 0 and "Usage:" in result.stdout:
        print(f"PASS\t{rel}")
        continue

    first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else "<no output>"
    print(f"FAIL\t{rel}\trc={result.returncode}; {first_line}")
    failed = True

sys.exit(1 if failed else 0)
PY
while IFS=$'\t' read -r status rel detail; do
    case "${status}" in
        PASS) ok "${rel} --help" ;;
        FAIL)
            fail "${rel} --help"
            [[ -z "${detail:-}" ]] || printf '         %s\n' "${detail}"
            ;;
    esac
done < "${help_report}"
rm -f "${help_report}"

# ── Resource Manager stack package ────────────────────────────────────
section "Resource Manager stack package"
rm_package_log="$(mktemp)"
if bash "${REPO_ROOT}/deploy/resource-manager/stack-package.sh" >"${rm_package_log}" 2>&1; then
    ok "deploy/resource-manager package builds"
else
    fail "deploy/resource-manager package builds"
    sed 's/^/         /' "${rm_package_log}" | head -20
fi
rm -f "${rm_package_log}"

rm_stack_zip="${REPO_ROOT}/deploy/resource-manager/build/octo-stack.zip"
if [[ -f "${rm_stack_zip}" ]] && unzip -tq "${rm_stack_zip}" >/dev/null 2>&1; then
    ok "deploy/resource-manager/build/octo-stack.zip is a valid zip"
else
    fail "deploy/resource-manager/build/octo-stack.zip is a valid zip"
fi

if command -v terraform >/dev/null 2>&1 && [[ -f "${rm_stack_zip}" ]]; then
    rm_stack_tmp="$(mktemp -d)"
    rm_stack_init_log="$(mktemp)"
    rm_stack_validate_log="$(mktemp)"
    if unzip -q "${rm_stack_zip}" -d "${rm_stack_tmp}" && \
        terraform -chdir="${rm_stack_tmp}" init -backend=false -input=false -no-color >"${rm_stack_init_log}" 2>&1 && \
        terraform -chdir="${rm_stack_tmp}" validate -no-color >"${rm_stack_validate_log}" 2>&1; then
        ok "deploy/resource-manager package terraform validate"
    else
        fail "deploy/resource-manager package terraform validate"
        sed 's/^/         /' "${rm_stack_init_log}" | tail -20
        sed 's/^/         /' "${rm_stack_validate_log}" | tail -20
    fi
    rm -rf "${rm_stack_tmp}"
    rm -f "${rm_stack_init_log}" "${rm_stack_validate_log}"
else
    warn "terraform not installed — skipped Resource Manager package validate"
fi

# ── YAML ──────────────────────────────────────────────────────────────
section "YAML manifests"
while IFS= read -r yml; do
    if python3 -c "import yaml,sys; list(yaml.safe_load_all(open(sys.argv[1])))" "${yml}" 2>/dev/null; then
        ok "${yml#${REPO_ROOT}/}"
    else
        # docker-compose-unified uses ${VAR} interpolation that PyYAML can
        # parse but `docker-compose config` will warn about — accept here.
        fail "${yml#${REPO_ROOT}/}"
        python3 -c "import yaml,sys; list(yaml.safe_load_all(open(sys.argv[1])))" "${yml}" 2>&1 | sed 's/^/         /' | head -5
    fi
done < <(
    find "${REPO_ROOT}/deploy" -type f \( -name "*.yaml" -o -name "*.yml" \) \
        -not -path "*/.venv/*" \
        -not -path "${REPO_ROOT}/deploy/helm/*/templates/*"
)

# ── Helm charts ───────────────────────────────────────────────────────
section "Helm charts"
if command -v helm >/dev/null 2>&1; then
    helm_render="$(mktemp)"
    helm_render_err="$(mktemp)"
    helm_lint_out="$(mktemp)"
    helm_secrets_render="$(mktemp)"
    helm_secrets_err="$(mktemp)"
    helm_missing_err="$(mktemp)"
    if helm template octo-apm-demo "${REPO_ROOT}/deploy/helm/octo-apm-demo" \
            --namespace octo-drone-shop \
            --set namespaces.create=false \
            --set global.dnsDomain=verify.example.invalid \
            --set global.image.tenancy=verify-placeholder \
            --set global.image.tag=verify \
            --set ingress.tls.secretName=verify-tls \
            >"${helm_render}" 2>"${helm_render_err}" && \
        python3 -c "import yaml,sys; list(yaml.safe_load_all(open(sys.argv[1])))" "${helm_render}" 2>/dev/null; then
        ok "deploy/helm/octo-apm-demo renders via helm template"
    else
        fail "deploy/helm/octo-apm-demo renders via helm template"
        sed 's/^/         /' "${helm_render_err}" | head -10
    fi
    if [[ -s "${helm_render}" ]]; then
        if command -v kubectl >/dev/null 2>&1; then
            if kubectl apply --dry-run=client --validate=false -f "${helm_render}" >/dev/null 2>&1; then
                ok "deploy/helm/octo-apm-demo passes kubectl client dry-run"
            else
                fail "deploy/helm/octo-apm-demo passes kubectl client dry-run"
                kubectl apply --dry-run=client --validate=false -f "${helm_render}" 2>&1 | sed 's/^/         /' | head -10
            fi
        else
            warn "kubectl not installed — skipped Helm client dry-run"
        fi
    fi

    if helm template octo-apm-demo "${REPO_ROOT}/deploy/helm/octo-apm-demo" \
            --namespace octo-drone-shop \
            --set namespaces.create=true \
            --set global.dnsDomain=verify.example.invalid \
            --set global.image.tenancy=verify-placeholder \
            --set global.image.tag=20260424230757 \
            --set ingress.tls.enabled=false \
            --set secrets.create=true \
            --set secrets.data.atp.dsn=octoatp_low \
            --set secrets.data.atp.username=ADMIN \
            --set secrets.data.atp.password=verify-db-password \
            --set secrets.data.atp.walletPassword=verify-wallet-password \
            --set secrets.data.auth.tokenSecret=verify-token-secret \
            --set secrets.data.auth.internalServiceKey=verify-internal-service-key \
            --set secrets.data.auth.appSecretKey=verify-app-secret-key \
            --set secrets.data.auth.bootstrapAdminPassword=verify-admin-password \
            --set secrets.data.ociConfig.compartmentId=ocid1.compartment.oc1..verify \
            --set-string secrets.atpWallet=verify-wallet-bytes \
            >"${helm_secrets_render}" 2>"${helm_secrets_err}" && \
        python3 -c "import yaml,sys; list(yaml.safe_load_all(open(sys.argv[1])))" "${helm_secrets_render}" 2>/dev/null; then
        ok "deploy/helm/octo-apm-demo renders chart-managed secrets"
    else
        fail "deploy/helm/octo-apm-demo renders chart-managed secrets"
        sed 's/^/         /' "${helm_secrets_err}" | head -10
    fi

    if helm template octo-apm-demo "${REPO_ROOT}/deploy/helm/octo-apm-demo" \
            --namespace octo-drone-shop \
            --set global.image.tenancy=verify-placeholder \
            --set secrets.create=true \
            >/dev/null 2>"${helm_missing_err}"; then
        fail "deploy/helm/octo-apm-demo rejects incomplete chart-managed secrets"
    elif grep -q "secrets.data.atp.dsn is required when secrets.create=true" "${helm_missing_err}"; then
        ok "deploy/helm/octo-apm-demo rejects incomplete chart-managed secrets"
    else
        fail "deploy/helm/octo-apm-demo rejects incomplete chart-managed secrets"
        sed 's/^/         /' "${helm_missing_err}" | head -10
    fi

    if helm lint "${REPO_ROOT}/deploy/helm/octo-apm-demo" \
            --set namespaces.create=false \
            --set global.dnsDomain=verify.example.invalid \
            --set global.image.tenancy=verify-placeholder \
            --set global.image.tag=verify \
            --set ingress.tls.secretName=verify-tls \
            >"${helm_lint_out}" 2>&1; then
        ok "deploy/helm/octo-apm-demo passes helm lint"
    else
        fail "deploy/helm/octo-apm-demo passes helm lint"
        sed 's/^/         /' "${helm_lint_out}" | head -10
    fi

    rm -f "${helm_render}" "${helm_render_err}" "${helm_lint_out}" \
        "${helm_secrets_render}" "${helm_secrets_err}" "${helm_missing_err}"
else
    warn "helm not installed — skipped"
fi

# ── JSON manifests ────────────────────────────────────────────────────
section "JSON manifests"
while IFS= read -r jsf; do
    if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "${jsf}" 2>/dev/null; then
        ok "${jsf#${REPO_ROOT}/}"
    else
        fail "${jsf#${REPO_ROOT}/}"
    fi
done < <(find "${REPO_ROOT}/deploy" "${REPO_ROOT}/tools" -type f -name "*.json" \
            -not -path "*/.venv/*" -not -path "*/node_modules/*" -not -path "*/build/*" 2>/dev/null)

# ── Terraform fmt + validate ──────────────────────────────────────────
section "Terraform fmt + validate"
if command -v terraform >/dev/null 2>&1; then
    if terraform -chdir="${REPO_ROOT}/deploy/terraform" fmt -check -recursive >/dev/null 2>&1; then
        ok "deploy/terraform/* fmt clean"
    else
        warn "deploy/terraform/* fmt drift (run terraform fmt -recursive)"
    fi
    if (cd "${REPO_ROOT}/deploy/terraform" && terraform validate >/dev/null 2>&1); then
        ok "deploy/terraform validate"
    else
        fail "deploy/terraform validate"
        (cd "${REPO_ROOT}/deploy/terraform" && terraform validate 2>&1 | tail -20 | sed 's/^/         /')
    fi
    rm_tf_files=()
    while IFS= read -r tf_file; do
        rm_tf_files+=("${tf_file}")
    done < <(find "${REPO_ROOT}/deploy/resource-manager" \
        -path "${REPO_ROOT}/deploy/resource-manager/build" -prune -o \
        -type f -name "*.tf" -print)
    if [[ "${#rm_tf_files[@]}" -gt 0 ]] && terraform fmt -check "${rm_tf_files[@]}" >/dev/null 2>&1; then
        ok "deploy/resource-manager/* fmt clean"
    else
        warn "deploy/resource-manager/* fmt drift"
    fi
else
    warn "terraform not installed — skipped"
fi

# ── Compose config ────────────────────────────────────────────────────
section "Docker compose config"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    # Per-run random tokens so verify.sh never commits literal secrets and
    # an operator accidentally pasting this script into a shell session
    # cannot leak a reusable value.
    rand_token() { openssl rand -hex 16 2>/dev/null || python3 -c 'import secrets;print(secrets.token_hex(16))'; }
    compose_env=$(cat <<EOF
OCIR_REGION=${OCIR_REGION:-eu-frankfurt-1}
OCIR_TENANCY=verify-placeholder
DNS_DOMAIN=verify.example.invalid
INTERNAL_SERVICE_KEY=$(rand_token)
AUTH_TOKEN_SECRET=$(rand_token)
APP_SECRET_KEY=$(rand_token)
BOOTSTRAP_ADMIN_PASSWORD=$(rand_token)
ORACLE_DSN=verify-dsn
ORACLE_PASSWORD=$(rand_token)
ORACLE_WALLET_PASSWORD=$(rand_token)
EOF
)
    if docker compose -f "${REPO_ROOT}/deploy/vm/docker-compose-unified.yml" \
            --env-file <(echo "${compose_env}") \
            config >/dev/null 2>&1; then
        ok "deploy/vm/docker-compose-unified.yml"
    else
        fail "deploy/vm/docker-compose-unified.yml"
    fi
else
    warn "docker compose not installed — skipped"
fi

# ── Pre-flight error messages ─────────────────────────────────────────
section "Pre-flight required-var enforcement"
preflight_out=$(env -i PATH="${PATH}" bash "${REPO_ROOT}/deploy/pre-flight-check.sh" 2>&1 || true)
for var in DNS_DOMAIN OCIR_REPO K8S_NAMESPACE; do
    if echo "${preflight_out}" | grep -q "${var}"; then
        ok "pre-flight surfaces missing ${var}"
    else
        fail "pre-flight does NOT surface missing ${var}"
    fi
done

# ── MkDocs strict ─────────────────────────────────────────────────────
section "MkDocs strict build"
if command -v mkdocs >/dev/null 2>&1; then
    if (cd "${REPO_ROOT}" && mkdocs build --strict >/dev/null 2>&1); then
        ok "mkdocs --strict"
    else
        fail "mkdocs --strict"
        (cd "${REPO_ROOT}" && mkdocs build --strict 2>&1 | grep -E "WARNING|ERROR" | head -5 | sed 's/^/         /')
    fi
else
    warn "mkdocs not installed — skipped"
fi

# ── Python tests (shop, crm, tools) ───────────────────────────────────
section "Python test suites"
if (cd "${REPO_ROOT}" && python3 -m pytest -q tests/test_unified_deploy_surface.py >/dev/null 2>&1); then
    ok "root unified deploy pytest"
else
    fail "root unified deploy pytest"
    (cd "${REPO_ROOT}" && python3 -m pytest -q tests/test_unified_deploy_surface.py 2>&1 | tail -20 | sed 's/^/         /')
fi

if (cd "${REPO_ROOT}" && python3 -m pytest -q deploy/wizard/tests/test_plan.py >/dev/null 2>&1); then
    ok "deploy/wizard pytest"
else
    fail "deploy/wizard pytest"
    (cd "${REPO_ROOT}" && python3 -m pytest -q deploy/wizard/tests/test_plan.py 2>&1 | tail -20 | sed 's/^/         /')
fi

for testdir in services/load-control shop crm tools/traffic-generator; do
    if [[ -d "${REPO_ROOT}/${testdir}" ]] && find "${REPO_ROOT}/${testdir}" -name "test_*.py" -print -quit | grep -q .; then
        if (cd "${REPO_ROOT}/${testdir}" && python -m pytest -q --no-header 2>&1 | tail -1 | grep -q "passed"); then
            ok "${testdir} pytest"
        else
            warn "${testdir} pytest had failures or was not runnable here"
        fi
    fi
done

# ── Template import smoke (catches Starlette signature break KB-448) ──
section "Template rendering smoke"
_template_smoke() {
    local svc="$1"
    (
        cd "${REPO_ROOT}/${svc}" || return 1
        APP_ENV=test APP_SECRET_KEY=smoke BOOTSTRAP_ADMIN_PASSWORD=smoke \
        python - >/dev/null 2>/tmp/_octo_tpl_smoke.$$ <<PYEOF
import sys
from fastapi.testclient import TestClient
from server.main import app
client = TestClient(app)
# We only check HTML rendering here (KB-448 canary). Readiness can fail
# locally because ATP isn't configured in test env — that's not what we're
# validating. A 500 on "/" means the TemplateResponse signature is wrong.
html = client.get("/")
if html.status_code < 500:
    sys.stderr.write("SMOKE_OK\n")
    sys.exit(0)
sys.stderr.write(f"SMOKE_FAIL html={html.status_code} body={html.text[:200]}\n")
sys.exit(1)
PYEOF
        rc=$?
        grep -oE 'SMOKE_(OK|FAIL[^[:cntrl:]]*)' "/tmp/_octo_tpl_smoke.$$" 2>/dev/null | head -1
        rm -f "/tmp/_octo_tpl_smoke.$$"
        return $rc
    )
}

if python -c "import fastapi" >/dev/null 2>&1; then
    for svc in shop crm; do
        if [[ -d "${REPO_ROOT}/${svc}/server" ]]; then
            out=$(_template_smoke "${svc}")
            if [[ "${out}" == "SMOKE_OK" ]]; then
                ok "${svc} template smoke (/ → non-500)"
            else
                fail "${svc} template smoke: ${out:-no output}"
            fi
        fi
    done
else
    warn "fastapi not installed — template smoke skipped"
fi

# ── Summary ───────────────────────────────────────────────────────────
echo
if [[ "${errors}" -gt 0 ]]; then
    red "VERIFY FAILED"; printf " — %d error(s), %d warning(s)\n" "${errors}" "${warnings}"
    exit 1
fi

green "VERIFY PASSED"; printf " — %d warning(s)\n" "${warnings}"
exit 0
