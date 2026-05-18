-- ============================================================================
-- oke-checkout-payment-correlation
-- OKE stdout timeline for checkout, wallet/card, payment gateway, Java sidecar,
-- CRM order sync, and trace/log correlation.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Trace ID' = '<TRACE_ID>', 'Order ID' = '<ORDER_ID>', or
-- 'Payment Gateway Request ID' = '<REQUEST_ID>'.
-- ============================================================================
'Log Source' = 'SOC Application Logs'
and 'Service Namespace' = 'octo'
and 'Service Name' in ('octo-drone-shop-oke', 'enterprise-crm-portal-oke', 'octo-java-app-server-oke')
| where 'Workflow ID' = 'checkout'
    or 'Workflow Step' = 'payment'
    or 'Order ID' != null
    or 'Payment Gateway Request ID' != null
    or 'Payment Provider' != null
    or 'Downstream Component' != null
| sort Time
| fields Time, 'Log Source', Namespace, 'Service Name',
         'Trace ID', 'Span ID', 'Workflow ID', 'Workflow Step',
         Message, 'URL Path', 'HTTP Status Code',
         'Order ID', 'Source Order ID', 'Payment Gateway Request ID',
         'Payment Provider', 'Payment Status', 'Payment Network',
         'Payment Wallet Token Hash', Method, ORDER_AMOUNT, BillingCurrency,
         Gateway, Provider, Version, 'Step Id', 'Process Phase',
         'Event Status', 'Elapsed Time (Gateway)', 'Response Code',
         'Gateway ID', 'Transaction ID', Result, 'Security Result',
         Program, 'Flow Code', Flow, 'Java APM Path',
         'Downstream Component', 'Java APM Status Code',
         'Java APM Latency ms', 'Java APM Error Type'
