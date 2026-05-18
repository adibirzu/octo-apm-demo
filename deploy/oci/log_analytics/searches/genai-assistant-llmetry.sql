-- ============================================================================
-- genai-assistant-llmetry
-- Assistant, Select AI, OCI GenAI, Langfuse, and LLMetry troubleshooting.
-- This query is live-safe for the current namespace field quota and uses
-- existing namespace fields from fields/octo-apm-correlation-fields.json.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Trace ID' = '<TRACE_ID>' or 'Session ID' = '<SESSION_ID>'.
-- ============================================================================
('Service Name' = 'octo-drone-shop'
 and (msg like '%assistant%' or msg like '%LLMetry%' or msg like '%GenAI%' or msg like '%Langfuse%' or msg like '%Select AI%'
      or 'Session ID' != null or 'Application Hash' != null))
| stats count as Events,
        values('Trace ID') as Traces,
        values('Span ID') as Spans,
        values('Session ID') as 'Assistant Sessions',
        values(Session) as 'Langfuse Sessions',
        values(Provider) as Providers,
        values('Model Version') as Models,
        values('Application Hash') as 'Prompt Hashes',
        values('Current Hash') as 'Response Hashes',
        avg('Server Response Wait Time') as 'Avg LLMetry ms',
        sum('Content Size In') as 'Input Tokens',
        sum('Content Size Out') as 'Output Tokens'
  by Service, 'Service Name', 'Workflow ID'
| sort -Events
