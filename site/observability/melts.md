# MELTS Overview

## Metrics (M)

| Source | Destination | What |
|---|---|---|
| Prometheus `/metrics` | Grafana / scraper | HTTP RED, business KPIs, runtime |
| OCI Monitoring SDK | OCI Monitoring (`octo_drone_shop` namespace) | app.health, requests.rate, errors.rate, checkout.count, orders.count, db.latency_ms, crm.sync_age_s, inventory.low_stock_products |
| OCI Alarms | OCI Notifications | Error rate > 5/min, DB p95 > 2s, health down, CRM sync stale, low stock |
| OCI Health Checks | OCI Console | HTTP `/ready` every 30s |

## Events (E)

| Event Type | How Generated | Where Visible |
|---|---|---|
| Security spans | 19 MITRE ATT&CK types via `security_span()` | APM → filter `security.vuln_type` |
| Span error events | 4xx → client_error; 5xx → ERROR status | APM → Error Analysis |
| OCI Alarms | MQL queries on custom metrics | Monitoring → Alarms |
| WAF blocks | OCI WAF protection rules | WAF → Logs → Log Analytics |

## Logs (L)

| Log Source | Destination | Correlation Key |
|---|---|---|
| App structured logs | OCI Logging SDK | `oracleApmTraceId`, `trace_id`, `span_id` |
| App structured logs | Splunk HEC (optional) | Same fields |
| LB access logs | OCI Logging | Request ID |
| WAF logs | OCI Logging | Request ID |

!!! info "PII Masking"
    All email and phone fields are masked before external push: `u***@example.com`, `***5309`

## Traces (T)

| Instrumentation | Span Examples | Attributes |
|---|---|---|
| FastAPI middleware | Every HTTP request | method, route, status, duration_ms, client_ip |
| SQLAlchemy | Every SQL query | db.statement, execution_time_ms, row_count, SQL_ID |
| httpx | Every CRM call | W3C traceparent, peer.service |
| Custom spans | 50+ across 13 modules | shop.checkout, auth.login, shipping.get, etc. |
| Oracle session tags | Per-connection | MODULE, ACTION, CLIENT_IDENTIFIER=trace_id |

## Security (S)

| Control | Implementation |
|---|---|
| WAF | OCI WAF with SQLi, XSS, CmdInj, PathTraversal block rules + rate limiting |
| Cloud Guard | Target + detector recipes for compartment monitoring |
| Security Zones | Compliance recipe enforcing encryption and Vault policies |
| Vault | OCI Vault for secret management (HSM-backed AES-256 keys) |
| VSS | OCI Vulnerability Scanning integration in 360 dashboard |
| Security Spans | 19 MITRE ATT&CK types with OWASP 2021 codes |

## OCI Console Verification

| Layer | Verification Path |
|---|---|
| Traces | APM → Trace Explorer → `serviceName=octo-drone-shop-oke` |
| Topology | APM → Topology → CRM ↔ Shop ↔ ATP edges |
| RUM | APM → RUM → Session Explorer → add-to-cart, checkout events |
| Logs | Log Analytics → search `oracleApmTraceId=<trace_id>` |
| Metrics | Monitoring → Metric Explorer → namespace `octo_drone_shop` |
| Alarms | Monitoring → Alarms (5 configured) |
| DB | DB Management → Performance Hub → SQL Monitor |
| DB Insights | OPSI → SQL Warehouse → filter by `MODULE=octo-drone-shop` |
| Security | WAF → Logs; Cloud Guard → Security Score |
