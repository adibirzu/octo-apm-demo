-- ============================================================================
-- attack-lab-trace-timeline
-- Full event timeline for attack-lab evidence.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Attack ID' = '<ATTACK_ID>' or 'Trace ID' = '<TRACE_ID>'.
-- ============================================================================
'Attack ID' != null
| sort Time
| fields Time, Service, 'Attack ID', 'Run ID', 'Trace ID', 'Span ID',
         'Attack Stage', 'MITRE Tactic', 'MITRE Technique ID',
         'Host IP Address (Client)', 'Server Address', 'Destination IP', 'Destination Port',
         'Gateway', 'Scope', 'API Gateway Route',
         'API Gateway Request ID', 'API Gateway Action',
         'API Gateway Policy Decision', 'API Gateway Latency ms',
         'Host Name', 'Instance OCID', 'Compromised VM',
         'Payment Status', 'Payment Interception', 'Payment Redirect URL',
         'OSQuery Query', 'OSQuery Finding', msg
