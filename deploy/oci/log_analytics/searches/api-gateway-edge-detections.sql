-- ============================================================================
-- api-gateway-edge-detections
-- OCI API Gateway route-policy, auth, quota, and backend decisions correlated
-- with attack-lab trace ids.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Attack ID' = '<ATTACK_ID>' or 'Trace ID' = '<TRACE_ID>'.
-- ============================================================================
('API Gateway Request ID' != null)
| stats count as Events,
        min(Time) as 'First Seen',
        max(Time) as 'Last Seen',
        values('Gateway') as Gateways,
        values('Scope') as Scopes,
        values('Deployment ID') as Deployments,
        values('API Gateway Route') as Routes,
        values('Family') as 'Route Families',
        values('Host IP Address (Client)') as 'Client IPs',
        values('API Gateway Policy Decision') as Decisions,
        values('HTTP Status Code') as Statuses,
        values('API Gateway Latency ms') as Latencies,
        values('API Gateway Rate Remaining') as 'Rate Remaining',
        values('API Gateway Threat Signal') as 'Threat Signals',
        values('Trace ID') as Traces
  by 'Attack ID', 'API Gateway Action', 'Security Severity'
| sort -'Last Seen'
