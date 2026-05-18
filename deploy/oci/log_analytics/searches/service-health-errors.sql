-- ============================================================================
-- service-health-errors
-- Health-focused error view that excludes known/expected demo and attack-lab
-- events. Use service-error-triage for the full threat-hunting view.
-- ============================================================================
('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal')
 and (Message like '%"level":"ERROR"%' or Message like '%"level":"CRITICAL"%'
      or Message like '%"http_status_code":5%'))
| jsonextract field = Message Service = '$.service_name'
| jsonextract field = Message 'Service Name' = '$.service_name'
| jsonextract field = Message 'Workflow ID' = '$.workflow_id'
| jsonextract field = Message 'Trace ID' = '$.trace_id'
| jsonextract field = Message 'URL Path' = '$.url_path'
| jsonextract field = Message 'HTTP Status Code' = '$.http_status_code'
| jsonextract field = Message Severity = '$.level'
| jsonextract field = Message 'Security Severity' = '$.attack_severity'
| jsonextract field = Message 'Demo Scenario' = '$.demo.scenario'
| jsonextract field = Message 'Expected Error' = '$.error.expected'
| where 'Expected Error' = null
        and 'Security Severity' = null
        and ('Workflow ID' = null or 'Workflow ID' not in ('admin-threat-simulation','attack-lab'))
| stats count as Events,
        values('Trace ID') as Traces,
        values('URL Path') as Paths,
        values('HTTP Status Code') as Statuses,
        values('Demo Scenario') as 'Demo Scenarios'
  by Service, 'Service Name', 'Workflow ID', Severity
| sort -Events
