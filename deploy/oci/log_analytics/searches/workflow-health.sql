-- ============================================================================
-- workflow-health
-- Per-workflow latency + error-rate over the selected window.
-- ============================================================================
'Workflow ID' != null
| where Time > dateRelative(1h)
| stats count as Requests,
        countif('HTTP Status Code' >= 500) as Errors,
        pct('DB Elapsed ms', 95) as 'DB p95 ms'
  by 'Workflow ID', Service
| eval 'Error Rate %' = round((Errors / Requests) * 100, 2)
| sort -'Error Rate %'
