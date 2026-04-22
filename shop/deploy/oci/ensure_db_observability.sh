#!/usr/bin/env bash
set -euo pipefail

if ! command -v oci >/dev/null 2>&1; then
  echo "ERROR: OCI CLI is required." >&2
  exit 1
fi

AUTONOMOUS_DATABASE_ID="${AUTONOMOUS_DATABASE_ID:-}"
if [[ -z "${AUTONOMOUS_DATABASE_ID}" ]]; then
  echo "ERROR: set AUTONOMOUS_DATABASE_ID" >&2
  exit 1
fi

echo "Enabling Autonomous Database Management..."
oci db autonomous-database enable-autonomous-database-management \
  --autonomous-database-id "${AUTONOMOUS_DATABASE_ID}" 2>/dev/null || \
  echo "  (already enabled or not supported on this ATP edition)"

echo "Enabling Operations Insights..."
oci db autonomous-database enable-operations-insights \
  --autonomous-database-id "${AUTONOMOUS_DATABASE_ID}" 2>/dev/null || \
  echo "  (already enabled or not supported on this ATP edition)"

cat <<'EOF'

Database observability base services are enabled.

Recommended next steps:
1. Confirm the ATP shows up in DB Management and Operations Insights.
2. Point WORKFLOW_API_BASE_URL at the OCI API Gateway deployment endpoint.
3. Route workflow gateway logs into OCI Logging and attach the log group to Log Analytics.
4. If you want recurring faulty probes, set WORKFLOW_FAULTY_QUERY_ENABLED=true in the workflow gateway runtime.
EOF
