#!/usr/bin/env bash
# Package the Resource Manager stack into a zip ready for OCI Console
# upload. The zip MUST be flat at the root — Resource Manager rejects
# nested stacks inside a single archive.
#
# Output: deploy/resource-manager/build/octo-stack.zip

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
STAGE_DIR="${BUILD_DIR}/stage"
OUT_ZIP="${BUILD_DIR}/octo-stack.zip"

rm -rf "${BUILD_DIR}"
mkdir -p "${STAGE_DIR}"

# 1. Copy Resource Manager root files (main.tf, variables.tf, schema.yaml)
cp "${SCRIPT_DIR}/main.tf"      "${STAGE_DIR}/main.tf"
cp "${SCRIPT_DIR}/variables.tf" "${STAGE_DIR}/variables.tf"
cp "${SCRIPT_DIR}/schema.yaml"  "${STAGE_DIR}/schema.yaml"

# 2. Fold in the upstream terraform stack so the module "../terraform"
#    reference in main.tf resolves inside the archive. Resource Manager
#    runs the zip's root as the working directory, so we relocate the
#    module to a sibling directory and rewrite the path.
mkdir -p "${STAGE_DIR}/modules-shared"
cp -R "${REPO_ROOT}/deploy/terraform/"*.tf "${STAGE_DIR}/modules-shared/"
cp -R "${REPO_ROOT}/deploy/terraform/modules" "${STAGE_DIR}/modules-shared/modules"

# Rewrite the relative module source from "../terraform" to
# "./modules-shared" so the zip is self-contained.
sed -i.bak 's#source = "\.\./terraform"#source = "./modules-shared"#' "${STAGE_DIR}/main.tf"
rm -f "${STAGE_DIR}/main.tf.bak"

# 3. Strip backend.tf from the shared copy — Resource Manager supplies
#    its own state backend and will reject any backend configuration
#    baked into the stack.
rm -f "${STAGE_DIR}/modules-shared/backend.tf"

# 4. Build the archive.
(cd "${STAGE_DIR}" && zip -qr "${OUT_ZIP}" .)

echo "Packaged: ${OUT_ZIP}"
echo
echo "Next: upload in OCI Console → Resource Manager → Stacks → Create Stack"
echo "      (source = My Configuration, file = octo-stack.zip)"
