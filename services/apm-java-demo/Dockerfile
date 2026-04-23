###############################################################################
# octo-apm-java-demo — Spring Boot service wired with the OCI APM Java agent.
#
# Build context MUST be the repo root so the build can reach ../services/... if
# we ever bundle shared resources. Right now the build only uses this service's
# own sources:
#
#     docker build -f services/apm-java-demo/Dockerfile \
#         -t <ocir>/octo-apm-java-demo:<tag> .
#
# The OCI APM Java agent zip is downloaded at build time from the APM data-
# upload endpoint. Pass `APM_ENDPOINT` (the data-upload endpoint, same value as
# OCI_APM_ENDPOINT in the app) and `APM_AGENT_VERSION` as build args.
###############################################################################

# ── Builder ─────────────────────────────────────────────────────────────────
FROM maven:3.9-eclipse-temurin-21 AS builder
WORKDIR /build
COPY services/apm-java-demo/pom.xml /build/pom.xml
# Pre-fetch deps (cache layer)
RUN mvn -B -q dependency:go-offline || true
COPY services/apm-java-demo/src /build/src
RUN mvn -B -q package -DskipTests

# ── Runtime ─────────────────────────────────────────────────────────────────
# NOTE on the APM Java agent:
# The OCI APM Java agent is downloaded per-APM-domain from the Console
# (APM → Agent Registration Keys → Java). The exact download URL is
# tenancy-specific (embeds a signed token), so baking it at build time is
# not portable. We SIDE-LOAD the agent at runtime via an initContainer OR
# a `kubectl cp` operation. See services/apm-java-demo/README.md for the
# one-time side-load command. The entrypoint gracefully skips the agent
# if the jar is missing, so the app still serves traffic even before the
# agent is attached.
FROM eclipse-temurin:21-jre
ENV LANG=C.UTF-8 \
    JAVA_TOOL_OPTIONS="-XX:+UseG1GC -XX:MaxRAMPercentage=75" \
    APP_HOME=/app \
    APM_AGENT_DIR=/opt/apm-agent

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 10001 appuser \
    && mkdir -p /opt/apm-agent && chown -R appuser:appuser /opt/apm-agent

WORKDIR /app

COPY --from=builder /build/target/apm-java-demo.jar /app/apm-java-demo.jar

# Optional: bundle a pre-downloaded APM Java agent. The deploy script
# unpacks the operator-provided zip into services/apm-java-demo/agent-bundle/.
# If the directory is empty (no agent available at build time), the copy
# still succeeds — the runtime entrypoint detects a missing jar and boots
# without the agent. This keeps the image portable across tenancies.
COPY services/apm-java-demo/agent-bundle/ /opt/apm-agent/

COPY services/apm-java-demo/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
