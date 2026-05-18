# Codebase Stack

Generated: 2026-05-14

## Primary Languages

- Python for Shop, CRM/Admin, traffic/workload services, deployment helpers,
  OCI automation, tests, and telemetry utilities.
- Java 21 for the `services/apm-java-demo` payment app-server sidecar.
- TypeScript/Node for Playwright E2E suites and the browser-runner service.
- Go for `shop/services/workflow-gateway`.
- Bash, Terraform, Helm/YAML, and Docker/Podman for deployment.
- Markdown, Mermaid, DrawIO, and SVG for docs and architecture artifacts.

## Application Frameworks

- `shop/` uses FastAPI, Uvicorn, SQLAlchemy async, Oracle/Postgres drivers,
  Jinja templates, HTTPX, Redis, OpenTelemetry, OCI SDK, and Playwright tests.
- `crm/` uses FastAPI, Uvicorn, SQLAlchemy, Oracle driver, Jinja templates,
  Pydantic settings, HTTPX, OpenTelemetry, OCI SDK, and Admin templates.
- `services/apm-java-demo/` uses Spring Boot 3.3.5, Spring Web, Actuator,
  Oracle JDBC, OpenTelemetry API/SDK/exporter, and Maven.
- Supporting Python services use small `pyproject.toml` packages with FastAPI
  or CLI surfaces and focused pytest suites.

## Observability Stack

- OpenTelemetry Python SDK/instrumentation `1.41.1` / `0.62b1` for FastAPI,
  SQLAlchemy, HTTPX, and logging.
- OpenTelemetry Java `1.43.0` for the Java payment app-server sidecar.
- OCI APM for traces, topology, RUM, App Servers, saved queries, and drilldowns.
- OCI Logging, Service Connector Hub where available, and Log Analytics for
  parser-backed logs, saved searches, dashboards, and detection rules.
- OCI Monitoring custom metrics under the shared `octo_apm_demo` namespace.
- OCI Kubernetes Monitoring for OKE container and tcpconnect telemetry.
- Langfuse/LLMetry optional OTLP trace export for GenAI evidence.

## Deployment Stack

- VM/Compute: `deploy/compute/`, `deploy/vm/`, Podman/Docker Compose, systemd,
  private hosts behind OCI Load Balancer/WAF/API Gateway.
- OKE: `deploy/k8s/oke/`, `deploy/oke/`, Helm chart under
  `deploy/helm/octo-apm-demo/`, OCIR images, HPA/PDB, OKE monitoring.
- Terraform/Resource Manager: `deploy/terraform/`, `deploy/resource-manager/`,
  and `deploy/compute/terraform/` for OCI resources.
- Local regression: `deploy/local-stack/` with local Postgres/Redis and
  Playwright/k6-compatible flows.

## Tooling

- Pytest for Python unit/integration tests.
- Playwright for end-to-end browser workflows.
- Maven/JUnit for Java sidecar tests.
- MkDocs for public docs.
- `deploy/verify.sh` for broad deployment surface validation.
- OCI CLI, kubectl, Helm, Terraform, Docker/Podman, jq, and envsubst for
  operator workflows.
