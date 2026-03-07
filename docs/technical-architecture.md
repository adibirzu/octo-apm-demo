# OCTO Drone Shop Technical Architecture

## Runtime topology

1. OCI WAF protects the public endpoint.
2. OCI Load Balancer fronts the OKE service defined in [deploy/k8s/deployment.yaml](../deploy/k8s/deployment.yaml).
3. The Python app serves the storefront and backend APIs.
4. Oracle ATP stores the operational data for products, carts, customers, orders, shipments, page views, and assistant conversations.
5. OCI APM receives backend traces through OTLP and browser telemetry through OCI APM RUM.
6. OCI Logging stores structured application logs. Log Analytics can ingest those logs for correlation with `oracleApmTraceId`.

## Data model additions

- `assistant_sessions`: conversation session metadata for the GenAI advisor.
- `assistant_messages`: user and assistant turns, provider, model id, and trace id.
- Existing tables continue to back catalog, cart, order, shipment, analytics, and audit flows.

## Trace and log coverage

- Middleware traces every request with method, route, status, duration, and client IP.
- SQLAlchemy auto-instrumentation is enabled by passing the sync engine into OpenTelemetry setup.
- Store spans cover storefront reads, coupon checks, cart updates, checkout, order persistence, and assistant calls.
- Assistant messages and order audit rows store the active trace id for easier cross-correlation.
- App logs include `oracleApmTraceId`, `trace_id`, and `span_id`.

## RUM

- The browser shell injects OCI APM RUM when `OCI_APM_RUM_ENDPOINT` and `OCI_APM_PUBLIC_DATAKEY` are present.
- The browser shell also uses `OCI_APM_WEB_APPLICATION` to identify the web application context.
- The frontend also posts explicit page-view events to `/api/analytics/track` so the backend stores synthetic user activity even when browser agent rollout is still being validated.

## OCI APM endpoint mapping

- Backend traces use `OCI_APM_ENDPOINT` plus the OTLP path:
  - `/20200101/opentelemetry/private/v1/traces`
- Browser RUM uses:
  - `OCI_APM_RUM_ENDPOINT`
  - `OCI_APM_PUBLIC_DATAKEY`
  - `OCI_APM_WEB_APPLICATION`
- The concrete setup steps are in [docs/install-guide.md](install-guide.md#oci-apm-and-rum-configuration).

## OCI Generative AI

- Configure `OCI_COMPARTMENT_ID`, `OCI_GENAI_ENDPOINT`, and `OCI_GENAI_MODEL_ID`.
- The app uses the OCI Python SDK `GenerativeAiInferenceClient.chat`.
- Product answers are grounded with catalog snippets sourced from ATP.
- If OCI GenAI is unavailable, the app falls back to a deterministic grounded responder so the assistant remains usable.

## ATP deployment notes

- Production deployment and local smoke tests are ATP-only.
- Mount the ATP wallet secret at `/opt/oracle/wallet`.
- The readiness endpoint validates DB connectivity with `SELECT 1 FROM DUAL` for Oracle.

## OCI edge logging

The application code cannot enable OCI resource logs by itself; enable these in OCI for the deployed resources:

1. On the OCI Load Balancer, enable access logs and error logs to OCI Logging.
2. On OCI WAF, enable policy logs to OCI Logging.
3. In OCI Logging Analytics, create a source or ingest pipeline for the LB and WAF log groups.
4. For external Splunk, choose one of these patterns:
   - Use OCI Logging plus Service Connector Hub to stream logs to OCI Streaming, then run a Splunk forwarder consumer.
   - Or export from OCI Logging/Logging Analytics into your existing external collector pipeline.
5. The application already supports direct HEC shipping for app logs with `SPLUNK_HEC_URL` and `SPLUNK_HEC_TOKEN`.

## Validation checklist

- `/ready` returns `database: connected` and `db_type: oracle_atp`.
- `/api/shop/storefront` shows `backend.database = oracle_atp`.
- `/api/shop/checkout` creates rows in `orders`, `order_items`, `shipments`, and `audit_logs`.
- `/api/shop/assistant/query` stores rows in `assistant_sessions` and `assistant_messages`.
- OCI APM shows request, DB, checkout, and assistant spans.
- OCI Logging and Log Analytics show correlated app logs.
- OCI LB and WAF logs are enabled in OCI and routed into the selected OCI Logging groups.
