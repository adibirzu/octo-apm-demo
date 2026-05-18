-- ============================================================================
-- chaos-vs-organic
-- Split error counts by whether chaos was active in the same window.
-- ============================================================================
'HTTP Status Code' >= 500
| where Time > dateRelative(2h)
| eval 'Origin' = if('Event Status' = 'true', 'chaos', 'organic')
| stats count as Errors by 'Origin', 'Workflow ID', 'Event Types'
| sort -Errors
