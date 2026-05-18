#!/usr/bin/env bash
# Deploy the scoped Octo APM Log Analytics workshop slice from octo-apm-demo.
#
# Usage:
#   DETECTIONS_REPO=../oci-log-analytics-detections \
#   OCI_PROFILE=<OCI_PROFILE> \
#   OCI_COMPARTMENT_ID=<COMPARTMENT_OCID> \
#   LA_NAMESPACE=<LA_NAMESPACE> \
#   LOG_ANALYTICS_LOG_GROUP_ID=<LA_LOG_GROUP_OCID> \
#   ./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --dry-run
#
#   ./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh \
#     --deploy --generate-data --ingest-data --verify
#
#   ./deploy/oci/log_analytics/deploy_octo_apm_workshop.sh --field-audit
#
# This wrapper intentionally uses variables for every tenancy-specific value.
# It exports metadata-only detection-rule specs; it does not create alarms.

set -euo pipefail

show_usage() {
    awk 'NR == 1 { next } /^$/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

DETECTIONS_REPO="${DETECTIONS_REPO:-${REPO_ROOT}/../oci-log-analytics-detections}"
DETECTIONS_PYTHON="${DETECTIONS_PYTHON:-python3}"
OCTO_APM_DASHBOARD_NAME="${OCTO_APM_DASHBOARD_NAME:-OCI-DEMO: Octo APM Demo Dashboard}"
OCTO_WORKSHOP_DAYS="${OCTO_WORKSHOP_DAYS:-21}"
OCTO_WORKSHOP_LOOKBACK="${OCTO_WORKSHOP_LOOKBACK:-21d}"
OCTO_WORKSHOP_QUERY_TIMEOUT="${OCTO_WORKSHOP_QUERY_TIMEOUT:-90}"
OCTO_WORKSHOP_DATA_FILE="${OCTO_WORKSHOP_DATA_FILE:-octo_apm_workshop_application_logs.jsonl}"
OCTO_WORKSHOP_EVIDENCE_JSON="${OCTO_WORKSHOP_EVIDENCE_JSON:-docs/health/octo-apm-workshop-live.json}"
OCTO_WORKSHOP_RULE_EVIDENCE_JSON="${OCTO_WORKSHOP_RULE_EVIDENCE_JSON:-docs/health/octo-apm-detection-rules-live.json}"
OCTO_WORKSHOP_INGEST_MODE="${OCTO_WORKSHOP_INGEST_MODE:-direct}"

DRY_RUN=false
DEPLOY=false
VERIFY=false
GENERATE_DATA=false
INGEST_DATA=false
SKIP_LIVE_VALIDATION=false
FIELD_AUDIT=false
ACTION_SELECTED=false

while (($#)); do
    case "$1" in
        -h|--help)
            show_usage
            exit 0
            ;;
        --dry-run)
            DRY_RUN=true
            ACTION_SELECTED=true
            ;;
        --deploy)
            DEPLOY=true
            ACTION_SELECTED=true
            ;;
        --verify)
            VERIFY=true
            ACTION_SELECTED=true
            ;;
        --field-audit)
            FIELD_AUDIT=true
            ACTION_SELECTED=true
            ;;
        --generate-data)
            GENERATE_DATA=true
            ;;
        --ingest-data)
            INGEST_DATA=true
            ;;
        --skip-live-validation)
            SKIP_LIVE_VALIDATION=true
            ;;
        --activate-rules)
            echo "--activate-rules is not implemented by the metadata-only detection-rule exporter." >&2
            echo "Review queries/detection_rule_specs.json and promote scheduled searches through the approved release path." >&2
            exit 2
            ;;
        --profile)
            shift
            : "${1:?--profile requires a value}"
            export OCI_PROFILE="$1"
            ;;
        --detections-repo)
            shift
            : "${1:?--detections-repo requires a value}"
            DETECTIONS_REPO="$1"
            ;;
        --lookback)
            shift
            : "${1:?--lookback requires a value}"
            OCTO_WORKSHOP_LOOKBACK="$1"
            ;;
        --query-timeout)
            shift
            : "${1:?--query-timeout requires a value}"
            OCTO_WORKSHOP_QUERY_TIMEOUT="$1"
            ;;
        --days)
            shift
            : "${1:?--days requires a value}"
            OCTO_WORKSHOP_DAYS="$1"
            ;;
        --evidence-json)
            shift
            : "${1:?--evidence-json requires a value}"
            OCTO_WORKSHOP_EVIDENCE_JSON="$1"
            ;;
        *)
            echo "Unknown argument: $1" >&2
            show_usage >&2
            exit 2
            ;;
    esac
    shift
done

if ! $ACTION_SELECTED; then
    DRY_RUN=true
fi

require_detections_repo() {
    if [[ ! -f "${DETECTIONS_REPO}/scripts/octo_apm_workshop.py" ]]; then
        echo "DETECTIONS_REPO does not point at oci-log-analytics-detections: ${DETECTIONS_REPO}" >&2
        exit 2
    fi
}

run_detection_python() {
    (cd "${DETECTIONS_REPO}" && "${DETECTIONS_PYTHON}" "$@")
}

require_detections_repo

echo "Octo APM workshop deployment surface"
echo "  detections repo: ${DETECTIONS_REPO}"
echo "  dashboard:       ${OCTO_APM_DASHBOARD_NAME}"
echo "  lookback:        ${OCTO_WORKSHOP_LOOKBACK}"
echo "  data file:       ${OCTO_WORKSHOP_DATA_FILE}"

run_detection_python "scripts/octo_apm_workshop.py" --export-bundle

if $FIELD_AUDIT; then
    run_detection_python "scripts/setup_log_sources.py" --octo-apm-only --field-audit
fi

if $DRY_RUN; then
    run_detection_python "scripts/octo_apm_workshop.py" --summary
    run_detection_python "scripts/setup_log_sources.py" --octo-apm-only --dry-run
    run_detection_python "scripts/deploy_dashboard.py" --dry-run \
        --dashboard-name "${OCTO_APM_DASHBOARD_NAME}"
    echo "Dry run complete. No OCI resources were mutated."
    exit 0
fi

if $DEPLOY; then
    if ! $FIELD_AUDIT; then
        run_detection_python "scripts/setup_log_sources.py" --octo-apm-only --field-audit
    fi
    run_detection_python "scripts/setup_log_sources.py" --octo-apm-only
fi

if $FIELD_AUDIT && ! $DEPLOY && ! $VERIFY && ! $GENERATE_DATA && ! $INGEST_DATA; then
    echo "Field audit complete. No OCI resources were mutated."
    exit 0
fi

if $GENERATE_DATA; then
    run_detection_python "scripts/octo_apm_workshop.py" --generate-data --days "${OCTO_WORKSHOP_DAYS}"
fi

if $INGEST_DATA; then
    run_detection_python "scripts/ingest_test_data.py" --mode "${OCTO_WORKSHOP_INGEST_MODE}" \
        --file "${OCTO_WORKSHOP_DATA_FILE}"
fi

if $DEPLOY; then
    deploy_args=(
        "scripts/deploy_dashboard.py"
        --dashboard-name "${OCTO_APM_DASHBOARD_NAME}"
        --query-lookback "${OCTO_WORKSHOP_LOOKBACK}"
        --query-timeout "${OCTO_WORKSHOP_QUERY_TIMEOUT}"
    )
    if $SKIP_LIVE_VALIDATION; then
        deploy_args+=(--skip-live-validation)
    fi

    run_detection_python "scripts/detection_rule_creator.py" --write-default
    run_detection_python "${deploy_args[@]}"
    echo "Detection-rule specs exported as metadata-only content. No OCI alarms or scheduled searches were created."
fi

if $VERIFY; then
    run_detection_python "scripts/verify_deployed_dashboards.py" --dashboard-name "${OCTO_APM_DASHBOARD_NAME}" \
        --lookback "${OCTO_WORKSHOP_LOOKBACK}" \
        --query-timeout "${OCTO_WORKSHOP_QUERY_TIMEOUT}" \
        --max-workers 4 \
        --json "${OCTO_WORKSHOP_EVIDENCE_JSON}"
    run_detection_python "scripts/verify_octo_apm_detection_rules.py" \
        --lookback "${OCTO_WORKSHOP_LOOKBACK}" \
        --query-timeout "${OCTO_WORKSHOP_QUERY_TIMEOUT}" \
        --json "${OCTO_WORKSHOP_RULE_EVIDENCE_JSON}"
fi

echo "Octo APM workshop operation complete."
