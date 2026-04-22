-- ============================================================================
-- waf-vs-app-errors
-- Correlate WAF detections with app 5xx spikes using Request ID / Client IP.
-- ============================================================================
('WAF Action' != null or 'HTTP Status Code' >= 500)
| where Time > dateRelative(1h)
| stats count as Events,
        countif('WAF Action' != null) as 'WAF Detections',
        countif('HTTP Status Code' >= 500) as 'App 5xx'
  by 'Client IP', 'URL Path'
| where 'WAF Detections' > 0 and 'App 5xx' > 0
| sort -Events
