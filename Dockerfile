# Pin the base image per tenancy build. For reproducibility, override
# PYTHON_BASE at build time with a digest-locked reference:
#   docker build --build-arg PYTHON_BASE=python:3.12-slim@sha256:<digest> .
# The floating tag below is acceptable for local development only.
ARG PYTHON_BASE=python:3.12-slim
FROM ${PYTHON_BASE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

# Install system deps for oracledb thin mode
RUN apt-get update && apt-get install -y --no-install-recommends     curl     ca-certificates &&     rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && pip install -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
