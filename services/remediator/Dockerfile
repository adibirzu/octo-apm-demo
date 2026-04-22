ARG PYTHON_BASE=python:3.12-slim
FROM ${PYTHON_BASE}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip setuptools wheel && pip install ".[k8s]"

EXPOSE 8080
CMD ["octo-remediator"]
