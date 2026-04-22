-- ============================================================================
-- trace-drilldown
-- Pivot a single trace across Shop + CRM + DB + WAF.
-- Parameter: :trace_id (required)
-- ============================================================================
'Trace ID' = :trace_id
| sort Time
| fields Time, Service, 'Workflow ID', 'Workflow Step', 'URL Path',
         'HTTP Status Code', 'DB Elapsed ms', 'WAF Rule Name', 'WAF Action',
         'Chaos Scenario', 'Chaos Injected', 'Original Log Content'
