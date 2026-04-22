ARG PYTHON_BASE=python:3.12-slim
FROM ${PYTHON_BASE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY octo_traffic ./octo_traffic
RUN pip install --upgrade pip setuptools wheel && pip install .

# Default is continuous (K8s Deployment).
# Override OCTO_TRAFFIC_RUN_DURATION_SECONDS for one-shot Job runs.
ENTRYPOINT ["octo-traffic"]
