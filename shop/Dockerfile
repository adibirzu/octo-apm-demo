# Pin the base image per tenancy build. For reproducibility, override
# PYTHON_BASE at build time with a digest-locked reference:
#   docker build --build-arg PYTHON_BASE=python:3.12-slim@sha256:<digest> .
# The floating tag below is acceptable for local development only.
#
# BUILD CONTEXT MUST BE THE REPO ROOT (octo-apm-demo/), NOT shop/, because
# the image installs two sibling editable packages (services/cache/client
# and services/async-worker). Build with:
#     docker build -f shop/Dockerfile -t <image>:<tag> .
ARG PYTHON_BASE=python:3.12-slim

# ── Builder stage: install Python deps + local editable packages ───
FROM ${PYTHON_BASE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc build-essential ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements + local packages referenced by requirements-dev.txt
COPY shop/requirements.txt shop/requirements.txt
COPY services/cache/client services/cache/client
COPY services/async-worker services/async-worker

RUN pip install --upgrade pip setuptools wheel && \
    pip install --prefix=/install --ignore-installed -r shop/requirements.txt && \
    pip install --prefix=/install --ignore-installed --no-deps \
        ./services/cache/client \
        ./services/async-worker

# ── Runtime stage: slim, non-root ──────────────────────────────────
FROM ${PYTHON_BASE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash --uid 10001 appuser

COPY --from=builder /install /usr/local

WORKDIR /app
COPY shop/server /app/server

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
