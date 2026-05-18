-- ============================================================================
-- melts-collection-completeness
-- Fast confidence check for demo signal completeness across app logs, trace
-- correlation fields, workflow events, and OKE Kubernetes ingestion.
-- ============================================================================
('Log Source' = 'SOC Application Logs' and 'Service Namespace' = 'octo')
or ('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal'))
or ('Log Source' = 'Kubernetes Container Generic Logs' and 'Kubernetes Cluster Name' = 'octo-apm-demo-oke' and Namespace in ('octo-drone-shop', 'enterprise-crm', 'oci-onm'))
| jsonextract field = Message MessageService = '$.service_name'
| jsonextract field = Message MessageTraceID = '$.trace_id'
| jsonextract field = Message MessageSpanID = '$.span_id'
| jsonextract field = Message MessageWorkflowID = '$.workflow_id'
| jsonextract field = Message MessageWorkflowStep = '$.workflow_step'
| jsonextract field = Message MessageOrderID = '$.order_id'
| jsonextract field = Message MessageGatewayID = '$.payment_gateway_request_id'
| stats count as Samples,
        distinctcount('Trace ID') as Traces,
        distinctcount(MessageTraceID) as 'Message Traces',
        distinctcount('Span ID') as Spans,
        distinctcount(MessageSpanID) as 'Message Spans',
        distinctcount('Workflow ID') as 'Promoted Workflows',
        distinctcount(MessageWorkflowID) as Workflows,
        distinctcount('Order ID') as 'Promoted Orders',
        distinctcount(MessageOrderID) as Orders,
        distinctcount('Payment Gateway Request ID') as 'Promoted Gateway Requests',
        distinctcount(MessageGatewayID) as 'Gateway Requests'
  by 'Log Source', 'Service Name', MessageService, Namespace
| sort -Samples
