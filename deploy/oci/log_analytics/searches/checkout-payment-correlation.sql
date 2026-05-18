-- ============================================================================
-- checkout-payment-correlation
-- End-to-end order, payment, Java sidecar, card/wallet rail, and CRM pivots.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Trace ID' = '<TRACE_ID>' or 'Order ID' = '<ORDER_ID>'.
-- ============================================================================
('Log Source' = 'OCI Unified Schema Logs' and 'OCI Resource Name' in ('octo-drone-shop', 'enterprise-crm-portal'))
| jsonextract field = Message Service = '$.service_name'
| jsonextract field = Message 'Service Name' = '$.service_name'
| jsonextract field = Message 'Workflow ID' = '$.workflow_id'
| jsonextract field = Message 'Workflow Step' = '$.workflow_step'
| jsonextract field = Message 'Trace ID' = '$.trace_id'
| jsonextract field = Message 'Span ID' = '$.span_id'
| jsonextract field = Message 'Request ID' = '$.request_id'
| jsonextract field = Message 'Journey ID' = '$.shop_journey_id'
| jsonextract field = Message 'User Action' = '$.enduser_action'
| jsonextract field = Message 'Checkout Step' = '$.checkout_step'
| jsonextract field = Message 'Browser Trace ID' = '$.browser_trace_id'
| jsonextract field = Message 'Order ID' = '$.order_id'
| jsonextract field = Message 'Source Order ID' = '$.source_order_id'
| jsonextract field = Message 'Payment Gateway Request ID' = '$.payment_gateway_request_id'
| jsonextract field = Message 'Payment Provider' = '$.payment_provider'
| jsonextract field = Message 'Payment Status' = '$.payment_status'
| jsonextract field = Message 'Payment Network' = '$.payment_network'
| jsonextract field = Message 'Payment Wallet Token Hash' = '$.payment_wallet_token_hash'
| jsonextract field = Message 'Payment Risk Score' = '$.payment_risk_score'
| jsonextract field = Message Gateway = '$.payment_gateway_name'
| jsonextract field = Message Provider = '$.payment_gateway_provider'
| jsonextract field = Message Version = '$.payment_gateway_version'
| jsonextract field = Message Method = '$.payment_method'
| jsonextract field = Message ORDER_AMOUNT = '$.payment_amount_minor_units'
| jsonextract field = Message BillingCurrency = '$.payment_currency'
| jsonextract field = Message 'Step Id' = '$.payment_gateway_step'
| jsonextract field = Message 'Process Phase' = '$.payment_gateway_phase'
| jsonextract field = Message 'Event Status' = '$.payment_gateway_step_status'
| jsonextract field = Message 'Elapsed Time (Gateway)' = '$.payment_gateway_step_latency_ms'
| jsonextract field = Message 'Gateway Step Count' = '$.payment_gateway_step_count'
| jsonextract field = Message 'Response Code' = '$.payment_processor_response_code'
| jsonextract field = Message 'Gateway ID' = '$.payment_processor_gateway_code'
| jsonextract field = Message 'Transaction ID' = '$.payment_network_transaction_id'
| jsonextract field = Message Result = '$.payment_card_avs_result'
| jsonextract field = Message 'Security Result' = '$.payment_card_cvv_result'
| jsonextract field = Message Program = '$.payment_3ds_program'
| jsonextract field = Message 'Flow Code' = '$.payment_3ds_eci'
| jsonextract field = Message Flow = '$.payment_3ds_flow'
| jsonextract field = Message 'Java APM Path' = '$.java_apm_path'
| jsonextract field = Message 'Downstream Component' = '$.java_apm_service_name'
| jsonextract field = Message 'Payment Processor' = '$.payment_processor_name'
| jsonextract field = Message 'Java APM Status Code' = '$.java_apm_status_code'
| jsonextract field = Message 'Java APM Latency ms' = '$.java_apm_latency_ms'
| jsonextract field = Message 'Java APM Error Type' = '$.java_apm_error_type'
| jsonextract field = Message msg = '$.event_message'
| where 'Payment Gateway Request ID' != null or 'Order ID' != null or 'Workflow ID' = 'checkout'
| sort Time
| fields Time, Service, 'Service Name', 'Workflow ID', 'Workflow Step',
         'Trace ID', 'Span ID', 'Request ID', 'Journey ID', 'User Action',
         'Checkout Step', 'Browser Trace ID', 'Order ID', 'Source Order ID',
         'Payment Gateway Request ID', 'Payment Provider',
         Gateway, Provider, Version, Method, ORDER_AMOUNT, BillingCurrency,
         'Step Id', 'Process Phase', 'Event Status',
         'Elapsed Time (Gateway)', 'Gateway Step Count', Latency,
         'Payment Status', 'Payment Risk Score', 'Payment Network',
         'Payment Wallet Token Hash', 'Response Code', 'Gateway ID',
         'Transaction ID', 'Result', 'Security Result', 'Program',
         'Flow Code', Flow, 'Error Type', 'Payment Interception',
         'Payment Redirect', 'Payment Redirect URL',
         'Java APM Path', 'Downstream Component', 'Payment Processor',
         'Java APM Status Code', 'Java APM Latency ms',
         'Java APM Error Type', msg
