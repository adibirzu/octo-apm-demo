-- ============================================================================
-- chaos-vs-organic
-- Split error counts by whether chaos was active in the same window.
-- ============================================================================
'HTTP Status Code' >= 500
| where Time > dateRelative(2h)
| eval 'Origin' = if('Chaos Injected' = 'true', 'chaos', 'organic')
| stats count as Errors by 'Origin', 'Workflow ID', 'Chaos Scenario'
| sort -Errors
