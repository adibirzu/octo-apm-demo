-- ============================================================================
-- db-slowness-hotspots
-- Top slow SQL statements by workflow over the last 30 minutes.
-- ============================================================================
'DB Elapsed ms' > 250
| where Time > dateRelative(30m)
| stats count as Hits,
        avg('DB Elapsed ms') as 'Avg ms',
        pct('DB Elapsed ms', 95) as 'p95 ms',
        max('DB Elapsed ms') as 'Max ms'
  by 'Workflow ID', 'DB Statement', Service
| sort -'p95 ms'
