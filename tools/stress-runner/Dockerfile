# octo-stress-runner — FastAPI wrapper + k6 binary in a single image.
#
# Multi-stage:
#   Stage 1 (k6): pin the k6 binary from grafana/k6:0.55.0-alpine.
#   Stage 2 (runtime): python:3.12-slim, copy the k6 binary, install the
#                      Python wrapper from pyproject.toml, start uvicorn.
#
# Build (per global cloud-build rule — run on control-plane VM, not local ARM):
#   ssh control-plane-oci "cd /tmp/octo-apm-demo/tools/stress-runner && \
#       docker build -t ${OCIR_REGION}.ocir.io/${OCIR_TENANCY}/octo-stress-runner:$(date +%Y%m%d%H%M%S) ."
# ----------------------------------------------------------------------------

ARG K6_IMAGE=grafana/k6:0.55.0
ARG PYTHON_BASE=python:3.12-slim

# Stage 1 — k6 binary source.
FROM ${K6_IMAGE} AS k6

# Stage 2 — Python runtime.
FROM ${PYTHON_BASE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OCTO_STRESS_RUNNER_K6_BINARY=/usr/local/bin/k6 \
    OCTO_STRESS_RUNNER_SCENARIOS_DIR=/app/scenarios

# Copy the k6 binary from the official image into PATH.
COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6

# Install the wrapper package.
COPY pyproject.toml ./
COPY octo_stress_runner ./octo_stress_runner
RUN pip install --upgrade pip setuptools wheel && pip install .

# Scenarios are baked into the image so the pod has no network dependency
# at run start (and so the scenario allow-list is auditable per release).
COPY scenarios ./scenarios

# Verify k6 is reachable at build time — fail fast if multi-stage copy broke.
RUN /usr/local/bin/k6 version

EXPOSE 8080

# uvicorn entrypoint — single worker (concurrency=1 is enforced inside the
# app via the asyncio.Lock; running >1 worker would defeat that guard).
ENTRYPOINT ["uvicorn", "octo_stress_runner.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
