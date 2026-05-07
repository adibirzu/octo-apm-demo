-- ============================================================================
-- attack-lab-trace-timeline
-- Full event timeline for one attack id or, when parameterized, one trace id.
-- Parameters: :attack_id optional, :trace_id optional.
-- ============================================================================
('Attack ID' = :attack_id or 'Trace ID' = :trace_id)
| sort Time
| fields Time, Service, 'Attack ID', 'Run ID', 'Trace ID', 'Span ID',
         'Attack Stage', 'MITRE Tactic', 'MITRE Technique ID',
         'Client IP', 'Server Address', 'Destination IP', 'Destination Port',
         'API Gateway Name', 'API Gateway Scope', 'API Gateway Route',
         'API Gateway Request ID', 'API Gateway Action',
         'API Gateway Policy Decision', 'API Gateway Latency ms',
         'Host Name', 'Instance OCID', 'Compromised VM',
         'Payment Status', 'Payment Interception', 'Payment Redirect URL',
         'OSQuery Query', 'OSQuery Finding', 'Original Log Content'
