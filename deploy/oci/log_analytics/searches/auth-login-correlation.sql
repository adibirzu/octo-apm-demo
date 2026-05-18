-- ============================================================================
-- auth-login-correlation
-- Login/session traces mapped to user action logs and DB/session writes.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Trace ID' = '<TRACE_ID>' or 'Request ID' = '<REQUEST_ID>'.
-- ============================================================================
('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal')
 and (Message like '%login%' or Message like '%auth%'))
| jsonextract field = Message Service = '$.service_name'
| jsonextract field = Message 'Service Name' = '$.service_name'
| jsonextract field = Message 'URL Path' = '$.url_path'
| jsonextract field = Message 'HTTP Status Code' = '$.http_status_code'
| jsonextract field = Message 'Workflow ID' = '$.workflow_id'
| jsonextract field = Message 'Trace ID' = '$.trace_id'
| jsonextract field = Message 'Request ID' = '$.request_id'
| jsonextract field = Message 'User ID' = '$.user_id'
| jsonextract field = Message 'DB Statement' = '$.db_statement'
| jsonextract field = Message msg = '$.event_message'
| stats count as Events,
        values('HTTP Status Code') as Statuses,
        values('Trace ID') as Traces,
        values('Request ID') as Requests,
        values('User ID') as Users,
        values('DB Statement') as 'DB Statements'
  by Service, 'Service Name', 'URL Path', 'HTTP Status Code'
| sort -Events
