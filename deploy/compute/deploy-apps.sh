#!/usr/bin/env bash
# Promote or reconcile OCTO apps on private Compute instances through OCI Run Command.
#
# The script is dry-run by default. With --apply it creates one OCI Run Command
# per selected private instance, updates only non-secret runtime values, runs
# the instance-side pre-flight, restarts the app service, and checks /ready.
#
# Usage:
#   ./deploy/compute/deploy-apps.sh --outputs-json outputs.json --role all --image-tag 20260505
#   ./deploy/compute/deploy-apps.sh --profile <OCI_PROFILE> --role shop --shop-image iad.ocir.io/ns/octo-drone-shop:20260505 --apply
#   ./deploy/compute/deploy-apps.sh --outputs-json outputs.json --compartment-id ocid1.compartment.oc1..xxxx --repo-ref main --apply
#   ./deploy/compute/deploy-apps.sh --shop-instance-id ocid1.instance.oc1..shop --crm-instance-id ocid1.instance.oc1..crm --compartment-id ocid1.compartment.oc1..xxxx --apply

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
OUTPUTS_JSON_FILE=""
OCI_PROFILE_VALUE="${OCI_PROFILE:-${TF_VAR_oci_profile:-}}"
COMPARTMENT_ID="${COMPARTMENT_ID:-${TF_VAR_compartment_id:-}}"
ROLE="all"
IMAGE_TAG=""
SHOP_IMAGE=""
CRM_IMAGE=""
REPO_REF=""
APP_IMAGE_BUILD_ENABLED=""
APP_IMAGE_PULL_POLICY=""
SHOP_INSTANCE_ID=""
CRM_INSTANCE_ID=""
APPLY=false
WAIT_FOR_COMPLETION=true
TIMEOUT_SECONDS=1800
WAIT_TIMEOUT_SECONDS=2400
POLL_INTERVAL_SECONDS=15

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_usage
            exit 0
            ;;
        --terraform-dir)
            TERRAFORM_DIR="${2:?--terraform-dir requires a directory path}"
            shift 2
            ;;
        --outputs-json)
            OUTPUTS_JSON_FILE="${2:?--outputs-json requires a file path}"
            shift 2
            ;;
        --profile)
            OCI_PROFILE_VALUE="${2:?--profile requires an OCI profile name}"
            shift 2
            ;;
        --compartment-id)
            COMPARTMENT_ID="${2:?--compartment-id requires a compartment OCID}"
            shift 2
            ;;
        --role)
            ROLE="${2:?--role requires shop, crm, or all}"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="${2:?--image-tag requires a tag}"
            shift 2
            ;;
        --shop-image)
            SHOP_IMAGE="${2:?--shop-image requires an image reference}"
            shift 2
            ;;
        --crm-image)
            CRM_IMAGE="${2:?--crm-image requires an image reference}"
            shift 2
            ;;
        --repo-ref)
            REPO_REF="${2:?--repo-ref requires a branch, tag, or commit}"
            shift 2
            ;;
        --app-image-build-enabled)
            APP_IMAGE_BUILD_ENABLED="${2:?--app-image-build-enabled requires true or false}"
            shift 2
            ;;
        --app-image-pull-policy)
            APP_IMAGE_PULL_POLICY="${2:?--app-image-pull-policy requires always, if-not-present, or never}"
            shift 2
            ;;
        --shop-instance-id)
            SHOP_INSTANCE_ID="${2:?--shop-instance-id requires an instance OCID}"
            shift 2
            ;;
        --crm-instance-id)
            CRM_INSTANCE_ID="${2:?--crm-instance-id requires an instance OCID}"
            shift 2
            ;;
        --timeout)
            TIMEOUT_SECONDS="${2:?--timeout requires seconds}"
            shift 2
            ;;
        --wait-timeout)
            WAIT_TIMEOUT_SECONDS="${2:?--wait-timeout requires seconds}"
            shift 2
            ;;
        --poll-interval)
            POLL_INTERVAL_SECONDS="${2:?--poll-interval requires seconds}"
            shift 2
            ;;
        --apply)
            APPLY=true
            shift
            ;;
        --dry-run)
            APPLY=false
            shift
            ;;
        --no-wait)
            WAIT_FOR_COMPLETION=false
            shift
            ;;
        *)
            printf 'Unknown option: %s\n\n' "$1" >&2
            show_usage >&2
            exit 2
            ;;
    esac
done

case "${ROLE}" in
    shop|crm|all) ;;
    *)
        printf -- '--role must be shop, crm, or all\n' >&2
        exit 2
        ;;
esac

case "${APP_IMAGE_PULL_POLICY}" in
    ""|always|if-not-present|never) ;;
    *)
        printf -- '--app-image-pull-policy must be always, if-not-present, or never\n' >&2
        exit 2
        ;;
esac

case "${APP_IMAGE_BUILD_ENABLED}" in
    ""|true|false) ;;
    *)
        printf -- '--app-image-build-enabled must be true or false\n' >&2
        exit 2
        ;;
esac

for numeric in TIMEOUT_SECONDS WAIT_TIMEOUT_SECONDS POLL_INTERVAL_SECONDS; do
    if ! [[ "${!numeric}" =~ ^[0-9]+$ ]]; then
        printf '%s must be a positive integer\n' "${numeric}" >&2
        exit 2
    fi
done

NEED_TERRAFORM_OUTPUTS=false
if [[ -z "${OUTPUTS_JSON_FILE}" ]]; then
    if [[ -z "${COMPARTMENT_ID}" ]]; then
        NEED_TERRAFORM_OUTPUTS=true
    fi
    case "${ROLE}" in
        all)
            if [[ -z "${SHOP_INSTANCE_ID}" || -z "${CRM_INSTANCE_ID}" ]]; then
                NEED_TERRAFORM_OUTPUTS=true
            fi
            ;;
        shop)
            [[ -z "${SHOP_INSTANCE_ID}" ]] && NEED_TERRAFORM_OUTPUTS=true
            ;;
        crm)
            [[ -z "${CRM_INSTANCE_ID}" ]] && NEED_TERRAFORM_OUTPUTS=true
            ;;
    esac
fi

if [[ "${NEED_TERRAFORM_OUTPUTS}" == "true" ]]; then
    if [[ ! -d "${TERRAFORM_DIR}" ]]; then
        printf 'Terraform directory does not exist: %s\n' "${TERRAFORM_DIR}" >&2
        exit 2
    fi
    if ! command -v terraform >/dev/null 2>&1; then
        printf 'terraform is required unless --outputs-json or explicit instance OCIDs are supplied\n' >&2
        exit 2
    fi
fi

if [[ -n "${OUTPUTS_JSON_FILE}" && ! -r "${OUTPUTS_JSON_FILE}" ]]; then
    printf 'Outputs JSON file is not readable: %s\n' "${OUTPUTS_JSON_FILE}" >&2
    exit 2
fi

if [[ "${APPLY}" == "true" ]] && ! command -v oci >/dev/null 2>&1; then
    printf 'oci CLI is required when --apply is supplied\n' >&2
    exit 2
fi

tmp_dir="$(mktemp -d)"
cleanup() {
    rm -rf "${tmp_dir}"
}
trap cleanup EXIT

outputs_json="${tmp_dir}/outputs.json"
if [[ -n "${OUTPUTS_JSON_FILE}" ]]; then
    cp "${OUTPUTS_JSON_FILE}" "${outputs_json}"
elif [[ "${NEED_TERRAFORM_OUTPUTS}" == "true" ]]; then
    terraform -chdir="${TERRAFORM_DIR}" output -json >"${outputs_json}"
else
    printf '{}\n' >"${outputs_json}"
fi

targets_json="${tmp_dir}/targets.json"
python3 - "${outputs_json}" "${COMPARTMENT_ID}" "${ROLE}" "${SHOP_INSTANCE_ID}" "${CRM_INSTANCE_ID}" >"${targets_json}" <<'PY'
import json
import sys

outputs_path, compartment_id, requested_role, shop_instance_id, crm_instance_id = sys.argv[1:]
with open(outputs_path, encoding="utf-8") as handle:
    outputs = json.load(handle)


def output_value(name, default=None):
    item = outputs.get(name)
    if item is None:
        return default
    if isinstance(item, dict) and "value" in item and (
        "type" in item or "sensitive" in item or "description" in item
    ):
        return item.get("value", default)
    return item


instance_ids = output_value("instance_ids", {}) or {}
if shop_instance_id:
    instance_ids = {**instance_ids, "shop": shop_instance_id}
if crm_instance_id:
    instance_ids = {**instance_ids, "crm": crm_instance_id}

effective_compartment_id = compartment_id or output_value("deployment_compartment_id", "")
roles = ["shop", "crm"] if requested_role == "all" else [requested_role]
errors = []
for role in roles:
    if not instance_ids.get(role):
        errors.append(f"missing {role} instance OCID; use a stack with instance_ids output or pass --{role}-instance-id")
if not effective_compartment_id:
    errors.append("missing compartment OCID; pass --compartment-id or use deployment_compartment_id output")
if errors:
    raise SystemExit("; ".join(errors))

print(json.dumps({
    "compartment_id": effective_compartment_id,
    "roles": [{"role": role, "instance_id": instance_ids[role]} for role in roles],
}, indent=2, sort_keys=True))
PY

COMPARTMENT_ID="$(python3 - "${targets_json}" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["compartment_id"])
PY
)"

oci_cli() {
    if [[ -n "${OCI_PROFILE_VALUE}" ]]; then
        oci --profile "${OCI_PROFILE_VALUE}" "$@"
    else
        oci "$@"
    fi
}

render_remote_script() {
    local role="$1"
    local app_image="$2"
    local out_file="$3"

    python3 - "${role}" "${app_image}" "${IMAGE_TAG}" "${REPO_REF}" "${APP_IMAGE_PULL_POLICY}" "${APP_IMAGE_BUILD_ENABLED}" >"${out_file}" <<'PY'
import shlex
import sys

role, app_image, image_tag, repo_ref, pull_policy, build_enabled = sys.argv[1:]


def sq(value: str) -> str:
    return shlex.quote(value)


print("#!/usr/bin/env bash")
print("set -euo pipefail")
print(f"ROLE={sq(role)}")
print(f"APP_IMAGE_OVERRIDE={sq(app_image)}")
print(f"IMAGE_TAG={sq(image_tag)}")
print(f"REPO_REF={sq(repo_ref)}")
print(f"APP_IMAGE_PULL_POLICY_OVERRIDE={sq(pull_policy)}")
print(f"APP_IMAGE_BUILD_ENABLED_OVERRIDE={sq(build_enabled)}")
print(r'''
ENV_FILE="${ENV_FILE:-/opt/octo/runtime.env}"
REPO_DIR="${REPO_DIR:-/opt/octo/repo}"

log() {
    printf '[octo-deploy:%s] %s\n' "${ROLE}" "$*"
}

fail() {
    printf '[octo-deploy:%s] ERROR %s\n' "${ROLE}" "$*" >&2
    exit 1
}

set_env_var() {
    local name="$1"
    local value="$2"
    python3 - "${ENV_FILE}" "${name}" "${value}" <<'PYENV'
import pathlib
import shlex
import sys

path = pathlib.Path(sys.argv[1])
name = sys.argv[2]
value = sys.argv[3]
new_line = f"{name}={shlex.quote(value)}"
lines = path.read_text(encoding="utf-8").splitlines()
updated = False
rendered = []
for line in lines:
    if line.startswith(f"{name}="):
        rendered.append(new_line)
        updated = True
    else:
        rendered.append(line)
if not updated:
    rendered.append(new_line)
tmp = path.with_name(f"{path.name}.tmp")
tmp.write_text("\n".join(rendered) + "\n", encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(path)
PYENV
}

retag_image() {
    local image="$1"
    local tag="$2"
    if [[ -z "${image}" ]]; then
        fail "APP_IMAGE is empty and --image-tag cannot infer an image repository"
    fi
    if [[ "${image}" == *@sha256:* ]]; then
        fail "APP_IMAGE uses a digest; pass --${ROLE}-image instead of --image-tag"
    fi
    local last_segment="${image##*/}"
    if [[ "${last_segment}" == *:* ]]; then
        printf '%s:%s\n' "${image%:*}" "${tag}"
    else
        printf '%s:%s\n' "${image}" "${tag}"
    fi
}

if [[ "$(id -u)" -ne 0 ]]; then
    fail "OCI Run Command must run as root; check Oracle Cloud Agent privileges"
fi
if [[ ! -f "${ENV_FILE}" ]]; then
    fail "missing ${ENV_FILE}; render/copy runtime.env before app promotion"
fi

# shellcheck disable=SC1090
set -a; . "${ENV_FILE}"; set +a

if [[ "${OCTO_COMPUTE_ROLE:-}" != "${ROLE}" ]]; then
    fail "${ENV_FILE} has OCTO_COMPUTE_ROLE=${OCTO_COMPUTE_ROLE:-<empty>}, expected ${ROLE}"
fi

if [[ -n "${REPO_REF}" ]]; then
    if [[ -d "${REPO_DIR}/.git" ]]; then
        log "updating repository checkout to ${REPO_REF}"
        git -C "${REPO_DIR}" fetch --depth 1 origin "${REPO_REF}" || git -C "${REPO_DIR}" fetch --tags --prune origin
        git -C "${REPO_DIR}" checkout --force FETCH_HEAD || \
            git -C "${REPO_DIR}" checkout --force "${REPO_REF}" || \
            git -C "${REPO_DIR}" checkout --force "origin/${REPO_REF}"
    else
        log "repository checkout not found at ${REPO_DIR}; skipping repo update"
    fi
fi

if [[ -d "${REPO_DIR}/deploy/compute" ]]; then
    log "refreshing /opt/octo/deploy from repository checkout"
    cp -a "${REPO_DIR}/deploy/." /opt/octo/deploy/
    chmod 0755 /opt/octo/deploy/compute/install.sh
fi

if [[ -n "${APP_IMAGE_OVERRIDE}" ]]; then
    set_env_var APP_IMAGE "${APP_IMAGE_OVERRIDE}"
    APP_IMAGE="${APP_IMAGE_OVERRIDE}"
elif [[ -n "${IMAGE_TAG}" ]]; then
    APP_IMAGE="$(retag_image "${APP_IMAGE:-}" "${IMAGE_TAG}")"
    set_env_var APP_IMAGE "${APP_IMAGE}"
fi

if [[ -n "${APP_IMAGE_PULL_POLICY_OVERRIDE}" ]]; then
    set_env_var APP_IMAGE_PULL_POLICY "${APP_IMAGE_PULL_POLICY_OVERRIDE}"
fi
if [[ -n "${APP_IMAGE_BUILD_ENABLED_OVERRIDE}" ]]; then
    set_env_var APP_IMAGE_BUILD_ENABLED "${APP_IMAGE_BUILD_ENABLED_OVERRIDE}"
fi

log "running app pre-flight"
/opt/octo/deploy/compute/install.sh --check
log "applying runtime configuration"
/opt/octo/deploy/compute/install.sh
log "restarting octo-compute.service"
systemctl restart octo-compute.service
systemctl is-active --quiet octo-compute.service

for attempt in $(seq 1 30); do
    if curl -fsS --max-time 10 http://127.0.0.1:8080/ready >/tmp/octo-ready.json; then
        log "local /ready passed"
        log "deployment finished"
        exit 0
    fi
    sleep 2
done

fail "local /ready did not pass after service restart"
''')
PY
    chmod 0600 "${out_file}"
}

render_payload() {
    local role="$1"
    local instance_id="$2"
    local script_file="$3"
    local payload_file="$4"

    python3 - "${role}" "${COMPARTMENT_ID}" "${instance_id}" "${script_file}" "${TIMEOUT_SECONDS}" >"${payload_file}" <<'PY'
import hashlib
import json
import pathlib
import sys

role, compartment_id, instance_id, script_path, timeout = sys.argv[1:]
script = pathlib.Path(script_path).read_text(encoding="utf-8")
payload = {
    "compartmentId": compartment_id,
    "displayName": f"octo-compute-{role}-app-deploy",
    "target": {"instanceId": instance_id},
    "content": {
        "source": {
            "sourceType": "TEXT",
            "text": script,
            "textSha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        },
        "output": {"outputType": "TEXT"},
    },
    "timeoutInSeconds": str(timeout),
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY
    chmod 0600 "${payload_file}"
}

json_field() {
    local file="$1"
    local expression="$2"
    python3 - "${file}" "${expression}" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
current = data
for part in sys.argv[2].split("."):
    if not part:
        continue
    current = current.get(part, {}) if isinstance(current, dict) else {}
print(current if current is not None else "")
PY
}

print_execution_output() {
    local execution_file="$1"
    python3 - "${execution_file}" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8")).get("data", {})
content = data.get("content") or {}
exit_code = content.get("exit-code", content.get("exitCode"))
message = content.get("message")
text = content.get("text")
if exit_code is not None:
    print(f"Run Command exit code: {exit_code}")
if message:
    print(message)
if text:
    print(text[-12000:])
PY
}

wait_for_command() {
    local role="$1"
    local instance_id="$2"
    local command_id="$3"
    local execution_file="${tmp_dir}/${role}.execution.json"
    local error_file="${tmp_dir}/${role}.execution.err"
    local start now state

    start="$(date +%s)"
    while true; do
        if oci_cli instance-agent command-execution get \
            --instance-id "${instance_id}" \
            --command-id "${command_id}" \
            --output json >"${execution_file}" 2>"${error_file}"; then
            state="$(json_field "${execution_file}" "data.lifecycle-state")"
            printf '%s Run Command state: %s\n' "${role}" "${state}"
            case "${state}" in
                SUCCEEDED)
                    print_execution_output "${execution_file}"
                    return 0
                    ;;
                FAILED|TIMED_OUT|CANCELED)
                    print_execution_output "${execution_file}"
                    return 1
                    ;;
            esac
        fi

        now="$(date +%s)"
        if (( now - start >= WAIT_TIMEOUT_SECONDS )); then
            printf '%s Run Command did not complete within %s seconds\n' "${role}" "${WAIT_TIMEOUT_SECONDS}" >&2
            if [[ -s "${error_file}" ]]; then
                sed 's/^/  /' "${error_file}" >&2
            fi
            return 1
        fi
        sleep "${POLL_INTERVAL_SECONDS}"
    done
}

if [[ "${APPLY}" != "true" ]]; then
    printf 'DRY RUN: no OCI Run Command resources will be created. Add --apply to execute.\n'
fi
printf 'Target compartment: %s\n' "${COMPARTMENT_ID}"
if [[ -n "${OCI_PROFILE_VALUE}" ]]; then
    printf 'OCI profile: %s\n' "${OCI_PROFILE_VALUE}"
fi

failed=0
while IFS=$'\t' read -r role instance_id; do
    [[ -z "${role}" ]] && continue
    case "${role}" in
        shop) app_image="${SHOP_IMAGE}" ;;
        crm) app_image="${CRM_IMAGE}" ;;
        *) printf 'Unexpected role from target resolver: %s\n' "${role}" >&2; exit 2 ;;
    esac

    script_file="${tmp_dir}/${role}.remote.sh"
    payload_file="${tmp_dir}/${role}.payload.json"
    create_file="${tmp_dir}/${role}.create.json"
    render_remote_script "${role}" "${app_image}" "${script_file}"
    render_payload "${role}" "${instance_id}" "${script_file}" "${payload_file}"

    printf '\nRole: %s\n' "${role}"
    printf 'Instance OCID: %s\n' "${instance_id}"
    if [[ -n "${app_image}" ]]; then
        printf 'Image override: %s\n' "${app_image}"
    elif [[ -n "${IMAGE_TAG}" ]]; then
        printf 'Image tag promotion: %s\n' "${IMAGE_TAG}"
    else
        printf 'Image override: unchanged\n'
    fi
    [[ -n "${REPO_REF}" ]] && printf 'Repo ref: %s\n' "${REPO_REF}"
    [[ -n "${APP_IMAGE_PULL_POLICY}" ]] && printf 'APP_IMAGE_PULL_POLICY: %s\n' "${APP_IMAGE_PULL_POLICY}"
    [[ -n "${APP_IMAGE_BUILD_ENABLED}" ]] && printf 'APP_IMAGE_BUILD_ENABLED: %s\n' "${APP_IMAGE_BUILD_ENABLED}"

    if [[ "${APPLY}" != "true" ]]; then
        printf 'Would create OCI Run Command: octo-compute-%s-app-deploy\n' "${role}"
        continue
    fi

    if ! oci_cli instance-agent command create --from-json "file://${payload_file}" --output json >"${create_file}"; then
        printf 'Failed to create OCI Run Command for %s\n' "${role}" >&2
        failed=1
        continue
    fi

    command_id="$(json_field "${create_file}" "data.id")"
    if [[ -z "${command_id}" ]]; then
        printf 'OCI Run Command create response for %s did not include a command OCID\n' "${role}" >&2
        failed=1
        continue
    fi
    printf 'Created Run Command for %s: %s\n' "${role}" "${command_id}"

    if [[ "${WAIT_FOR_COMPLETION}" == "true" ]]; then
        if ! wait_for_command "${role}" "${instance_id}" "${command_id}"; then
            failed=1
        fi
    else
        printf 'Not waiting for %s. Check later with: oci instance-agent command-execution get --instance-id %s --command-id %s\n' "${role}" "${instance_id}" "${command_id}"
    fi
done < <(python3 - "${targets_json}" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
for item in data["roles"]:
    print(f"{item['role']}\t{item['instance_id']}")
PY
)

if [[ "${failed}" -ne 0 ]]; then
    exit 1
fi
