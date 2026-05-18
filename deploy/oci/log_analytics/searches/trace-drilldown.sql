-- ============================================================================
-- trace-drilldown
-- Pivot trace-bearing records across Shop + CRM + DB + WAF.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add a literal filter
-- such as 'Trace ID' = '<TRACE_ID>'.
-- ============================================================================
('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal'))
| jsonextract field = Message Service = '$.service_name'
| jsonextract field = Message 'Workflow ID' = '$.workflow_id'
| jsonextract field = Message 'Workflow Step' = '$.workflow_step'
| jsonextract field = Message 'URL Path' = '$.url_path'
| jsonextract field = Message 'HTTP Status Code' = '$.http_status_code'
| jsonextract field = Message 'Trace ID' = '$.trace_id'
| jsonextract field = Message 'DB Elapsed ms' = '$.db_elapsed_ms'
| jsonextract field = Message 'Order ID' = '$.order_id'
| jsonextract field = Message 'Source Order ID' = '$.source_order_id'
| jsonextract field = Message 'Payment Gateway Request ID' = '$.payment_gateway_request_id'
| jsonextract field = Message 'Payment Status' = '$.payment_status'
| jsonextract field = Message 'Payment Network' = '$.payment_network'
| jsonextract field = Message 'Payment Wallet Token Hash' = '$.payment_wallet_token_hash'
| jsonextract field = Message 'Process Phase' = '$.payment_gateway_phase'
| jsonextract field = Message 'Elapsed Time (Gateway)' = '$.payment_gateway_step_latency_ms'
| jsonextract field = Message 'Response Code' = '$.payment_processor_response_code'
| jsonextract field = Message 'Gateway ID' = '$.payment_processor_gateway_code'
| jsonextract field = Message 'Transaction ID' = '$.payment_network_transaction_id'
| jsonextract field = Message Flow = '$.payment_3ds_flow'
| jsonextract field = Message 'Downstream Component' = '$.java_apm_service_name'
| jsonextract field = Message 'Payment Processor' = '$.payment_processor_name'
| jsonextract field = Message 'Java APM Error Type' = '$.java_apm_error_type'
| jsonextract field = Message msg = '$.event_message'
| where 'Trace ID' != null
| sort Time
| fields Time, Service, 'Workflow ID', 'Workflow Step', 'URL Path',
         'HTTP Status Code', 'DB Elapsed ms', 'Security Rule', 'Security Action',
         'Event Types', 'Event Status', 'Order ID', 'Source Order ID',
         'Payment Gateway Request ID', 'Payment Status', 'Payment Network',
         'Payment Wallet Token Hash', 'Process Phase', 'Elapsed Time (Gateway)',
         'Response Code', 'Gateway ID', 'Transaction ID', Flow,
         'Downstream Component', 'Payment Processor', 'Java APM Error Type', msg
