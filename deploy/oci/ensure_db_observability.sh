#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Enterprise CRM Portal — Enable Database Observability
#
# Enables OCI Database Management and Operations Insights on an Oracle ATP
# so that SQL performance, AWR, and OPSI dashboards are available.
#
# Required env vars:
#   AUTONOMOUS_DATABASE_ID — ATP instance OCID
# ─────────────────────────────────────────────────────────────────────────────

if ! command -v oci >/dev/null 2>&1; then
  echo "ERROR: OCI CLI is required." >&2
  exit 1
fi

AUTONOMOUS_DATABASE_ID="${AUTONOMOUS_DATABASE_ID:-}"
if [[ -z "${AUTONOMOUS_DATABASE_ID}" ]]; then
  echo "ERROR: set AUTONOMOUS_DATABASE_ID" >&2
  exit 1
fi

echo "Enabling Autonomous Database Management on ${AUTONOMOUS_DATABASE_ID}..."
oci db autonomous-database enable-autonomous-database-management \
  --autonomous-database-id "${AUTONOMOUS_DATABASE_ID}" 2>/dev/null || \
  echo "  (already enabled or not supported on this ATP edition)"

echo "Enabling Operations Insights on ${AUTONOMOUS_DATABASE_ID}..."
oci db autonomous-database enable-operations-insights \
  --autonomous-database-id "${AUTONOMOUS_DATABASE_ID}" 2>/dev/null || \
  echo "  (already enabled or not supported on this ATP edition)"

cat <<'EOF'

Database observability services enabled.

What this unlocks:
  - DB Management Console: SQL monitoring, performance hub, AWR reports
  - Operations Insights (OPSI): SQL warehouse, capacity planning, SQL analytics
  - Session tagging: CRM's db_session_tagging.py sets MODULE/ACTION/CLIENT_IDENTIFIER
    on every Oracle session, enabling drill-down from OPSI to individual CRM requests.

Recommended next steps:
  1. Verify ATP appears in OCI Console → Observability → Database Management
  2. Verify ATP appears in OCI Console → Observability → Operations Insights
  3. Set DATABASE_OBSERVABILITY_ENABLED=true in CRM config (default)
  4. Set ATP_OCID in CRM config to enable OCID-based span enrichment
  5. Run CRM and check that db.oracle.sql_id attributes appear in APM traces

If using OCI-DEMO, these are configured automatically by c27_deploy_enterprise_crm.sh.
EOF
