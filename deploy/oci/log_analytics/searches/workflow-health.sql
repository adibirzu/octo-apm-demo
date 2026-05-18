-- ============================================================================
-- workflow-health
-- Per-workflow latency + error-rate over the selected window.
-- ============================================================================
('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal'))
| jsonextract field = Message Service = '$.service_name'
| jsonextract field = Message 'Workflow ID' = '$.workflow_id'
| jsonextract field = Message 'HTTP Status Code' = '$.http_status_code'
| jsonextract field = Message 'DB Elapsed ms' = '$.db_elapsed_ms'
| where 'Workflow ID' != null
| stats count as Requests,
        values('HTTP Status Code') as Statuses,
        values('DB Elapsed ms') as 'DB ms samples'
  by 'Workflow ID', Service
| sort -Requests
