ARG PYTHON_BASE=python:3.12-slim
FROM ${PYTHON_BASE}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip setuptools wheel && pip install .

# Non-root runtime.
RUN groupadd -r octo && useradd -r -g octo -u 10001 -s /usr/sbin/nologin octo \
    && chown -R octo:octo /app
USER 10001

CMD ["octo-async-worker"]
