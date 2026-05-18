-- ============================================================================
-- service-error-triage
-- Fast error triage across app, Java sidecar, assistant, API Gateway, WAF,
-- attack lab, and OS evidence.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Trace ID' = '<TRACE_ID>' or 'Service Name' = '<SERVICE_NAME>'.
-- ============================================================================
('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal')
 and (Message like '%"level":"ERROR"%' or Message like '%"level":"CRITICAL"%'
      or Message like '%"http_status_code":5%' or Message like '%"java_apm_error_type"%'
      or Message like '%"attack_severity":"HIGH"%' or Message like '%"attack_severity":"CRITICAL"%'))
| jsonextract field = Message Service = '$.service_name'
| jsonextract field = Message 'Service Name' = '$.service_name'
| jsonextract field = Message 'Workflow ID' = '$.workflow_id'
| jsonextract field = Message 'Trace ID' = '$.trace_id'
| jsonextract field = Message 'Request ID' = '$.request_id'
| jsonextract field = Message 'URL Path' = '$.url_path'
| jsonextract field = Message 'HTTP Status Code' = '$.http_status_code'
| jsonextract field = Message Severity = '$.level'
| jsonextract field = Message 'Security Severity' = '$.attack_severity'
| jsonextract field = Message 'Java APM Error Type' = '$.java_apm_error_type'
| jsonextract field = Message 'Downstream Component' = '$.java_apm_service_name'
| jsonextract field = Message 'Demo Scenario' = '$.demo.scenario'
| jsonextract field = Message 'Expected Error' = '$.error.expected'
| jsonextract field = Message 'Payment Status' = '$.payment_status'
| jsonextract field = Message 'Payment Gateway Request ID' = '$.payment_gateway_request_id'
| jsonextract field = Message 'Process Phase' = '$.payment_gateway_phase'
| jsonextract field = Message 'Response Code' = '$.payment_processor_response_code'
| jsonextract field = Message 'Error Type' = '$.llmetry.error_type'
| jsonextract field = Message 'API Gateway Threat Signal' = '$.oci_api_gateway_threat_signal'
| jsonextract field = Message 'MITRE Technique ID' = '$.mitre_technique_id'
| jsonextract field = Message 'OSQuery Finding' = '$.osquery_finding'
| stats count as Events,
        values('Trace ID') as Traces,
        values('Request ID') as Requests,
        values('URL Path') as Paths,
        values('HTTP Status Code') as Statuses,
        values('Java APM Error Type') as 'Java Errors',
        values('Downstream Component') as 'Downstream Components',
        values('Demo Scenario') as 'Demo Scenarios',
        values('Expected Error') as 'Expected Flags',
        values('Payment Status') as 'Payment Statuses',
        values('Payment Gateway Request ID') as 'Payment Gateway Requests',
        values('Process Phase') as 'Payment Gateway Phases',
        values('Response Code') as 'Response Codes',
        values('Error Type') as 'Error Types',
        values('API Gateway Threat Signal') as 'Gateway Threats',
        values('MITRE Technique ID') as Techniques,
        values('OSQuery Finding') as Findings
  by 'Service Name', 'Workflow ID', 'Security Severity', 'Expected Error'
| sort -Events
