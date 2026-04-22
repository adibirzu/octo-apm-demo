ARG PYTHON_BASE=python:3.12-slim
FROM ${PYTHON_BASE}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip setuptools wheel && pip install ".[oci]"

RUN groupadd -r octo && useradd -r -g octo -u 10001 -s /usr/sbin/nologin octo \
    && mkdir -p /data && chown -R octo:octo /app /data
USER 10001

EXPOSE 8080
CMD ["uvicorn", "octo_load_control.api:app", "--host", "0.0.0.0", "--port", "8080"]
