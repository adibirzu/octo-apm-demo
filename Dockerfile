# ── Builder stage: install Python dependencies ──────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage: slim image with non-root user ────────────────
FROM python:3.11-slim

# Only runtime libraries needed (libpq for psycopg2-binary fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Non-root user for container security
RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local

WORKDIR /app
COPY server/ ./server/
COPY .env.example ./.env.example

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
