-- ============================================================================
-- waf-vs-app-errors
-- Correlate WAF detections with app 5xx spikes using Request ID / client IP.
-- ============================================================================
('Security Action' != null or 'HTTP Status Code' >= 500)
| where Time > dateRelative(1h)
| stats count as Events,
        values('Security Action') as 'WAF Actions',
        values('HTTP Status Code') as 'HTTP Statuses'
  by 'Host IP Address (Client)', 'URL Path'
| sort -Events
