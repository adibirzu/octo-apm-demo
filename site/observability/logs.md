# Logs

## Structured JSON Logging

Every log entry includes trace context for OCI Log Analytics correlation:

```json
{
  "timestamp": "2026-04-11T12:00:00.000Z",
  "level": "INFO",
  "message": "Store checkout persisted",
  "trace_id": "79c76c8173b086043b36e60422a2b317",
  "span_id": "af2ac0675e8b5211",
  "oracleApmTraceId": "79c76c8173b086043b36e60422a2b317",
  "traceparent": "00-79c76c8173b086043b36e60422a2b317-af2ac0675e8b5211-01",
  "service.name": "octo-drone-shop-oke",
  "orders.order_id": 3142,
  "orders.total": 2499.99
}
```

## Log Destinations

| Destination | Configuration | Purpose |
|---|---|---|
| **stdout** (JSON) | Always enabled | Container log collection |
| **OCI Logging SDK** | `OCI_LOG_ID` + `OCI_LOG_GROUP_ID` | OCI Logging → Log Analytics |
| **Splunk HEC** | `SPLUNK_HEC_URL` + `SPLUNK_HEC_TOKEN` | External SIEM |

## PII Masking

All personally identifiable information is masked before external push:

| Field | Example Input | Masked Output |
|---|---|---|
| `customer_email` | `alice@example.com` | `a***@example.com` |
| `customer_phone` | `+1-555-867-5309` | `***5309` |

Masking is applied immutably — original data never leaves the application process.

## Log Analytics Correlation

In OCI Log Analytics, search by `oracleApmTraceId` to find all logs from a specific APM trace:

```
oracleApmTraceId = "79c76c8173b086043b36e60422a2b317"
```

This joins application logs with APM trace data for end-to-end debugging.
