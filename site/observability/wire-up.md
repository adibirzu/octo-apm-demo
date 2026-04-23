# OCI Observability wire-up

Every service shipped by the platform emits to one or more OCI
Observability surfaces. This page is the authoritative map — "where
does `<signal>` from `<service>` land?"

## Signal → destination matrix

| Signal | Producer | Transport | Destination |
|---|---|---|---|
| Traces | shop, crm, traffic-generator, load-control, async-worker, remediator, browser-runner (via backend) | OTLP/HTTP → `gateway.octo-otel.svc.cluster.local:4318` | OCI APM Domain |
| RUM events | shop browser SDK, crm browser SDK | direct beacon to `OCI_APM_RUM_ENDPOINT` | OCI APM RUM |
| Application logs (JSON) | shop, crm | `oci.loggingingestion` SDK → `OCI_LOG_ID` | OCI Logging → Service Connector → OCI Log Analytics source `octo-shop-app-json` |
| Edge access logs | octo-edge-gateway (OCI API GW) | Gateway logging policy | OCI Logging → Log Analytics source `octo-edge-gateway-json` |
| WAF events | OCI WAF attached to LB | WAF logging | OCI Logging log group `octo-waf-logs` |
| Custom metrics | shop (shop.checkout.count, shop.http.errors_5xx, …), load-control run counts | OCI Monitoring SDK | OCI Monitoring namespace `octo_drone_shop` |
| Stream metrics (queue depth, cache hit ratio) | async-worker, cache client | OTLP metrics → otel-gateway | OCI Monitoring (once exporter GA; stdout debug today) |
| Stack Monitoring | ATP Monitored Resource | OCI management-agent | OCI Stack Monitoring |
| Host metrics (VM) | octo-vm-lab + any Compute targets | OCI Management Agent | OCI Monitoring / Stack Monitoring |
| OCI Events | shop payments, load-control runs, remediator runs, object-pipeline processed | HTTP POST to `OCI_EVENTS_TOPIC_URL` | OCI Events / Notifications → remediator subscriber |
| Prometheus scrape | otel-gateway `:8888`, shop `/metrics`, crm `/metrics`, workflow-gateway `:9090` | scrape | OCI Monitoring via OpenTelemetry Collector receiver |

## Required env per service

Each service's k8s manifest references these Secrets; populate once via
`deploy/init-tenancy.sh` + `deploy/oci/ensure_apm.sh --print`:

| Secret | Key | Consumer(s) |
|---|---|---|
| `octo-apm` | `endpoint` | otel-gateway, shop, crm, app services |
| `octo-apm` | `private-key` | otel-gateway |
| `octo-apm` | `public-key` | shop, crm (browser SDK inject) |
| `octo-apm` | `rum-endpoint` | shop, crm |
| `octo-apm` | `web-application` | shop (OCI_APM_WEB_APPLICATION) |
| `octo-logging` | `log-id` | shop, crm |
| `octo-logging` | `log-group-id` | shop, crm |
| `octo-oci-config` | `compartment-id` | shop (GenAI + Monitoring) |
| `octo-events` | `topic-url` | load-control, remediator, object-pipeline |

## Correlation contract — what appears on every signal

Per [architecture/correlation-contract.md](../architecture/correlation-contract.md),
every trace + log + event carries:

- `trace_id` + `span_id` (OTel, W3C)
- `oracleApmTraceId` (log records — same value as `trace_id`)
- `request_id` (one per user click)
- `workflow_id` (business-flow slug)
- `run_id` (present when an `octo-load-control` profile or a
  `octo-remediator` action is active)
- `service.name` + `service.namespace=octo` + `deployment.environment`

## Verify end-to-end

Walk workshop Lab 02 (`site/workshop/lab-02-trace-log-correlation.md`):
one request → APM trace visible within 60s → LA search on
`oracleApmTraceId` returns the matching app log → click back to APM.

If any hop is empty, check:

| Empty hop | First-look |
|---|---|
| No APM trace | otel-gateway pod logs; OTel SDK `OTEL_EXPORTER_OTLP_ENDPOINT` points at the gateway, not OCI directly |
| APM trace but no LA row | Service Connector `la-pipeline-octo-shop-app` running; `oci log-analytics source get --namespace-name … --source-name octo-shop-app-json` shows the source |
| LA row but no `oracleApmTraceId` | `shop/server/observability/correlation.py` enrichment active; pod restarted after env change |
| RUM session missing | `OCI_APM_WEB_APPLICATION` matches the web-app OCID; browser dev tools show beacon POSTs |

## OCI Alarms + Notifications + Remediator

The remediator consumes alarms via its `/events/alarm` webhook:

```
OCI Monitoring alarm fires
      ↓
OCI Notifications topic `octo-alarms`
      ↓
HTTPS subscription →
      https://crm.example.tld/remediator/events/alarm
      ↓
remediator matches playbook → auto-apply (LOW) or propose (MEDIUM/HIGH)
```

Alarms we recommend enabling (most defined in
`deploy/terraform/modules/api_gateway/alarms.tf` + `deploy/oci/ensure_monitoring.sh`):

- `shop.http.errors_5xx` > 0 per minute (WARNING)
- `api_gateway 5xx` burst > 50 in 5m (CRITICAL) — KG-029
- ATP CPU > 80% sustained (CRITICAL)
- Container pod `OOMKilled` > 0 (WARNING)
- Queue lag `async-worker` pending > 1000 (WARNING)

## Dashboards

Import these saved searches + widgets from the repo:

- `tools/la-saved-searches/trace-to-logs.json` — parameterized by
  `${trace_id}`; pin to APM Trace Explorer drilldown.
- `tools/la-saved-searches/errors-by-route.json` — 4xx/5xx by route,
  1h window, bar chart.
- `tools/la-saved-searches/slow-checkout-spans.json` — > 1s checkout
  spans by `oracleApmTraceId`.

Apply:

```bash
LA_NAMESPACE=<ns> LA_LOG_GROUP_ID=<ocid> ./tools/la-saved-searches/apply.sh
```
