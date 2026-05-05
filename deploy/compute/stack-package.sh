#!/usr/bin/env bash
# Package the two-instance Compute deployment as an OCI Resource Manager zip.
#
# Usage:
#   ./deploy/compute/stack-package.sh
#
# Output: deploy/compute/build/octo-compute-stack.zip

set -euo pipefail

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
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
OUT_ZIP="${BUILD_DIR}/octo-compute-stack.zip"

mkdir -p "${BUILD_DIR}"
STAGE_DIR="$(mktemp -d "${BUILD_DIR}/stage.XXXXXX")"
TMP_ZIP="${BUILD_DIR}/octo-compute-stack.$$.zip"
cleanup() {
    rm -rf "${STAGE_DIR}" "${TMP_ZIP}"
}
trap cleanup EXIT

cp -R "${SCRIPT_DIR}/terraform/"*.tf "${STAGE_DIR}/"
cp "${SCRIPT_DIR}/terraform/schema.yaml" "${STAGE_DIR}/schema.yaml"
mkdir -p "${STAGE_DIR}/cloud-init"
cp -R "${SCRIPT_DIR}/terraform/cloud-init/"* "${STAGE_DIR}/cloud-init/"
mkdir -p "${STAGE_DIR}/bootstrap/nginx" "${STAGE_DIR}/bootstrap/systemd"
cp "${SCRIPT_DIR}/install.sh" "${STAGE_DIR}/bootstrap/install.sh"
cp "${SCRIPT_DIR}/app-compose.yml" "${STAGE_DIR}/bootstrap/app-compose.yml"
cp "${SCRIPT_DIR}/runtime.env.template" "${STAGE_DIR}/bootstrap/runtime.env.template"
cp "${SCRIPT_DIR}/nginx/app.conf.template" "${STAGE_DIR}/bootstrap/nginx/app.conf.template"
cp "${SCRIPT_DIR}/systemd/octo-compute.service" "${STAGE_DIR}/bootstrap/systemd/octo-compute.service"
cp "${SCRIPT_DIR}/systemd/octo-podman.service" "${STAGE_DIR}/bootstrap/systemd/octo-podman.service"

mkdir -p "${STAGE_DIR}/modules-shared/modules"
cp -R "${REPO_ROOT}/deploy/terraform/modules/atp" "${STAGE_DIR}/modules-shared/modules/atp"
cp -R "${REPO_ROOT}/deploy/terraform/modules/apm_domain" "${STAGE_DIR}/modules-shared/modules/apm_domain"
cp -R "${REPO_ROOT}/deploy/terraform/modules/logging" "${STAGE_DIR}/modules-shared/modules/logging"
cp -R "${REPO_ROOT}/deploy/terraform/modules/stack_monitoring" "${STAGE_DIR}/modules-shared/modules/stack_monitoring"
cp -R "${REPO_ROOT}/deploy/terraform/modules/waf" "${STAGE_DIR}/modules-shared/modules/waf"

python3 - "${STAGE_DIR}" <<'PY'
import pathlib
import re
import sys

stage = pathlib.Path(sys.argv[1])
for tf in stage.glob("*.tf"):
    text = tf.read_text(encoding="utf-8")
    text = re.sub(
        r'source\s*=\s*"\.\./\.\./terraform/modules/',
        'source = "./modules-shared/modules/',
        text,
    )
    tf.write_text(text, encoding="utf-8")
PY

# Resource Manager injects provider auth/region. A local config profile would
# fail in the managed service.
cat >"${STAGE_DIR}/provider.tf" <<'EOF'
provider "oci" {}
EOF

(cd "${STAGE_DIR}" && zip -qr "${TMP_ZIP}" .)
mv "${TMP_ZIP}" "${OUT_ZIP}"

echo "Packaged: ${OUT_ZIP}"
echo
echo "Next: upload in OCI Console → Resource Manager → Stacks → Create Stack"
echo "      (source = My Configuration, file = octo-compute-stack.zip)"
