#!/usr/bin/env bash
# Launch the Spring Boot app with the OCI APM Java agent attached.
#
# Env required:
#   OCI_APM_ENDPOINT          — data-upload endpoint (https://<domain>.apm-agt.<region>.oci.oraclecloud.com)
#   OCI_APM_PRIVATE_DATAKEY   — private data key from the APM domain
#   OCI_APM_SERVICE_NAME      — service label shown in APM (default: octo-apm-java-demo)
#
# If the APM agent jar is missing (image was built without network access to
# OCI), the app still starts but will not appear in the App Servers view.
set -euo pipefail

AGENT_JAR="${APM_AGENT_DIR:-/opt/apm-agent}/bootstrap/apm-java-agent.jar"
APM_SERVICE_NAME="${OCI_APM_SERVICE_NAME:-octo-apm-java-demo}"

JAVA_OPTS=(
    "-Dspring.application.name=${APM_SERVICE_NAME}"
    "-Dserver.port=8080"
)

if [[ -f "${AGENT_JAR}" && -n "${OCI_APM_ENDPOINT:-}" && -n "${OCI_APM_PRIVATE_DATAKEY:-}" ]]; then
    JAVA_OPTS+=(
        "-javaagent:${AGENT_JAR}"
        "-Dcom.oracle.apm.agent.data.upload.endpoint=${OCI_APM_ENDPOINT}"
        "-Dcom.oracle.apm.agent.private.data.key=${OCI_APM_PRIVATE_DATAKEY}"
        "-Dcom.oracle.apm.agent.service.name=${APM_SERVICE_NAME}"
    )
    echo "[entrypoint] OCI APM Java agent attached: ${AGENT_JAR}" >&2
    echo "[entrypoint] service=${APM_SERVICE_NAME}, endpoint=${OCI_APM_ENDPOINT}" >&2
else
    echo "[entrypoint] OCI APM agent skipped (agent=${AGENT_JAR} endpoint=${OCI_APM_ENDPOINT:-unset})" >&2
fi

exec java "${JAVA_OPTS[@]}" -jar /app/apm-java-demo.jar
