-- ============================================================================
-- connector-live-log-coverage
-- Live OCI Logging -> Service Connector Hub -> Log Analytics coverage.
-- Service Connector Hub Logging sources land as OCI Unified Schema Logs; the
-- app emitters put a JSON envelope in Message so jsonextract can recover the
-- trace, span, user, workflow, DB, and order pivots.
-- ============================================================================
'Log Source' = 'OCI Unified Schema Logs'
and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal')
| jsonextract field = Message trace_id = '$.trace_id'
| jsonextract field = Message span_id = '$.span_id'
| jsonextract field = Message service_name = '$.service_name'
| jsonextract field = Message service_namespace = '$.service_namespace'
| jsonextract field = Message workflow_id = '$.workflow_id'
| jsonextract field = Message workflow_step = '$.workflow_step'
| jsonextract field = Message url_path = '$.url_path'
| jsonextract field = Message http_status_code = '$.http_status_code'
| jsonextract field = Message order_id = '$.order_id'
| jsonextract field = Message db_target = '$.db_target'
| jsonextract field = Message event_message = '$.event_message'
| stats count as Records,
        distinctcount(trace_id) as Traces,
        distinctcount(span_id) as Spans,
        values(url_path) as 'URL Paths',
        values(http_status_code) as Statuses,
        values(order_id) as Orders,
        values(db_target) as 'DB Targets'
  by service_name, service_namespace, workflow_id, workflow_step
| sort -Records
