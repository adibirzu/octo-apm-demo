-- ============================================================================
-- service-trace-log-coverage
-- Per-service coverage check for Log Analytics records that carry trace/span
-- correlation fields. Use this before assuming APM and logs are joined.
-- ============================================================================
('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal'))
or ('Log Source' = 'SOC Application Logs' and 'Service Namespace' = 'octo')
| jsonextract field = Message MessageService = '$.service_name'
| jsonextract field = Message MessageTraceID = '$.trace_id'
| jsonextract field = Message MessageSpanID = '$.span_id'
| jsonextract field = Message MessageEnvironment = '$.deployment_environment'
| where 'Trace ID' != null or 'Span ID' != null or MessageTraceID != null or MessageSpanID != null
| stats count as Records,
        values('Trace ID') as 'Trace IDs',
        values(MessageTraceID) as 'Message Trace IDs',
        values('Span ID') as 'Span IDs',
        values(MessageSpanID) as 'Message Span IDs',
        values('Log Source') as 'Log Sources',
        values('Deployment Environment') as Environments,
        values(MessageEnvironment) as 'Message Environments',
        values('Trace ID') as Traces,
        values(MessageTraceID) as 'Message Traces'
  by 'Service Name', MessageService
| sort -Records
