#!/usr/bin/env bash
set -euo pipefail

TEMPLATE_PATH="${TEMPLATE_PATH:-$(dirname "$0")/workflow-gateway-api-spec.template.json}"
WORKFLOW_BACKEND_URL="${WORKFLOW_BACKEND_URL:-}"
ALLOWED_ORIGIN="${ALLOWED_ORIGIN:-https://shop.octodemo.cloud}"
OUTPUT_PATH="${OUTPUT_PATH:-$(dirname "$0")/workflow-gateway-api-spec.rendered.json}"

if [[ -z "${WORKFLOW_BACKEND_URL}" ]]; then
  echo "ERROR: set WORKFLOW_BACKEND_URL to the workflow gateway base URL (for example https://workflow.example.com)." >&2
  exit 1
fi

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  echo "ERROR: template not found at ${TEMPLATE_PATH}" >&2
  exit 1
fi

python3 - <<'PY' "${TEMPLATE_PATH}" "${OUTPUT_PATH}" "${WORKFLOW_BACKEND_URL}" "${ALLOWED_ORIGIN}"
import pathlib
import sys

template_path = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
workflow_backend_url = sys.argv[3].rstrip("/")
allowed_origin = sys.argv[4]

payload = template_path.read_text()
payload = payload.replace("__WORKFLOW_BACKEND_URL__", workflow_backend_url)
payload = payload.replace("__ALLOWED_ORIGIN__", allowed_origin)
output_path.write_text(payload)
print(f"Rendered OCI API Gateway spec -> {output_path}")
PY

echo "Next step:"
echo "  oci api-gateway deployment create --gateway-id <gateway_ocid> --path-prefix /workflow --display-name octo-workflow --specification file://${OUTPUT_PATH}"
